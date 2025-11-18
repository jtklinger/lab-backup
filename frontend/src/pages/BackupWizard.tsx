/**
 * Backup Creation Wizard
 *
 * Multi-step form for creating backups with full configuration options.
 * Related: Issue #16 - React Frontend
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  ArrowBack as BackIcon,
  ArrowForward as NextIcon,
  Check as SubmitIcon,
} from '@mui/icons-material';
import api, { handleApiError } from '../services/api';
import type { VM, Container, StorageBackend } from '../types';

interface BackupFormData {
  // Step 1: Source selection
  sourceType: 'vm' | 'container';
  vmId: number | null;
  containerId: number | null;

  // Step 2: Storage backend
  storageBackendId: number | null;

  // Step 3: Backup options
  compressionAlgorithm: string;
  encryptionEnabled: boolean;
  encryptionKeyId: number | null;
  encryptionStrategy: string;
  immutable: boolean;
  immutableDays: number;
  legalHold: boolean;
  legalHoldReason: string;
  description: string;
}

const steps = ['Select Source', 'Choose Storage', 'Configure Options', 'Review & Confirm'];

const BackupWizard: React.FC = () => {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [vms, setVMs] = useState<VM[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [storageBackends, setStorageBackends] = useState<StorageBackend[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState<BackupFormData>({
    sourceType: 'vm',
    vmId: null,
    containerId: null,
    storageBackendId: null,
    compressionAlgorithm: 'gzip',
    encryptionEnabled: false,
    encryptionKeyId: null,
    encryptionStrategy: 'APP_LEVEL',
    immutable: false,
    immutableDays: 30,
    legalHold: false,
    legalHoldReason: '',
    description: '',
  });

  useEffect(() => {
    fetchResources();
  }, []);

  const fetchResources = async () => {
    try {
      setIsLoading(true);
      const [vmsResp, containersResp, storageResp] = await Promise.all([
        api.get<VM[]>('/vms'),
        api.get<Container[]>('/containers'),
        api.get<StorageBackend[]>('/storage-backends'),
      ]);
      setVMs(vmsResp.data);
      setContainers(containersResp.data);
      setStorageBackends(storageResp.data.filter(b => b.is_active));
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
      case 0: // Source selection
        if (formData.sourceType === 'vm' && !formData.vmId) {
          setError('Please select a virtual machine');
          return false;
        }
        if (formData.sourceType === 'container' && !formData.containerId) {
          setError('Please select a container');
          return false;
        }
        return true;

      case 1: // Storage selection
        if (!formData.storageBackendId) {
          setError('Please select a storage backend');
          return false;
        }
        return true;

      case 2: // Options
        if (formData.immutable && formData.immutableDays < 1) {
          setError('Immutable days must be at least 1');
          return false;
        }
        if (formData.legalHold && !formData.legalHoldReason.trim()) {
          setError('Legal hold requires a reason');
          return false;
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
        storage_backend_id: formData.storageBackendId,
        compression_algorithm: formData.compressionAlgorithm,
        description: formData.description || undefined,
      };

      // Add source
      if (formData.sourceType === 'vm') {
        payload.vm_id = formData.vmId;
      } else {
        payload.container_id = formData.containerId;
      }

      // Add encryption if enabled
      if (formData.encryptionEnabled) {
        payload.encryption_strategy = formData.encryptionStrategy;
        if (formData.encryptionKeyId) {
          payload.encryption_key_id = formData.encryptionKeyId;
        }
      }

      // Add immutability if enabled
      if (formData.immutable) {
        payload.immutable_days = formData.immutableDays;
      }

      // Add legal hold if enabled
      if (formData.legalHold) {
        payload.legal_hold_enabled = true;
        payload.legal_hold_reason = formData.legalHoldReason;
      }

      await api.post('/backups', payload);

      // Navigate to backups page
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
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
                  value={formData.sourceType}
                  onChange={(e) => setFormData({
                    ...formData,
                    sourceType: e.target.value as 'vm' | 'container',
                    vmId: null,
                    containerId: null,
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
                    value={formData.vmId || ''}
                    onChange={(e) => setFormData({ ...formData, vmId: Number(e.target.value) })}
                    helperText={vms.length === 0 ? 'No VMs available. Sync a KVM host first.' : 'Select a VM to backup'}
                  >
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
                    value={formData.containerId || ''}
                    onChange={(e) => setFormData({ ...formData, containerId: Number(e.target.value) })}
                    helperText={containers.length === 0 ? 'No containers available. Sync a Podman host first.' : 'Select a container to backup'}
                  >
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
                  value={formData.storageBackendId || ''}
                  onChange={(e) => setFormData({ ...formData, storageBackendId: Number(e.target.value) })}
                  helperText={storageBackends.length === 0 ? 'No storage backends available. Add one in Storage settings.' : 'Select destination for backup'}
                >
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
              Set compression, encryption, and retention policies.
            </Typography>

            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  select
                  label="Compression"
                  value={formData.compressionAlgorithm}
                  onChange={(e) => setFormData({ ...formData, compressionAlgorithm: e.target.value })}
                  helperText="Compression reduces backup size"
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
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  helperText="Optional description for this backup"
                  placeholder="e.g., Pre-upgrade backup"
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
                      checked={formData.encryptionEnabled}
                      onChange={(e) => setFormData({ ...formData, encryptionEnabled: e.target.checked })}
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
                    value={formData.encryptionStrategy}
                    onChange={(e) => setFormData({ ...formData, encryptionStrategy: e.target.value })}
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
                      checked={formData.immutable}
                      onChange={(e) => setFormData({ ...formData, immutable: e.target.checked })}
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
                    value={formData.immutableDays}
                    onChange={(e) => setFormData({ ...formData, immutableDays: Number(e.target.value) })}
                    helperText="Number of days backup cannot be deleted"
                    inputProps={{ min: 1 }}
                  />
                </Grid>
              )}

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.legalHold}
                      onChange={(e) => setFormData({ ...formData, legalHold: e.target.checked })}
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
                    value={formData.legalHoldReason}
                    onChange={(e) => setFormData({ ...formData, legalHoldReason: e.target.value })}
                    required
                    helperText="Reason for legal hold (required)"
                    placeholder="e.g., Pending litigation"
                  />
                </Grid>
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
                onClick={handleSubmit}
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
