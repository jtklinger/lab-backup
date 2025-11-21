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
  vm_id?: number;
  vm_name?: string;
  container_id?: number;
  container_name?: string;
  storage_backend_id: number;
  storage_backend_name?: string;
  storage_path: string;
  size: number;  // Changed from size_bytes to match backend
  status: BackupStatus;
  compression_algorithm?: string;
  encryption_key_id?: number;
  storage_encryption_type?: StorageEncryptionType;
  storage_encryption_key_id?: string;
  checksum?: string;
  is_immutable: boolean;
  immutable_until?: string;
  legal_hold_enabled: boolean;
  legal_hold_reason?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  error_message?: string;
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
  created_at: string;
  updated_at: string;
}

// Jobs
export const JobStatus = {
  PENDING: 'PENDING',
  RUNNING: 'RUNNING',
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
} as const;

export type JobStatus = typeof JobStatus[keyof typeof JobStatus];

export interface Job {
  id: number;
  backup_id?: number;
  schedule_id?: number;
  job_type: string;
  status: JobStatus;
  progress_percentage?: number;
  log_output?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
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
