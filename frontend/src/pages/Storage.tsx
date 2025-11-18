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
import api, { handleApiError } from '../services/api';
import type { StorageBackend } from '../types';
import { StorageType } from '../types';

const Storage: React.FC = () => {
  const [backends, setBackends] = useState<StorageBackend[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingBackend, setEditingBackend] = useState<StorageBackend | null>(null);
  const [testingBackend, setTestingBackend] = useState<number | null>(null);

  const [formData, setFormData] = useState<{
    name: string;
    type: typeof StorageType[keyof typeof StorageType];
    config: Record<string, any>;
    is_active: boolean;
  }>({
    name: '',
    type: StorageType.LOCAL,
    config: {},
    is_active: true,
  });

  const fetchBackends = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<StorageBackend[]>('/storage-backends');
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
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (backend: StorageBackend) => {
    setEditingBackend(backend);
    setFormData({
      name: backend.name,
      type: backend.type,
      config: backend.config,
      is_active: backend.is_active,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editingBackend) {
        await api.put(`/storage-backends/${editingBackend.id}`, formData);
      } else {
        await api.post('/storage-backends', formData);
      }
      setDialogOpen(false);
      await fetchBackends();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this storage backend?')) return;

    try {
      await api.delete(`/storage-backends/${id}`);
      await fetchBackends();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleTest = async (id: number) => {
    try {
      setTestingBackend(id);
      await api.post(`/storage-backends/${id}/test`);
      alert('Connection test successful!');
    } catch (err) {
      setError(handleApiError(err));
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
                      label={backend.is_active ? 'Active' : 'Inactive'}
                      color={backend.is_active ? 'success' : 'default'}
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
                        onClick={() => handleDelete(backend.id)}
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
    </Box>
  );
};

export default Storage;
