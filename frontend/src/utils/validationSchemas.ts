/**
 * Form Validation Schemas
 *
 * Zod schemas for form validation across the application.
 * Related: Issue #24 - Improve form validation and error messages
 */
import { z } from 'zod';

// ============================================================================
// COMMON VALIDATORS
// ============================================================================

const hostname = z
  .string()
  .min(1, 'Hostname is required')
  .regex(
    /^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/,
    'Invalid hostname format'
  );

const port = z
  .number()
  .min(1, 'Port must be at least 1')
  .max(65535, 'Port must not exceed 65535');

const email = z.string().email('Invalid email address');

const password = z.string().min(8, 'Password must be at least 8 characters');

const requiredString = (fieldName: string) =>
  z.string().min(1, `${fieldName} is required`);

// Cron expression validator (5-field format: minute hour day month weekday)
const cronExpression = z
  .string()
  .min(1, 'Cron expression is required')
  .refine(
    (val) => {
      const parts = val.trim().split(/\s+/);
      if (parts.length !== 5) return false;

      const [minute, hour, day, month, weekday] = parts;

      // Validate each field (basic validation)
      const isValidField = (field: string, min: number, max: number) => {
        if (field === '*') return true;
        if (field.includes('/')) {
          const [range, step] = field.split('/');
          return range === '*' && !isNaN(Number(step));
        }
        if (field.includes('-')) {
          const [start, end] = field.split('-');
          const s = Number(start);
          const e = Number(end);
          return !isNaN(s) && !isNaN(e) && s >= min && e <= max && s <= e;
        }
        if (field.includes(',')) {
          return field.split(',').every((n) => {
            const num = Number(n);
            return !isNaN(num) && num >= min && num <= max;
          });
        }
        const num = Number(field);
        return !isNaN(num) && num >= min && num <= max;
      };

      return (
        isValidField(minute, 0, 59) &&
        isValidField(hour, 0, 23) &&
        isValidField(day, 1, 31) &&
        isValidField(month, 1, 12) &&
        isValidField(weekday, 0, 7)
      );
    },
    {
      message: 'Invalid cron expression format (use: minute hour day month weekday)',
    }
  );

// Path validator (Unix-style paths)
const unixPath = z
  .string()
  .min(1, 'Path is required')
  .refine(
    (val) => val.startsWith('/') || val.startsWith('~'),
    'Path must start with / or ~'
  );

// ============================================================================
// LOGIN FORM
// ============================================================================

export const loginSchema = z.object({
  username: requiredString('Username'),
  password: requiredString('Password'),
});

export type LoginFormData = z.infer<typeof loginSchema>;

// ============================================================================
// USER FORMS
// ============================================================================

export const createUserSchema = z.object({
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(50, 'Username must not exceed 50 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Username can only contain letters, numbers, hyphens, and underscores'),
  email: email,
  password: password,
  role: z.enum(['admin', 'operator', 'viewer']),
  is_active: z.boolean(),
});

export const updateUserSchema = z.object({
  username: z
    .string()
    .min(3, 'Username must be at least 3 characters')
    .max(50, 'Username must not exceed 50 characters')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Username can only contain letters, numbers, hyphens, and underscores'),
  email: email,
  password: z.string().min(8, 'Password must be at least 8 characters').optional().or(z.literal('')),
  role: z.enum(['admin', 'operator', 'viewer']),
  is_active: z.boolean(),
});

export type CreateUserFormData = z.infer<typeof createUserSchema>;
export type UpdateUserFormData = z.infer<typeof updateUserSchema>;

// ============================================================================
// KVM HOST FORMS
// ============================================================================

export const kvmHostSchema = z
  .object({
    name: requiredString('Name'),
    hostname: hostname,
    port: port,
    username: requiredString('Username'),
    auth_type: z.enum(['SSH_KEY', 'PASSWORD']),
    ssh_key_path: z.string().optional(),
    password: z.string().optional(),
    is_active: z.boolean(),
  })
  .refine(
    (data) => {
      if (data.auth_type === 'SSH_KEY') {
        return !!data.ssh_key_path && data.ssh_key_path.trim().length > 0;
      }
      return true;
    },
    {
      message: 'SSH key path is required when using SSH key authentication',
      path: ['ssh_key_path'],
    }
  )
  .refine(
    (data) => {
      if (data.auth_type === 'PASSWORD') {
        return !!data.password && data.password.trim().length > 0;
      }
      return true;
    },
    {
      message: 'Password is required when using password authentication',
      path: ['password'],
    }
  );

export type KVMHostFormData = z.infer<typeof kvmHostSchema>;

// ============================================================================
// PODMAN HOST FORMS
// ============================================================================

export const podmanHostSchema = z.object({
  name: requiredString('Name'),
  hostname: hostname,
  port: port,
  username: requiredString('Username'),
  ssh_key_path: unixPath,
  is_active: z.boolean(),
});

export type PodmanHostFormData = z.infer<typeof podmanHostSchema>;

// ============================================================================
// STORAGE BACKEND FORMS
// ============================================================================

export const storageBackendSchema = z.object({
  name: requiredString('Name'),
  type: z.enum(['LOCAL', 'S3', 'SMB']),
  is_active: z.boolean(),
});

export type StorageBackendFormData = z.infer<typeof storageBackendSchema>;

// ============================================================================
// SCHEDULE FORMS
// ============================================================================

export const scheduleSchema = z
  .object({
    name: requiredString('Name'),
    cron_expression: cronExpression,
    vm_id: z.number().nullable(),
    container_id: z.number().nullable(),
    storage_backend_id: z.number().min(1, 'Please select a storage backend'),
    retention_count: z.number().min(1, 'Retention count must be at least 1').optional(),
    compression_algorithm: z.string().min(1, 'Please select a compression algorithm'),
    is_active: z.boolean(),
  })
  .refine(
    (data) => {
      // Either vm_id or container_id must be set, but not both
      return (data.vm_id !== null && data.container_id === null) ||
             (data.vm_id === null && data.container_id !== null);
    },
    {
      message: 'Please select either a VM or a Container (not both)',
      path: ['vm_id'],
    }
  );

export type ScheduleFormData = z.infer<typeof scheduleSchema>;

// ============================================================================
// BACKUP WIZARD FORMS
// ============================================================================

export const backupWizardSchema = z
  .object({
    // Step 1: Source selection
    sourceType: z.enum(['vm', 'container']),
    vmId: z.number().nullable(),
    containerId: z.number().nullable(),

    // Step 2: Storage selection
    storageBackendId: z.number().nullable(),

    // Step 3: Options
    backupMode: z.enum(['full', 'incremental']),
    retentionDays: z.number().min(1).max(3650).optional(),
    compressionAlgorithm: requiredString('Compression algorithm'),
    encryptionEnabled: z.boolean(),
    encryptionKeyId: z.number().nullable(),
    encryptionStrategy: z.string().optional(),
    immutable: z.boolean(),
    immutableDays: z.number().min(1).optional(),
    legalHold: z.boolean(),
    legalHoldReason: z.string().optional(),
    description: z.string().optional(),
    excludedDisks: z.array(z.string()).optional(),
  })
  .refine(
    (data) => {
      if (data.sourceType === 'vm') {
        return data.vmId !== null;
      } else {
        return data.containerId !== null;
      }
    },
    {
      message: 'Please select a source',
      path: ['vmId'],
    }
  )
  .refine(
    (data) => data.storageBackendId !== null,
    {
      message: 'Please select a storage backend',
      path: ['storageBackendId'],
    }
  )
  .refine(
    (data) => {
      if (data.immutable && !data.immutableDays) {
        return false;
      }
      return true;
    },
    {
      message: 'Immutable period (days) is required when immutability is enabled',
      path: ['immutableDays'],
    }
  )
  .refine(
    (data) => {
      if (data.legalHold && !data.legalHoldReason) {
        return false;
      }
      return true;
    },
    {
      message: 'Legal hold reason is required when legal hold is enabled',
      path: ['legalHoldReason'],
    }
  );

export type BackupWizardFormData = z.infer<typeof backupWizardSchema>;

// ============================================================================
// RESTORE WIZARD FORMS
// ============================================================================

export const restoreWizardSchema = z
  .object({
    restoreType: z.enum(['original', 'new']),
    verifyBeforeRestore: z.boolean(),
    targetKvmHostId: z.number().nullable(),
    targetPodmanHostId: z.number().nullable(),
    newName: z.string().optional(),
  })
  .refine(
    (data) => {
      if (data.restoreType === 'new' && !data.newName) {
        return false;
      }
      return true;
    },
    {
      message: 'Name is required when restoring to a new location',
      path: ['newName'],
    }
  );

export type RestoreWizardFormData = z.infer<typeof restoreWizardSchema>;
