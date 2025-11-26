/**
 * Storage Backends Management Page
 *
 * Manage storage backends (Local, S3, SMB) for backups.
 * Related: Issue #16 - React Frontend
 */
import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  CircularProgress,
  Alert,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  LinearProgress,
  Slider,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  CheckCircle as TestIcon,
  Storage as StorageIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import api, { handleApiError } from '../services/api';
import type { StorageBackend, StorageUsage } from '../types';
import { StorageType } from '../types';

const Storage: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [backends, setBackends] = useState<StorageBackend[]>([]);
  const [usageMap, setUsageMap] = useState<Record<number, StorageUsage>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingBackend, setEditingBackend] = useState<StorageBackend | null>(null);
  const [testingBackend, setTestingBackend] = useState<number | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [backendToDelete, setBackendToDelete] = useState<StorageBackend | null>(null);

  const [formData, setFormData] = useState<{
    name: string;
    type: typeof StorageType[keyof typeof StorageType];
    config: Record<string, any>;
    threshold: number;
    quota_gb: number | null;
    enabled: boolean;
  }>({
    name: '',
    type: StorageType.LOCAL,
    config: {},
    threshold: 80,
    quota_gb: null,
    enabled: true,
  });

  const fetchBackends = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<StorageBackend[]>('/storage');
      setBackends(response.data);

      // Fetch usage for each backend
      const usagePromises = response.data.map(async (backend) => {
        try {
          const usageRes = await api.get<StorageUsage>(`/storage/${backend.id}/usage`);
          return { id: backend.id, usage: usageRes.data };
        } catch {
          return null;
        }
      });

      const usageResults = await Promise.all(usagePromises);
      const newUsageMap: Record<number, StorageUsage> = {};
      usageResults.forEach((result) => {
        if (result) {
          newUsageMap[result.id] = result.usage;
        }
      });
      setUsageMap(newUsageMap);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBackends();
  }, []);

  const handleAdd = () => {
    setEditingBackend(null);
    setFormData({
      name: '',
      type: StorageType.LOCAL,
      config: {},
      threshold: 80,
      quota_gb: null,
      enabled: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (backend: StorageBackend) => {
    setEditingBackend(backend);
    setFormData({
      name: backend.name,
      type: backend.type,
      config: backend.config,
      threshold: backend.threshold,
      quota_gb: backend.quota_gb ?? null,
      enabled: backend.enabled,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editingBackend) {
        await api.put(`/storage/${editingBackend.id}`, formData);
      } else {
        await api.post('/storage', formData);
      }
      setDialogOpen(false);
      await fetchBackends();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDeleteClick = (backend: StorageBackend) => {
    setBackendToDelete(backend);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!backendToDelete) return;

    try {
      await api.delete(`/storage/${backendToDelete.id}`);
      enqueueSnackbar('Storage backend deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setBackendToDelete(null);
      await fetchBackends();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to delete storage backend', { variant: 'error' });
    }
  };

  const handleTest = async (id: number) => {
    try {
      setTestingBackend(id);
      await api.post(`/storage/${id}/test`);
      enqueueSnackbar('Connection test successful!', { variant: 'success' });
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Connection test failed', { variant: 'error' });
    } finally {
      setTestingBackend(null);
    }
  };

  const getTypeColor = (type: string): 'primary' | 'secondary' | 'success' => {
    switch (type) {
      case StorageType.S3:
        return 'primary';
      case StorageType.SMB:
        return 'secondary';
      default:
        return 'success';
    }
  };

  const getCapacityColor = (usedPercent: number, threshold: number): string => {
    if (usedPercent >= 95) return '#d32f2f'; // Red - critical
    if (usedPercent >= threshold) return '#ff9800'; // Orange - warning
    if (usedPercent >= 70) return '#ffb74d'; // Light orange - approaching
    return '#4caf50'; // Green - healthy
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 GB';
    const gb = bytes / (1024 ** 3);
    if (gb >= 1000) {
      return `${(gb / 1024).toFixed(2)} TB`;
    }
    return `${gb.toFixed(2)} GB`;
  };

  if (error) {
    return (
      <Box>
        <Alert severity="error" action={
          <Button color="inherit" size="small" onClick={fetchBackends}>
            Retry
          </Button>
        }>
          {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Storage Backends</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchBackends}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
          >
            Add Storage
          </Button>
        </Box>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell sx={{ minWidth: 200 }}>Capacity</TableCell>
              <TableCell>Threshold</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <CircularProgress />
                </TableCell>
              </TableRow>
            ) : backends.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Box sx={{ py: 4 }}>
                    <StorageIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No storage backends configured. Add one to store backups.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              backends.map((backend) => {
                const usage = usageMap[backend.id];
                const usedPercent = usage?.used_percent ?? 0;
                const hasCapacity = usage && usage.capacity > 0;

                return (
                  <TableRow key={backend.id} hover>
                    <TableCell>
                      <Typography variant="body2">{backend.name}</Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={backend.type}
                        color={getTypeColor(backend.type)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={backend.enabled ? 'Active' : 'Inactive'}
                        color={backend.enabled ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      {hasCapacity ? (
                        <Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <Box sx={{ flexGrow: 1 }}>
                              <LinearProgress
                                variant="determinate"
                                value={Math.min(usedPercent, 100)}
                                sx={{
                                  height: 10,
                                  borderRadius: 5,
                                  backgroundColor: '#e0e0e0',
                                  '& .MuiLinearProgress-bar': {
                                    backgroundColor: getCapacityColor(usedPercent, backend.threshold),
                                    borderRadius: 5,
                                  },
                                }}
                              />
                            </Box>
                            <Typography variant="body2" sx={{ minWidth: 45, fontWeight: 500 }}>
                              {usedPercent.toFixed(0)}%
                            </Typography>
                            {usage.threshold_exceeded && (
                              <Tooltip title="Threshold exceeded">
                                <WarningIcon color="warning" fontSize="small" />
                              </Tooltip>
                            )}
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            {formatBytes(usage.used)} / {formatBytes(usage.capacity)}
                          </Typography>
                        </Box>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          {backend.quota_gb ? `Quota: ${backend.quota_gb} GB` : 'No quota set'}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={`${backend.threshold}%`}
                        size="small"
                        color={usage?.threshold_exceeded ? 'warning' : 'default'}
                        variant={usage?.threshold_exceeded ? 'filled' : 'outlined'}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Test Connection">
                        <IconButton
                          size="small"
                          onClick={() => handleTest(backend.id)}
                          disabled={testingBackend === backend.id}
                        >
                          {testingBackend === backend.id ? (
                            <CircularProgress size={20} />
                          ) : (
                            <TestIcon />
                          )}
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Edit">
                        <IconButton
                          size="small"
                          onClick={() => handleEdit(backend)}
                        >
                          <EditIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleDeleteClick(backend)}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingBackend ? 'Edit Storage Backend' : 'Add Storage Backend'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                select
                label="Type"
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value as typeof StorageType[keyof typeof StorageType] })}
                required
              >
                <MenuItem value={StorageType.LOCAL}>Local Storage</MenuItem>
                <MenuItem value={StorageType.S3}>Amazon S3</MenuItem>
                <MenuItem value={StorageType.SMB}>SMB/CIFS</MenuItem>
              </TextField>
            </Grid>
            {/* SMB Configuration Fields */}
            {formData.type === StorageType.SMB && (
              <>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Server"
                    value={formData.config.server || ''}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, server: e.target.value } })}
                    required
                    helperText="SMB server hostname or IP address"
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Share Name"
                    value={formData.config.share || ''}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, share: e.target.value } })}
                    required
                    helperText="SMB share name (e.g., backups)"
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Username"
                    value={formData.config.username || ''}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, username: e.target.value } })}
                    required
                    helperText="SMB username for authentication"
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    type="password"
                    label="Password"
                    value={formData.config.password || ''}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, password: e.target.value } })}
                    required
                    helperText="SMB password for authentication"
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Domain (Optional)"
                    value={formData.config.domain || ''}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, domain: e.target.value } })}
                    helperText="Windows domain (default: WORKGROUP)"
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    fullWidth
                    label="Base Path (Optional)"
                    value={formData.config.path || '/'}
                    onChange={(e) => setFormData({ ...formData, config: { ...formData.config, path: e.target.value } })}
                    helperText="Base path within the share (default: /)"
                  />
                </Grid>
              </>
            )}
            {/* For other storage types show the placeholder */}
            {formData.type !== StorageType.SMB && (
              <Grid size={{ xs: 12 }}>
                <Alert severity="info">
                  {formData.type === StorageType.LOCAL && 'Local storage uses the default backup directory configured in settings.'}
                  {formData.type === StorageType.S3 && 'S3 storage configuration will be available in a future update.'}
                </Alert>
              </Grid>
            )}

            {/* Storage Quota Section */}
            <Grid size={{ xs: 12 }}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 1 }}>
                Capacity & Alerts
              </Typography>
            </Grid>

            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                fullWidth
                type="number"
                label="Storage Quota (GB)"
                value={formData.quota_gb ?? ''}
                onChange={(e) => setFormData({
                  ...formData,
                  quota_gb: e.target.value ? parseInt(e.target.value, 10) : null
                })}
                inputProps={{ min: 0 }}
                helperText={formData.type === StorageType.LOCAL
                  ? 'Optional - Local storage auto-detects capacity'
                  : 'Set capacity limit for usage tracking (required for S3/SMB)'}
              />
            </Grid>

            <Grid size={{ xs: 12, sm: 6 }}>
              <Typography variant="body2" gutterBottom>
                Alert Threshold: {formData.threshold}%
              </Typography>
              <Slider
                value={formData.threshold}
                onChange={(_, value) => setFormData({ ...formData, threshold: value as number })}
                min={50}
                max={99}
                step={5}
                marks={[
                  { value: 50, label: '50%' },
                  { value: 80, label: '80%' },
                  { value: 99, label: '99%' },
                ]}
                valueLabelDisplay="auto"
              />
              <Typography variant="caption" color="text.secondary">
                Alert when storage exceeds this percentage
              </Typography>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSubmit} variant="contained" disabled={!formData.name}>
            {editingBackend ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Storage Backend</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{backendToDelete?.name}</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Storage;
