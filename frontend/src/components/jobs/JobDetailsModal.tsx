/**
 * Job Details Modal with real-time log streaming
 *
 * Shows job metadata and logs with WebSocket support for running jobs.
 */
import { useState, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Chip,
  IconButton,
  Tooltip,
  CircularProgress,
  LinearProgress,
  Divider,
  Paper,
  Alert,
  Collapse,
} from '@mui/material';
import {
  Close as CloseIcon,
  ContentCopy as CopyIcon,
  Download as DownloadIcon,
  FiberManualRecord as DotIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import type { Job, JobLog } from '../../types';
import { useJobWebSocket } from '../../hooks/useJobWebSocket';
import { jobsAPI } from '../../services/api';

interface JobDetailsModalProps {
  open: boolean;
  job: Job | null;
  onClose: () => void;
}

// Log level colors
const levelColors: Record<string, string> = {
  DEBUG: '#9e9e9e',    // gray
  INFO: '#2196f3',     // blue
  WARNING: '#ff9800',  // orange
  ERROR: '#f44336',    // red
  CRITICAL: '#d32f2f', // dark red
};

// Status chip colors
const statusColors: Record<string, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
  pending: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

export function JobDetailsModal({ open, job, onClose }: JobDetailsModalProps) {
  const [historicalLogs, setHistoricalLogs] = useState<JobLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Use WebSocket for running jobs
  const isRunning = job?.status === 'running' || job?.status === 'pending';
  const { logs: wsLogs, progress, connected, error: wsError, isComplete } = useJobWebSocket(
    isRunning && open ? job?.id ?? null : null
  );
  const [showDiskDetails, setShowDiskDetails] = useState(false);

  // Load historical logs for completed/failed jobs
  useEffect(() => {
    if (open && job && !isRunning) {
      setLoadingLogs(true);
      jobsAPI.getLogs(job.id)
        .then(res => {
          setHistoricalLogs(res.data);
        })
        .catch(err => {
          console.error('Failed to load job logs:', err);
        })
        .finally(() => {
          setLoadingLogs(false);
        });
    } else {
      setHistoricalLogs([]);
    }
  }, [open, job, isRunning]);

  // Determine which logs to display
  const displayLogs = isRunning ? wsLogs : historicalLogs;

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [displayLogs, autoScroll]);

  // Handle scroll to detect if user scrolled up
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    }
  };

  // Copy logs to clipboard
  const handleCopyLogs = () => {
    const logText = displayLogs
      .map(log => `[${log.timestamp}] [${log.level}] ${log.message}`)
      .join('\n');
    navigator.clipboard.writeText(logText);
  };

  // Download logs as file
  const handleDownloadLogs = () => {
    const logText = displayLogs
      .map(log => {
        let line = `[${log.timestamp}] [${log.level}] ${log.message}`;
        if (log.details) {
          line += `\n  Details: ${JSON.stringify(log.details, null, 2)}`;
        }
        return line;
      })
      .join('\n');

    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `job-${job?.id}-logs.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!job) return null;

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return '-';
    return format(new Date(dateStr), 'MMM d, yyyy HH:mm:ss');
  };

  const getDuration = () => {
    if (!job.started_at) return '-';
    const start = new Date(job.started_at);
    const end = job.completed_at ? new Date(job.completed_at) : new Date();
    const seconds = Math.floor((end.getTime() - start.getTime()) / 1000);

    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  // Format bytes to human-readable size
  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  // Format ETA in human-readable format
  const formatEta = (seconds: number | null): string => {
    if (seconds === null || seconds <= 0) return 'Calculating...';
    if (seconds < 60) return `${Math.round(seconds)}s remaining`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s remaining`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m remaining`;
  };

  // Format transfer rate
  const formatRate = (bps: number): string => {
    if (bps === 0) return '0 B/s';
    const k = 1024;
    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    const i = Math.floor(Math.log(bps) / Math.log(k));
    return `${parseFloat((bps / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  // Get phase display name
  const getPhaseLabel = (phase: string): string => {
    const labels: Record<string, string> = {
      preparing: 'Preparing',
      disk_transfer: 'Transferring Disks',
      archiving: 'Creating Archive',
      encrypting: 'Encrypting',
      uploading: 'Uploading to Storage',
    };
    return labels[phase] || phase;
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: { height: '80vh', display: 'flex', flexDirection: 'column' }
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">Job #{job.id}</Typography>
          <Chip
            label={job.status}
            color={statusColors[job.status] || 'default'}
            size="small"
          />
          {isRunning && connected && (
            <Tooltip title="Connected - Live updates">
              <DotIcon sx={{ color: 'success.main', fontSize: 12 }} />
            </Tooltip>
          )}
          {isRunning && !connected && (
            <Tooltip title="Disconnected">
              <DotIcon sx={{ color: 'error.main', fontSize: 12 }} />
            </Tooltip>
          )}
        </Box>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Job metadata */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">Type</Typography>
              <Typography variant="body2">{job.type}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Started</Typography>
              <Typography variant="body2">{formatDate(job.started_at)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Completed</Typography>
              <Typography variant="body2">{formatDate(job.completed_at)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Duration</Typography>
              <Typography variant="body2">{getDuration()}</Typography>
            </Box>
          </Box>

          {job.error_message && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {job.error_message}
            </Alert>
          )}

          {wsError && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              WebSocket: {wsError}
            </Alert>
          )}
        </Box>

        {/* Progress section - only show when progress data is available */}
        {progress && isRunning && (
          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            {/* Overall progress */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="subtitle2">
                  {getPhaseLabel(progress.overall.current_phase)}
                  {progress.overall.current_phase === 'disk_transfer' && progress.overall.total_disks > 0 && (
                    <Typography component="span" variant="caption" sx={{ ml: 1, color: 'text.secondary' }}>
                      ({progress.overall.current_disk_index + 1} of {progress.overall.total_disks} disks)
                    </Typography>
                  )}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {formatEta(progress.overall.eta_seconds)}
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={progress.overall.percent}
                sx={{ height: 8, borderRadius: 1, mb: 1 }}
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">
                  {formatBytes(progress.overall.bytes_transferred)} / {formatBytes(progress.overall.bytes_total)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {progress.overall.percent.toFixed(1)}%
                </Typography>
              </Box>
            </Box>

            {/* Disk details toggle */}
            {progress.disks && progress.disks.length > 0 && (
              <>
                <Button
                  size="small"
                  onClick={() => setShowDiskDetails(!showDiskDetails)}
                  startIcon={<StorageIcon />}
                  sx={{ mb: 1 }}
                >
                  {showDiskDetails ? 'Hide' : 'Show'} Disk Details ({progress.disks.length})
                </Button>
                <Collapse in={showDiskDetails}>
                  <Box sx={{ pl: 2, borderLeft: '2px solid', borderColor: 'divider' }}>
                    {progress.disks.map((disk, index) => (
                      <Box key={disk.target} sx={{ mb: index < progress.disks.length - 1 ? 2 : 0 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                          <Typography variant="body2">
                            {disk.target}
                            <Chip
                              label={disk.status}
                              size="small"
                              color={
                                disk.status === 'completed' ? 'success' :
                                disk.status === 'transferring' ? 'primary' :
                                disk.status === 'failed' ? 'error' : 'default'
                              }
                              sx={{ ml: 1, height: 20, fontSize: '0.7rem' }}
                            />
                          </Typography>
                          {disk.status === 'transferring' && disk.transfer_rate_bps > 0 && (
                            <Typography variant="caption" color="text.secondary">
                              {formatRate(disk.transfer_rate_bps)}
                            </Typography>
                          )}
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={disk.percent}
                          sx={{ height: 4, borderRadius: 1, mb: 0.5 }}
                          color={
                            disk.status === 'completed' ? 'success' :
                            disk.status === 'failed' ? 'error' : 'primary'
                          }
                        />
                        <Typography variant="caption" color="text.secondary">
                          {formatBytes(disk.bytes_transferred)} / {formatBytes(disk.bytes_total)}
                          ({disk.percent.toFixed(1)}%)
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Collapse>
              </>
            )}
          </Paper>
        )}

        {/* Logs section header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle2">
            Logs ({displayLogs.length})
            {isRunning && !isComplete && (
              <Typography component="span" variant="caption" sx={{ ml: 1, color: 'text.secondary' }}>
                - Live streaming...
              </Typography>
            )}
          </Typography>
          <Box>
            <Tooltip title="Copy logs">
              <IconButton size="small" onClick={handleCopyLogs} disabled={displayLogs.length === 0}>
                <CopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Download logs">
              <IconButton size="small" onClick={handleDownloadLogs} disabled={displayLogs.length === 0}>
                <DownloadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* Logs container */}
        <Paper
          variant="outlined"
          ref={logContainerRef}
          onScroll={handleScroll}
          sx={{
            flex: 1,
            overflow: 'auto',
            bgcolor: '#1e1e1e',
            p: 2,
            fontFamily: 'monospace',
            fontSize: '0.85rem',
            lineHeight: 1.5,
          }}
        >
          {loadingLogs && (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress size={24} />
            </Box>
          )}

          {!loadingLogs && displayLogs.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
              No logs available
            </Typography>
          )}

          {displayLogs.map((log, index) => (
            <Box
              key={log.id || index}
              sx={{
                display: 'flex',
                gap: 1,
                mb: 0.5,
                '&:hover': { bgcolor: 'rgba(255,255,255,0.05)' }
              }}
            >
              <Typography
                component="span"
                sx={{ color: '#6a9955', whiteSpace: 'nowrap' }}
              >
                {format(new Date(log.timestamp), 'HH:mm:ss.SSS')}
              </Typography>
              <Typography
                component="span"
                sx={{
                  color: levelColors[log.level] || '#fff',
                  fontWeight: log.level === 'ERROR' || log.level === 'CRITICAL' ? 'bold' : 'normal',
                  minWidth: '70px',
                }}
              >
                [{log.level}]
              </Typography>
              <Box sx={{ flex: 1 }}>
                <Typography
                  component="span"
                  sx={{ color: '#d4d4d4', wordBreak: 'break-word' }}
                >
                  {log.message}
                </Typography>
                {log.details && (
                  <Box
                    component="pre"
                    sx={{
                      color: '#808080',
                      fontSize: '0.8rem',
                      m: 0,
                      mt: 0.5,
                      pl: 2,
                      borderLeft: '2px solid #404040',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                    }}
                  >
                    {JSON.stringify(log.details, null, 2)}
                  </Box>
                )}
              </Box>
            </Box>
          ))}
        </Paper>
      </DialogContent>

      <DialogActions>
        {!autoScroll && (
          <Button
            size="small"
            onClick={() => {
              setAutoScroll(true);
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
              }
            }}
          >
            Jump to Latest
          </Button>
        )}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
