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
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  CheckCircle as TestIcon,
  Storage as StorageIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useSnackbar } from 'notistack';
import api, { handleApiError } from '../services/api';
import type { StorageBackend } from '../types';
import { StorageType } from '../types';

const Storage: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [backends, setBackends] = useState<StorageBackend[]>([]);
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
    threshold?: number;
  }>({
    name: '',
    type: StorageType.LOCAL,
    config: {},
    threshold: 80,
  });

  const fetchBackends = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<StorageBackend[]>('/storage');
      setBackends(response.data);
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

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
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
              <TableCell>Created</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <CircularProgress />
                </TableCell>
              </TableRow>
            ) : backends.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Box sx={{ py: 4 }}>
                    <StorageIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No storage backends configured. Add one to store backups.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              backends.map((backend) => (
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
                  <TableCell>{formatDate(backend.created_at)}</TableCell>
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
              ))
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
            <Grid size={{ xs: 12 }}>
              <Alert severity="info">
                Storage backend configuration is managed via environment variables or API.
                See documentation for details.
              </Alert>
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
