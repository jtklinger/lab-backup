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
import api, { handleApiError } from '../services/api';
import type { Backup, KVMHost, PodmanHost } from '../types';

interface RestoreFormData {
  // Step 1: Restore options
  restoreType: 'original' | 'new';
  verifyBeforeRestore: boolean;

  // Step 2: Target selection (for 'new' restore)
  targetKvmHostId: number | null;
  targetPodmanHostId: number | null;
  newName: string;
}

const steps = ['Restore Options', 'Select Target', 'Review & Confirm'];

const RestoreWizard: React.FC = () => {
  const navigate = useNavigate();
  const { backupId } = useParams<{ backupId: string }>();
  const [activeStep, setActiveStep] = useState(0);
  const [backup, setBackup] = useState<Backup | null>(null);
  const [kvmHosts, setKvmHosts] = useState<KVMHost[]>([]);
  const [podmanHosts, setPodmanHosts] = useState<PodmanHost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState<RestoreFormData>({
    restoreType: 'original',
    verifyBeforeRestore: true,
    targetKvmHostId: null,
    targetPodmanHostId: null,
    newName: '',
  });

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
      setFormData(prev => ({
        ...prev,
        newName: `${sourceName}-restored-${Date.now()}`,
      }));
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleNext = () => {
    if (validateStep(activeStep)) {
      setActiveStep((prev) => prev + 1);
      setError(null);
    }
  };

  const handleBack = () => {
    setActiveStep((prev) => prev - 1);
    setError(null);
  };

  const validateStep = (step: number): boolean => {
    switch (step) {
      case 1: // Target selection
        if (formData.restoreType === 'new') {
          if (backup?.vm_id && !formData.targetKvmHostId) {
            setError('Please select a target KVM host');
            return false;
          }
          if (backup?.container_id && !formData.targetPodmanHostId) {
            setError('Please select a target Podman host');
            return false;
          }
          if (!formData.newName.trim()) {
            setError('Please enter a name for the restored resource');
            return false;
          }
        }
        return true;

      default:
        return true;
    }
  };

  const handleSubmit = async () => {
    try {
      setIsSubmitting(true);
      setError(null);

      const payload: any = {
        backup_id: Number(backupId),
        verify_before_restore: formData.verifyBeforeRestore,
      };

      if (formData.restoreType === 'new') {
        payload.restore_to_new = true;
        payload.new_name = formData.newName;

        if (backup?.vm_id) {
          payload.target_kvm_host_id = formData.targetKvmHostId;
        } else if (backup?.container_id) {
          payload.target_podman_host_id = formData.targetPodmanHostId;
        }
      }

      await api.post('/backups/restore', payload);

      // Navigate back to backups page
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
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
                      {formatBytes(backup.size_bytes)}
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
                  value={formData.restoreType}
                  onChange={(e) => setFormData({ ...formData, restoreType: e.target.value as 'original' | 'new' })}
                >
                  <MenuItem value="original">Restore to Original Location</MenuItem>
                  <MenuItem value="new">Restore to New Location</MenuItem>
                </TextField>
              </Grid>

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.verifyBeforeRestore}
                      onChange={(e) => setFormData({ ...formData, verifyBeforeRestore: e.target.checked })}
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
                  value={formData.newName}
                  onChange={(e) => setFormData({ ...formData, newName: e.target.value })}
                  required
                  helperText={`Name for the restored ${backup.vm_id ? 'VM' : 'container'}`}
                />
              </Grid>

              {backup.vm_id && (
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    select
                    label="Target KVM Host"
                    value={formData.targetKvmHostId || ''}
                    onChange={(e) => setFormData({ ...formData, targetKvmHostId: Number(e.target.value) })}
                    helperText="Select the KVM host where the VM will be restored"
                  >
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
                    value={formData.targetPodmanHostId || ''}
                    onChange={(e) => setFormData({ ...formData, targetPodmanHostId: Number(e.target.value) })}
                    helperText="Select the Podman host where the container will be restored"
                  >
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
                      {formatBytes(backup.size_bytes)} • {formatDate(backup.created_at)}
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
                onClick={handleSubmit}
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
