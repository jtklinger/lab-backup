/**
 * Restore Wizard
 *
 * Multi-step form for restoring backups with target selection.
 * Related: Issue #16 - React Frontend
 */
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
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
  Alert,
  CircularProgress,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  Switch,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  ArrowBack as BackIcon,
  ArrowForward as NextIcon,
  RestorePage as RestoreIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useSnackbar } from 'notistack';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import api, { handleApiError } from '../services/api';
import type { Backup, KVMHost, PodmanHost } from '../types';
import { restoreWizardSchema, type RestoreWizardFormData } from '../utils/validationSchemas';

const steps = ['Restore Options', 'Select Target', 'Review & Confirm'];

const RestoreWizard: React.FC = () => {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const { backupId } = useParams<{ backupId: string }>();
  const [activeStep, setActiveStep] = useState(0);
  const [backup, setBackup] = useState<Backup | null>(null);
  const [kvmHosts, setKvmHosts] = useState<KVMHost[]>([]);
  const [podmanHosts, setPodmanHosts] = useState<PodmanHost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    trigger,
    formState: { errors },
  } = useForm<RestoreWizardFormData>({
    resolver: zodResolver(restoreWizardSchema),
    mode: 'onChange',
    defaultValues: {
      restoreType: 'original',
      verifyBeforeRestore: true,
      targetKvmHostId: null,
      targetPodmanHostId: null,
      newName: '',
    },
  });

  const formData = watch();

  useEffect(() => {
    if (backupId) {
      fetchBackupAndHosts();
    }
  }, [backupId]);

  const fetchBackupAndHosts = async () => {
    try {
      setIsLoading(true);
      const [backupResp, kvmResp, podmanResp] = await Promise.all([
        api.get<Backup>(`/backups/${backupId}`),
        api.get<KVMHost[]>('/kvm-hosts'),
        api.get<PodmanHost[]>('/podman-hosts'),
      ]);

      setBackup(backupResp.data);
      setKvmHosts(kvmResp.data.filter(h => h.is_active));
      setPodmanHosts(podmanResp.data.filter(h => h.is_active));

      // Set default new name
      const sourceName = backupResp.data.vm_name || backupResp.data.container_name || 'backup';
      setValue('newName', `${sourceName}-restored-${Date.now()}`);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

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
      case 0: // Restore options
        return ['restoreType', 'verifyBeforeRestore'];
      case 1: // Target selection
        return ['targetKvmHostId', 'targetPodmanHostId', 'newName'];
      default:
        return [];
    }
  };

  const onSubmit = async (data: RestoreWizardFormData) => {
    try {
      setIsSubmitting(true);
      setError(null);

      const payload: any = {
        backup_id: Number(backupId),
        verify_before_restore: data.verifyBeforeRestore,
      };

      if (data.restoreType === 'new') {
        payload.restore_to_new = true;
        payload.new_name = data.newName;

        if (backup?.vm_id) {
          payload.target_kvm_host_id = data.targetKvmHostId;
        } else if (backup?.container_id) {
          payload.target_podman_host_id = data.targetPodmanHostId;
        }
      }

      await api.post('/backups/restore', payload);
      enqueueSnackbar('Restore initiated successfully', { variant: 'success' });

      // Navigate back to backups page
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to initiate restore', { variant: 'error' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  const renderStepContent = (step: number) => {
    if (!backup) return null;

    switch (step) {
      case 0:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Restore Options
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Choose how you want to restore this backup.
            </Typography>

            {/* Backup Info Card */}
            <Card variant="outlined" sx={{ mb: 3 }}>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Backup Information
                </Typography>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Source
                    </Typography>
                    <Typography variant="body2">
                      {backup.vm_name || backup.container_name}
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Size
                    </Typography>
                    <Typography variant="body2">
                      {formatBytes(backup.size || 0)}
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Created
                    </Typography>
                    <Typography variant="body2">
                      {formatDate(backup.created_at)}
                    </Typography>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" color="text.secondary">
                      Compression
                    </Typography>
                    <Typography variant="body2">
                      {backup.compression_algorithm || 'None'}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  select
                  label="Restore Type"
                  defaultValue="original"
                  {...register('restoreType')}
                >
                  <MenuItem value="original">Restore to Original Location</MenuItem>
                  <MenuItem value="new">Restore to New Location</MenuItem>
                </TextField>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      defaultChecked={true}
                      {...register('verifyBeforeRestore')}
                    />
                  }
                  label="Verify backup integrity before restoring"
                />
                <Typography variant="caption" color="text.secondary" display="block">
                  Recommended to ensure backup is not corrupted
                </Typography>
              </Grid>

              {formData.restoreType === 'original' && (
                <Grid size={{ xs: 12 }}>
                  <Alert severity="warning">
                    <strong>Warning:</strong> Restoring to the original location will overwrite the existing {backup.vm_id ? 'VM' : 'container'}. Make sure this is what you want.
                  </Alert>
                </Grid>
              )}
            </Grid>
          </Box>
        );

      case 1:
        if (formData.restoreType === 'original') {
          return (
            <Box>
              <Alert severity="info">
                Backup will be restored to its original location. No additional configuration needed.
              </Alert>
            </Box>
          );
        }

        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Select Target
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Choose where to restore the backup.
            </Typography>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  label="New Name"
                  required
                  error={!!errors.newName}
                  helperText={errors.newName?.message || `Name for the restored ${backup.vm_id ? 'VM' : 'container'}`}
                  {...register('newName')}
                />
              </Grid>

              {backup.vm_id && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    select
                    label="Target KVM Host"
                    defaultValue=""
                    error={!!errors.targetKvmHostId}
                    helperText={errors.targetKvmHostId?.message || "Select the KVM host where the VM will be restored"}
                    {...register('targetKvmHostId', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
                  >
                    <MenuItem value="">Select a KVM host</MenuItem>
                    {kvmHosts.map((host) => (
                      <MenuItem key={host.id} value={host.id}>
                        {host.name} ({host.hostname})
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              )}

              {backup.container_id && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    select
                    label="Target Podman Host"
                    defaultValue=""
                    error={!!errors.targetPodmanHostId}
                    helperText={errors.targetPodmanHostId?.message || "Select the Podman host where the container will be restored"}
                    {...register('targetPodmanHostId', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
                  >
                    <MenuItem value="">Select a Podman host</MenuItem>
                    {podmanHosts.map((host) => (
                      <MenuItem key={host.id} value={host.id}>
                        {host.name} ({host.hostname})
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              )}
            </Grid>
          </Box>
        );

      case 2:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Review Restore Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              Please review the restore settings before proceeding.
            </Typography>

            <Card variant="outlined">
              <CardContent>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Backup Source
                    </Typography>
                    <Typography variant="body1">
                      <strong>{backup.vm_name || backup.container_name}</strong>
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {formatBytes(backup.size || 0)} • {formatDate(backup.created_at)}
                    </Typography>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Restore Type
                    </Typography>
                    <Chip
                      label={formData.restoreType === 'original' ? 'Original Location' : 'New Location'}
                      color={formData.restoreType === 'original' ? 'warning' : 'primary'}
                      size="small"
                    />
                  </Grid>

                  {formData.restoreType === 'new' && (
                    <>
                      <Grid size={{ xs: 12 }}>
                        <Typography variant="subtitle2" color="text.secondary">
                          New Name
                        </Typography>
                        <Typography variant="body1">
                          {formData.newName}
                        </Typography>
                      </Grid>

                      <Grid size={{ xs: 12 }}>
                        <Typography variant="subtitle2" color="text.secondary">
                          Target Host
                        </Typography>
                        <Typography variant="body1">
                          {backup.vm_id
                            ? kvmHosts.find(h => h.id === formData.targetKvmHostId)?.name
                            : podmanHosts.find(h => h.id === formData.targetPodmanHostId)?.name}
                        </Typography>
                      </Grid>
                    </>
                  )}

                  <Grid size={{ xs: 12 }}>
                    <Typography variant="subtitle2" color="text.secondary">
                      Options
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                      {formData.verifyBeforeRestore && (
                        <Chip label="Verify Before Restore" color="success" size="small" />
                      )}
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {formData.restoreType === 'original' && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                <strong>Final Warning:</strong> This will overwrite the existing resource at its original location.
              </Alert>
            )}
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

  if (!backup) {
    return (
      <Box>
        <Alert severity="error">Backup not found</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Restore Backup
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Restore backup of {backup.vm_name || backup.container_name}
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
                startIcon={isSubmitting ? <CircularProgress size={20} /> : <RestoreIcon />}
              >
                {isSubmitting ? 'Restoring...' : 'Start Restore'}
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

export default RestoreWizard;
