/**
 * WebSocket hook for real-time job log streaming
 *
 * Connects to the job WebSocket endpoint and receives real-time log updates.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { getJobWebSocketUrl } from '../services/api';
import type { JobLog, WSMessage } from '../types';

export interface UseJobWebSocketResult {
  logs: JobLog[];
  status: string | null;
  connected: boolean;
  error: string | null;
  isComplete: boolean;
  clearLogs: () => void;
}

export function useJobWebSocket(jobId: number | null): UseJobWebSocketResult {
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const clearLogs = useCallback(() => {
    setLogs([]);
    setError(null);
    setIsComplete(false);
  }, []);

  useEffect(() => {
    // Don't connect if no job ID
    if (!jobId) {
      setConnected(false);
      return;
    }

    // Reset state for new connection
    setLogs([]);
    setStatus(null);
    setError(null);
    setIsComplete(false);

    const wsUrl = getJobWebSocketUrl(jobId);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);

        switch (msg.type) {
          case 'connected':
            setStatus(msg.status);
            break;

          case 'log':
            setLogs(prev => [...prev, msg.data]);
            break;

          case 'status':
            setStatus(msg.status);
            break;

          case 'complete':
            setStatus(msg.status);
            setIsComplete(true);
            break;

          case 'error':
            setError(msg.message);
            break;
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      setError('WebSocket connection error');
    };

    ws.onclose = (event) => {
      setConnected(false);
      if (event.code === 4001) {
        setError('Invalid authentication token');
      } else if (event.code === 4003) {
        setError('Insufficient permissions');
      } else if (event.code === 4004) {
        setError('Job not found');
      } else if (!isComplete && event.code !== 1000) {
        setError(`Connection closed unexpectedly (code: ${event.code})`);
      }
    };

    wsRef.current = ws;

    // Cleanup on unmount or job change
    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [jobId, isComplete]);

  return { logs, status, connected, error, isComplete, clearLogs };
}
