/**
 * TypeScript type definitions for Lab Backup System
 *
 * Related: Issue #16 - React Frontend
 */

// User and Authentication
export const UserRole = {
  ADMIN: 'admin',
  OPERATOR: 'operator',
  VIEWER: 'viewer',
} as const;

export type UserRole = typeof UserRole[keyof typeof UserRole];

export interface User {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// KVM Hosts
export const KVMAuthType = {
  SSH_KEY: 'SSH_KEY',
  PASSWORD: 'PASSWORD',
} as const;

export type KVMAuthType = typeof KVMAuthType[keyof typeof KVMAuthType];

export interface KVMHost {
  id: number;
  name: string;
  hostname: string;
  port: number;
  username: string;
  auth_type: KVMAuthType;
  ssh_key_path?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_connection?: string;
  connection_status?: string;
}

// Podman Hosts
export interface PodmanHost {
  id: number;
  name: string;
  hostname: string;
  port: number;
  username: string;
  ssh_key_path?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// VMs
export interface VM {
  id: number;
  name: string;
  kvm_host_id: number;
  kvm_host_name?: string;
  state?: string;
  created_at: string;
  updated_at: string;
}

// Containers
export interface Container {
  id: number;
  name: string;
  podman_host_id: number;
  podman_host_name?: string;
  state?: string;
  created_at: string;
  updated_at: string;
}

// Storage Backends
export const StorageType = {
  LOCAL: 'local',
  S3: 's3',
  SMB: 'smb',
  NFS: 'nfs',
} as const;

export type StorageType = typeof StorageType[keyof typeof StorageType];

export interface StorageBackend {
  id: number;
  name: string;
  type: StorageType;
  config: Record<string, any>;
  enabled: boolean;
  capacity?: number;
  used?: number;
  threshold: number;
  last_check?: string;
  encryption_strategy?: string;
  encryption_key_id?: number;
  encryption_config?: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

// Backups
export const BackupStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const;

export type BackupStatus = typeof BackupStatus[keyof typeof BackupStatus];

export const StorageEncryptionType = {
  NONE: 'NONE',
  APP_LEVEL: 'APP_LEVEL',
  SSE_S3: 'SSE_S3',
  SSE_KMS: 'SSE_KMS',
  SSE_C: 'SSE_C',
} as const;

export type StorageEncryptionType = typeof StorageEncryptionType[keyof typeof StorageEncryptionType];

export interface Backup {
  id: number;
  schedule_id?: number;
  source_name: string;
  source_type: SourceType;
  backup_type: string;
  backup_mode: string;
  parent_backup_id?: number;
  status: BackupStatus;
  size?: number;
  compressed_size?: number;
  storage_path?: string;
  started_at?: string;
  completed_at?: string;
  expires_at?: string;
  // Verification fields
  verified: boolean;
  verification_date?: string;
  verification_status?: string;
  verification_error?: string;
  verified_table_count?: number;
  verified_size_bytes?: number;
  verification_duration_seconds?: number;
  // Chain tracking fields
  chain_id?: string;
  sequence_number?: number;
  original_size?: number;
  dedupe_ratio?: number;
  compression_ratio?: number;
  space_saved_bytes?: number;
  // Immutability fields
  immutable: boolean;
  retention_until?: string;
  retention_mode?: string;
  immutability_reason?: string;
  // Storage encryption
  storage_encryption_type?: string;
  storage_encryption_key_id?: string;
  storage_backend_id?: number;
  // Legacy fields for backward compatibility (deprecated - use source_name)
  vm_name?: string;
  container_name?: string;
  vm_id?: number;
  container_id?: number;
  storage_backend_name?: string;
  is_immutable?: boolean;
  immutable_until?: string;
  legal_hold_enabled?: boolean;
  legal_hold_reason?: string;
  created_at?: string;
  compression_algorithm?: string;
}

// Schedules
export const SourceType = {
  VM: 'vm',
  CONTAINER: 'container',
} as const;

export type SourceType = typeof SourceType[keyof typeof SourceType];

export const ScheduleType = {
  FULL: 'full',
  INCREMENTAL: 'incremental',
} as const;

export type ScheduleType = typeof ScheduleType[keyof typeof ScheduleType];

export interface Schedule {
  id: number;
  name: string;
  source_type: SourceType;
  source_id: number;
  schedule_type: ScheduleType;
  cron_expression: string;
  retention_config: Record<string, any>;
  storage_backend_id: number;
  enabled: boolean;
  last_run?: string;
  next_run?: string;
  // Incremental backup configuration (Issue #15)
  backup_mode_policy: 'auto' | 'full_only' | 'incremental_preferred';
  max_chain_length: number;
  full_backup_day?: number;
  last_full_backup_id?: number;
  checkpoint_name?: string;
  incremental_capable?: boolean;
  capability_checked_at?: string;
  created_at: string;
  updated_at: string;
}

// Backup Chain Types (Issue #15)
export interface BackupChain {
  chain_id: string;
  backup_count: number;
  backups: Backup[];
}

export interface ChainStatistics {
  chain_id: string;
  source_type: string;
  source_id: number;
  source_name: string;
  backup_count: number;
  first_backup: string;
  last_backup: string;
  total_original_size_bytes: number;
  total_compressed_size_bytes: number;
  total_space_saved_bytes: number;
  average_dedupe_ratio: number;
  average_compression_ratio: number;
  backups: {
    id: number;
    sequence: number;
    mode: string;
    created_at: string;
    size?: number;
    dedupe_ratio?: number;
    compression_ratio?: number;
  }[];
}

export interface RestorationPlan {
  success: boolean;
  target_backup_id: number;
  target_backup_date: string;
  source_name: string;
  source_type: string;
  chain_id: string;
  backup_count: number;
  total_download_size_bytes: number;
  total_download_size_gb: number;
  restoration_steps: {
    step: number;
    backup_id: number;
    backup_mode: string;
    sequence_number: number;
    storage_path?: string;
    size_bytes?: number;
    created_at: string;
    action: string;
  }[];
  estimated_restore_time_seconds: number;
}

export interface ChainIntegrity {
  valid: boolean;
  chain_id: string;
  total_backups: number;
  completed_backups: number;
  issues: {
    type: string;
    message: string;
    severity: 'critical' | 'warning';
  }[];
  restorable: boolean;
}

// Jobs
export const JobStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

export type JobStatus = typeof JobStatus[keyof typeof JobStatus];

export const JobType = {
  BACKUP: 'backup',
  RESTORE: 'restore',
  VERIFICATION: 'verification',
  CLEANUP: 'cleanup',
  SYNC: 'sync',
} as const;

export type JobType = typeof JobType[keyof typeof JobType];

export interface Job {
  id: number;
  type: JobType;
  status: JobStatus;
  backup_id?: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface JobLog {
  id: number;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  message: string;
  details?: Record<string, any>;
}

export interface JobsListResponse {
  jobs: Job[];
  total: number;
  limit: number;
  offset: number;
}

// WebSocket message types
export type WSMessage =
  | { type: 'connected'; job_id: number; status: string; message: string }
  | { type: 'log'; data: JobLog }
  | { type: 'status'; status: string }
  | { type: 'complete'; status: string; message: string }
  | { type: 'error'; message: string };

// Application Logs (system-level logging)
export interface ApplicationLog {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  module?: string;
  function?: string;
  exception?: string;
  job_id?: number;
  backup_id?: number;
}

export interface ApplicationLogsResponse {
  logs: ApplicationLog[];
  total: number;
  limit: number;
  offset: number;
}

// Audit Logs
export const AuditSeverity = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  WARNING: 'WARNING',
  ERROR: 'ERROR',
  CRITICAL: 'CRITICAL',
} as const;

export type AuditSeverity = typeof AuditSeverity[keyof typeof AuditSeverity];

export interface AuditLog {
  id: number;
  created_at: string;
  user_id?: number;
  username?: string;
  action: string;
  resource_type?: string;
  resource_id?: number;
  resource_name?: string;
  ip_address?: string;
  user_agent?: string;
  request_method?: string;
  request_path?: string;
  response_status?: number;
  response_message?: string;
  duration_ms?: number;
  severity: AuditSeverity;
  tags?: string[];
}

// Dashboard Statistics
export interface DashboardStats {
  total_backups: number;
  successful_backups: number;
  failed_backups: number;
  total_size_bytes: number;
  active_jobs: number;
  total_vms: number;
  total_containers: number;
  active_schedules: number;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// Settings
export interface Setting {
  id: number;
  key: string;
  value: string;
  category: string;
  description: string;
  data_type: string;
  is_secret: boolean;
  created_at: string;
  updated_at: string;
}

export interface SettingUpdate {
  key: string;
  value: string;
}

export interface SettingsCategory {
  category: string;
  settings: Setting[];
}

// SSH Keys
export interface SSHKey {
  id: number;
  name: string;
  fingerprint: string;
  key_type: string;
  public_key?: string;
  created_at: string;
}

export interface SSHKeyCreate {
  name: string;
  private_key: string;
}

export interface SSHKeyGenerate {
  name: string;
  key_type?: string;
  key_size?: number;
}
