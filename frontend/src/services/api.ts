/**
 * API Client for Lab Backup System
 *
 * Centralized axios instance with authentication and error handling.
 * Related: Issue #16 - React Frontend
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios';

// API base URL from environment variable or default to backend URL
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://localhost:8443';

/**
 * Axios instance with default configuration
 */
const api: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor to add authentication token
 */
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor for error handling
 */
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;

/**
 * API error handler utility
 */
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    if (error.response?.data?.detail) {
      return error.response.data.detail;
    }
    if (error.response?.data?.message) {
      return error.response.data.message;
    }
    if (error.message) {
      return error.message;
    }
  }
  return 'An unexpected error occurred';
};

/**
 * Settings API
 */
export const settingsAPI = {
  /**
   * Get all setting categories
   */
  getCategories: () => api.get<string[]>('/settings/categories'),

  /**
   * Get settings by category
   */
  getByCategory: (category: string) => api.get(`/settings/category/${category}`),

  /**
   * Get specific setting
   */
  get: (key: string) => api.get(`/settings/${key}`),

  /**
   * Update setting
   */
  update: (key: string, value: string) => api.put(`/settings/${key}`, { value }),

  /**
   * Bulk update settings
   */
  bulkUpdate: (updates: Record<string, string>) => api.put('/settings/bulk', updates),
};

/**
 * SSH Key API
 */
export const sshKeyAPI = {
  /**
   * List SSH keys for a host
   */
  list: (hostId: number) => api.get(`/kvm/hosts/${hostId}/ssh-keys`),

  /**
   * Upload SSH key
   */
  upload: (hostId: number, data: { name: string; private_key: string }) =>
    api.post(`/kvm/hosts/${hostId}/ssh-keys`, data),

  /**
   * Generate new SSH key pair
   */
  generate: (hostId: number, data: { name: string; key_type?: string; key_size?: number }) =>
    api.post(`/kvm/hosts/${hostId}/ssh-keys/generate`, data),

  /**
   * Get public key
   */
  getPublicKey: (hostId: number, keyId: number) =>
    api.get(`/kvm/hosts/${hostId}/ssh-keys/${keyId}/public`),

  /**
   * Delete SSH key
   */
  delete: (hostId: number, keyId: number) =>
    api.delete(`/kvm/hosts/${hostId}/ssh-keys/${keyId}`),
};

/**
 * Jobs API
 */
import type { Job, JobLog, JobsListResponse, JobStatus, JobType, ApplicationLogsResponse } from '../types';

export const jobsAPI = {
  /**
   * List jobs with filtering and pagination
   */
  list: (params?: {
    status?: JobStatus;
    job_type?: JobType;
    start_date?: string;
    end_date?: string;
    limit?: number;
    offset?: number;
  }) => api.get<JobsListResponse>('/jobs', { params }),

  /**
   * Get single job details
   */
  get: (id: number) => api.get<Job>(`/jobs/${id}`),

  /**
   * Get logs for a specific job
   */
  getLogs: (id: number, level?: string) =>
    api.get<JobLog[]>(`/jobs/${id}/logs`, { params: level ? { level } : {} }),

  /**
   * Cancel a running or pending job
   */
  cancel: (id: number) => api.post(`/jobs/${id}/cancel`),
};

/**
 * Application Logs API
 */
export const logsAPI = {
  /**
   * Get application logs with filtering
   */
  getApplicationLogs: (params?: {
    level?: string;
    search?: string;
    job_id?: number;
    backup_id?: number;
    limit?: number;
    offset?: number;
  }) => api.get<ApplicationLogsResponse>('/logs/application', { params }),

  /**
   * Get log statistics
   */
  getStats: () => api.get('/logs/application/stats'),
};

/**
 * Get WebSocket URL for job logs streaming
 */
export const getJobWebSocketUrl = (jobId: number): string => {
  const token = localStorage.getItem('auth_token');
  // Use wss for https, ws for http
  const wsProtocol = API_BASE_URL.startsWith('https') ? 'wss' : 'ws';
  const wsHost = API_BASE_URL.replace(/^https?:\/\//, '');
  return `${wsProtocol}://${wsHost}/api/v1/ws/jobs/${jobId}?token=${token}`;
};
