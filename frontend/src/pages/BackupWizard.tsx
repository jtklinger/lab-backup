/**
 * Backup Creation Wizard
 *
 * Multi-step form for creating backups with full configuration options.
 * Related: Issue #16 - React Frontend
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Stepper,
  Step,
  StepLabel,
  Paper,
  TextField,
  MenuItem,
  FormControlLabel,
  Switch,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  Chip,
  Divider,
  Checkbox,
  FormGroup,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  ArrowBack as BackIcon,
  ArrowForward as NextIcon,
  Check as SubmitIcon,
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import api, { handleApiError } from '../services/api';
import type { VM, Container, StorageBackend } from '../types';
import { backupWizardSchema, type BackupWizardFormData } from '../utils/validationSchemas';

const steps = ['Select Source', 'Choose Storage', 'Configure Options', 'Review & Confirm'];

const BackupWizard: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { enqueueSnackbar } = useSnackbar();
  const [activeStep, setActiveStep] = useState(0);
  const [vms, setVMs] = useState<VM[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [storageBackends, setStorageBackends] = useState<StorageBackend[]>([]);
  const [vmDisks, setVmDisks] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDisks, setIsLoadingDisks] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    trigger,
    formState: { errors },
  } = useForm<BackupWizardFormData>({
    resolver: zodResolver(backupWizardSchema),
    mode: 'onChange',
    defaultValues: {
      sourceType: 'vm',
      vmId: null,
      containerId: null,
      storageBackendId: null,
      backupMode: 'full',
      retentionDays: 30,
      compressionAlgorithm: 'gzip',
      encryptionEnabled: false,
      encryptionKeyId: null,
      encryptionStrategy: 'APP_LEVEL',
      immutable: false,
      immutableDays: 30,
      legalHold: false,
      legalHoldReason: '',
      description: '',
      excludedDisks: [],
    },
  });

  const formData = watch();

  useEffect(() => {
    fetchResources();
  }, []);

  // Pre-fill form if navigated from VMs page
  useEffect(() => {
    const state = location.state as any;
    if (state?.sourceType && state?.vmId) {
      setValue('sourceType', state.sourceType);
      setValue('vmId', state.vmId);
    }
  }, [location.state, setValue]);

  const fetchResources = async () => {
    try {
      setIsLoading(true);
      const [vmsResp, containersResp, storageResp] = await Promise.all([
        api.get<any>('/kvm/vms'),
        api.get<any>('/podman/containers'),
        api.get<StorageBackend[]>('/storage'),
      ]);

      // Handle paginated VMs response
      const vmsData = vmsResp.data?.items || vmsResp.data;
      setVMs(Array.isArray(vmsData) ? vmsData : []);

      // Handle paginated containers response
      const containersData = containersResp.data?.items || containersResp.data;
      setContainers(Array.isArray(containersData) ? containersData : []);

      // Storage is a direct array
      setStorageBackends(Array.isArray(storageResp.data) ? storageResp.data.filter(b => b.enabled) : []);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const fetchVMDisks = async (vmId: number) => {
    try {
      setIsLoadingDisks(true);
      const response = await api.get(`/kvm/vms/${vmId}`);
      const vm = response.data;
      // Extract disk information from VM details
      if (vm.disks && Array.isArray(vm.disks)) {
        setVmDisks(vm.disks);
      } else {
        setVmDisks([]);
      }
    } catch (err) {
      console.error('Failed to fetch VM disks:', err);
      setVmDisks([]);
    } finally {
      setIsLoadingDisks(false);
    }
  };

  // Fetch disks when VM is selected and we're on the options step
  useEffect(() => {
    if (formData.sourceType === 'vm' && formData.vmId && activeStep === 2) {
      fetchVMDisks(formData.vmId);
    } else {
      setVmDisks([]);
    }
  }, [formData.vmId, formData.sourceType, activeStep]);

  const handleNext = async () => {
    // Trigger validation for current step fields
    const fieldsToValidate = getStepFields(activeStep);
    const isValid = await trigger(fieldsToValidate as any);

    if (isValid) {
      setActiveStep((prev) => prev + 1);
      setError(null);
    } else {
      setError('Please fix the errors before continuing');
    }
  };

  const handleBack = () => {
    setActiveStep((prev) => prev - 1);
    setError(null);
  };

  const getStepFields = (step: number): string[] => {
    switch (step) {
      case 0: // Source selection
        return ['sourceType', 'vmId', 'containerId'];
      case 1: // Storage selection
        return ['storageBackendId'];
      case 2: // Options
        return ['backupMode', 'retentionDays', 'compressionAlgorithm', 'immutableDays', 'legalHoldReason'];
      default:
        return [];
    }
  };

  const onSubmit = async (data: BackupWizardFormData) => {
    try {
      setIsSubmitting(true);
      setError(null);

      // Build API payload with correct parameter names
      const payload: any = {
        source_type: data.sourceType,
        source_id: data.sourceType === 'vm' ? data.vmId : data.containerId,
        backup_mode: data.backupMode,
        storage_backend_id: data.storageBackendId,
        encryption_enabled: data.encryptionEnabled,
        retention_days: data.retentionDays,
      };

      // Add optional fields
      if (data.description) {
        payload.description = data.description;
      }

      if (data.encryptionEnabled && data.encryptionKeyId) {
        payload.encryption_key_id = data.encryptionKeyId;
      }

      if (data.immutable && data.immutableDays) {
        payload.immutable_days = data.immutableDays;
      }

      if (data.legalHold) {
        payload.legal_hold_enabled = true;
        payload.legal_hold_reason = data.legalHoldReason;
      }

      if (data.excludedDisks && data.excludedDisks.length > 0) {
        payload.excluded_disks = data.excludedDisks;
      }

      await api.post('/backups/trigger', payload);
      enqueueSnackbar('Backup created successfully', { variant: 'success' });

      // Navigate to backups page
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to create backup', { variant: 'error' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSelectedSource = () => {
    if (formData.sourceType === 'vm' && formData.vmId) {
      return vms.find(v => v.id === formData.vmId);
    }
    if (formData.sourceType === 'container' && formData.containerId) {
      return containers.find(c => c.id === formData.containerId);
    }
    return null;
  };

  const getSelectedStorage = () => {
    return storageBackends.find(s => s.id === formData.storageBackendId);
  };

  const renderStepContent = (step: number) => {
    switch (step) {
      case 0:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Select Backup Source
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Choose whether to backup a virtual machine or container.
            </Typography>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  select
                  label="Source Type"
                  defaultValue="vm"
                  {...register('sourceType', {
                    onChange: () => {
                      setValue('vmId', null);
                      setValue('containerId', null);
                    },
                  })}
                >
                  <MenuItem value="vm">Virtual Machine</MenuItem>
                  <MenuItem value="container">Container</MenuItem>
                </TextField>
              </Grid>

              {formData.sourceType === 'vm' && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    select
                    label="Virtual Machine"
                    required
                    defaultValue=""
                    error={!!errors.vmId}
                    helperText={errors.vmId?.message || (vms.length === 0 ? 'No VMs available. Sync a KVM host first.' : 'Select a VM to backup')}
                    {...register('vmId', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
                  >
                    <MenuItem value="">Select a VM</MenuItem>
                    {vms.map((vm) => (
                      <MenuItem key={vm.id} value={vm.id}>
                        {vm.name} ({vm.kvm_host_name})
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              )}

              {formData.sourceType === 'container' && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    select
                    label="Container"
                    required
                    defaultValue=""
                    error={!!errors.containerId}
                    helperText={errors.containerId?.message || (containers.length === 0 ? 'No containers available. Sync a Podman host first.' : 'Select a container to backup')}
                    {...register('containerId', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
                  >
                    <MenuItem value="">Select a container</MenuItem>
                    {containers.map((container) => (
                      <MenuItem key={container.id} value={container.id}>
                        {container.name} ({container.podman_host_name})
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              )}
            </Grid>
          </Box>
        );

      case 1:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Choose Storage Backend
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Select where to store the backup.
            </Typography>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  select
                  label="Storage Backend"
                  required
                  defaultValue=""
                  error={!!errors.storageBackendId}
                  helperText={errors.storageBackendId?.message || (storageBackends.length === 0 ? 'No storage backends available. Add one in Storage settings.' : 'Select destination for backup')}
                  {...register('storageBackendId', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
                >
                  <MenuItem value="">Select a storage backend</MenuItem>
                  {storageBackends.map((backend) => (
                    <MenuItem key={backend.id} value={backend.id}>
                      {backend.name} ({backend.type})
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
            </Grid>
          </Box>
        );

      case 2:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Configure Backup Options
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Set backup type, compression, encryption, and retention policies.
            </Typography>

            <Grid container spacing={3}>
              {/* Backup Mode Selection */}
              <Grid size={{ xs: 12 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Backup Type
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  select
                  label="Backup Mode"
                  defaultValue="full"
                  error={!!errors.backupMode}
                  helperText={errors.backupMode?.message || "Full backup includes all data, incremental only changes since last backup"}
                  {...register('backupMode')}
                >
                  <MenuItem value="full">Full Backup</MenuItem>
                  <MenuItem value="incremental">Incremental Backup</MenuItem>
                </TextField>
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  type="number"
                  label="Retention Period (Days)"
                  defaultValue={30}
                  error={!!errors.retentionDays}
                  helperText={errors.retentionDays?.message || "Number of days to keep this backup"}
                  inputProps={{ min: 1, max: 3650 }}
                  {...register('retentionDays', { valueAsNumber: true })}
                />
              </Grid>

              <Grid size={{ xs: 12 }}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" gutterBottom>
                  Compression & Description
                </Typography>
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  select
                  label="Compression"
                  defaultValue="gzip"
                  error={!!errors.compressionAlgorithm}
                  helperText={errors.compressionAlgorithm?.message || "Compression reduces backup size"}
                  {...register('compressionAlgorithm')}
                >
                  <MenuItem value="gzip">GZIP (Recommended)</MenuItem>
                  <MenuItem value="bzip2">BZIP2 (Better compression)</MenuItem>
                  <MenuItem value="xz">XZ (Best compression)</MenuItem>
                  <MenuItem value="none">None (Faster but larger)</MenuItem>
                </TextField>
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  label="Description"
                  error={!!errors.description}
                  helperText={errors.description?.message || "Optional description for this backup"}
                  placeholder="e.g., Pre-upgrade backup"
                  {...register('description')}
                />
              </Grid>

              <Grid size={{ xs: 12 }}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" gutterBottom>
                  Security & Retention
                </Typography>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      defaultChecked={false}
                      {...register('encryptionEnabled')}
                    />
                  }
                  label="Enable Encryption"
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  Encrypt backup data for security
                </Typography>
              </Grid>

              {formData.encryptionEnabled && (
                <Grid size={{ xs: 12, md: 6 }}>
                  <TextField
                    fullWidth
                    select
                    label="Encryption Strategy"
                    defaultValue="APP_LEVEL"
                    {...register('encryptionStrategy')}
                  >
                    <MenuItem value="APP_LEVEL">Application Level</MenuItem>
                    <MenuItem value="STORAGE_NATIVE">Storage Native (S3 SSE)</MenuItem>
                  </TextField>
                </Grid>
              )}

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      defaultChecked={false}
                      {...register('immutable')}
                    />
                  }
                  label="Make Immutable"
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  Prevent deletion for compliance
                </Typography>
              </Grid>

              {formData.immutable && (
                <Grid size={{ xs: 12, md: 6 }}>
                  <TextField
                    fullWidth
                    type="number"
                    label="Immutable Days"
                    required
                    error={!!errors.immutableDays}
                    helperText={errors.immutableDays?.message || "Number of days backup cannot be deleted"}
                    inputProps={{ min: 1 }}
                    {...register('immutableDays', { valueAsNumber: true })}
                  />
                </Grid>
              )}

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      defaultChecked={false}
                      {...register('legalHold')}
                    />
                  }
                  label="Legal Hold"
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  Place legal hold on backup (prevents deletion)
                </Typography>
              </Grid>

              {formData.legalHold && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Legal Hold Reason"
                    required
                    error={!!errors.legalHoldReason}
                    helperText={errors.legalHoldReason?.message || "Reason for legal hold (required)"}
                    placeholder="e.g., Pending litigation"
                    {...register('legalHoldReason')}
                  />
                </Grid>
              )}

              {/* Disk Selection for VMs */}
              {formData.sourceType === 'vm' && (
                <>
                  <Grid size={{ xs: 12 }}>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="subtitle2" gutterBottom>
                      Disk Selection
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Select which disks to include in the backup. All disks are included by default.
                    </Typography>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    {isLoadingDisks ? (
                      <Box display="flex" alignItems="center" gap={1}>
                        <CircularProgress size={20} />
                        <Typography variant="body2">Loading disk information...</Typography>
                      </Box>
                    ) : vmDisks.length > 0 ? (
                      <FormGroup>
                        {vmDisks.map((disk: any, index: number) => {
                          const diskId = disk.target || disk.path || `disk-${index}`;
                          const isExcluded = formData.excludedDisks?.includes(diskId);

                          return (
                            <FormControlLabel
                              key={diskId}
                              control={
                                <Checkbox
                                  checked={!isExcluded}
                                  onChange={(e) => {
                                    const currentExcluded = formData.excludedDisks || [];
                                    if (e.target.checked) {
                                      // Remove from excluded list
                                      setValue('excludedDisks', currentExcluded.filter((d: string) => d !== diskId));
                                    } else {
                                      // Add to excluded list
                                      setValue('excludedDisks', [...currentExcluded, diskId]);
                                    }
                                  }}
                                />
                              }
                              label={
                                <Box>
                                  <Typography variant="body2">
                                    {disk.target || disk.path || `Disk ${index + 1}`}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {disk.type || 'Unknown type'}
                                    {disk.size && ` • ${(disk.size / 1024 / 1024 / 1024).toFixed(2)} GB`}
                                    {disk.protocol === 'rbd' && disk.rbd_pool && ` • RBD Pool: ${disk.rbd_pool}`}
                                  </Typography>
                                </Box>
                              }
                            />
                          );
                        })}
                      </FormGroup>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        No disk information available for this VM
                      </Typography>
                    )}
                  </Grid>
                </>
              )}
            </Grid>
          </Box>
        );

      case 3:
        const source = getSelectedSource();
        const storage = getSelectedStorage();

        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Review Backup Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Please review your backup settings before creating.
            </Typography>

            <Card variant="outlined">
              <CardContent>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Source
                    </Typography>
                    <Typography variant="body1">
                      {formData.sourceType === 'vm' ? 'Virtual Machine' : 'Container'}:{' '}
                      <strong>{source?.name || 'Unknown'}</strong>
                    </Typography>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Storage Backend
                    </Typography>
                    <Typography variant="body1">
                      <strong>{storage?.name}</strong> ({storage?.type})
                    </Typography>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Compression
                    </Typography>
                    <Typography variant="body1">
                      {formData.compressionAlgorithm.toUpperCase()}
                    </Typography>
                  </Grid>

                  {formData.description && (
                    <Grid size={{ xs: 12 }}>
                      <Typography variant="subtitle2" color="text.secondary">
                        Description
                      </Typography>
                      <Typography variant="body1">
                        {formData.description}
                      </Typography>
                    </Grid>
                  )}

                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Security & Retention
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                      {formData.encryptionEnabled && (
                        <Chip label={`Encrypted (${formData.encryptionStrategy})`} color="primary" size="small" />
                      )}
                      {formData.immutable && (
                        <Chip label={`Immutable (${formData.immutableDays} days)`} color="warning" size="small" />
                      )}
                      {formData.legalHold && (
                        <Chip label="Legal Hold" color="error" size="small" />
                      )}
                      {!formData.encryptionEnabled && !formData.immutable && !formData.legalHold && (
                        <Typography variant="body2" color="text.secondary">
                          No additional security features enabled
                        </Typography>
                      )}
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>
        );

      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Create Backup
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Follow the steps to configure and create a new backup.
      </Typography>

      <Paper sx={{ p: 3, mt: 3 }}>
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        <Box sx={{ minHeight: 400 }}>
          {renderStepContent(activeStep)}
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
          <Button
            onClick={() => navigate('/backups')}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Box>
            <Button
              disabled={activeStep === 0 || isSubmitting}
              onClick={handleBack}
              startIcon={<BackIcon />}
              sx={{ mr: 1 }}
            >
              Back
            </Button>
            {activeStep === steps.length - 1 ? (
              <Button
                variant="contained"
                onClick={handleSubmit(onSubmit)}
                disabled={isSubmitting}
                startIcon={isSubmitting ? <CircularProgress size={20} /> : <SubmitIcon />}
              >
                {isSubmitting ? 'Creating...' : 'Create Backup'}
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={handleNext}
                endIcon={<NextIcon />}
              >
                Next
              </Button>
            )}
          </Box>
        </Box>
      </Paper>
    </Box>
  );
};

export default BackupWizard;
