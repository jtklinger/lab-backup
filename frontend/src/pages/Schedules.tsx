/**
 * Schedules Management Page
 *
 * Manage automated backup schedules with cron expressions.
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
  Switch,
  FormControlLabel,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Schedule as ScheduleIcon,
  PlayArrow as EnableIcon,
  Pause as DisableIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import api, { handleApiError } from '../services/api';
import type { Schedule, VM, Container, StorageBackend } from '../types';

const Schedules: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [vms, setVMs] = useState<VM[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [storageBackends, setStorageBackends] = useState<StorageBackend[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);

  const [formData, setFormData] = useState({
    name: '',
    cron_expression: '0 2 * * *', // Daily at 2 AM
    vm_id: null as number | null,
    container_id: null as number | null,
    storage_backend_id: 1,
    retention_count: 7,
    compression_algorithm: 'gzip',
    is_active: true,
  });

  // Common cron patterns
  const cronPresets = [
    { label: 'Daily at 2 AM', value: '0 2 * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Weekly (Sunday 2 AM)', value: '0 2 * * 0' },
    { label: 'Monthly (1st at 2 AM)', value: '0 2 1 * *' },
    { label: 'Every hour', value: '0 * * * *' },
  ];

  const fetchSchedules = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<Schedule[]>('/schedules');
      setSchedules(response.data);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const fetchResources = async () => {
    try {
      const [vmsResp, containersResp, storageResp] = await Promise.all([
        api.get<VM[]>('/vms'),
        api.get<Container[]>('/containers'),
        api.get<StorageBackend[]>('/storage-backends'),
      ]);
      setVMs(vmsResp.data);
      setContainers(containersResp.data);
      setStorageBackends(storageResp.data);
    } catch (err) {
      console.error('Failed to fetch resources:', err);
    }
  };

  useEffect(() => {
    fetchSchedules();
    fetchResources();
  }, []);

  const handleAdd = () => {
    setEditingSchedule(null);
    setFormData({
      name: '',
      cron_expression: '0 2 * * *',
      vm_id: null,
      container_id: null,
      storage_backend_id: storageBackends[0]?.id || 1,
      retention_count: 7,
      compression_algorithm: 'gzip',
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (schedule: Schedule) => {
    setEditingSchedule(schedule);
    setFormData({
      name: schedule.name,
      cron_expression: schedule.cron_expression,
      vm_id: schedule.vm_id || null,
      container_id: schedule.container_id || null,
      storage_backend_id: schedule.storage_backend_id,
      retention_count: schedule.retention_count || 7,
      compression_algorithm: schedule.compression_algorithm,
      is_active: schedule.is_active,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editingSchedule) {
        await api.put(`/schedules/${editingSchedule.id}`, formData);
      } else {
        await api.post('/schedules', formData);
      }
      setDialogOpen(false);
      await fetchSchedules();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleToggle = async (id: number, currentState: boolean) => {
    try {
      await api.patch(`/schedules/${id}`, { is_active: !currentState });
      await fetchSchedules();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this schedule?')) return;

    try {
      await api.delete(`/schedules/${id}`);
      await fetchSchedules();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  if (error) {
    return (
      <Box>
        <Alert severity="error" action={
          <Button color="inherit" size="small" onClick={fetchSchedules}>
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
        <Typography variant="h4">Backup Schedules</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchSchedules}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
          >
            Add Schedule
          </Button>
        </Box>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Target</TableCell>
              <TableCell>Schedule</TableCell>
              <TableCell>Storage</TableCell>
              <TableCell>Retention</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Next Run</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <CircularProgress />
                </TableCell>
              </TableRow>
            ) : schedules.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <Box sx={{ py: 4 }}>
                    <ScheduleIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No schedules configured. Create one to automate backups.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              schedules.map((schedule) => (
                <TableRow key={schedule.id} hover>
                  <TableCell>
                    <Typography variant="body2">{schedule.name}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {schedule.vm_name || schedule.container_name || 'Unknown'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {schedule.vm_id ? 'VM' : 'Container'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontFamily="monospace">
                      {schedule.cron_expression}
                    </Typography>
                  </TableCell>
                  <TableCell>{schedule.storage_backend_name}</TableCell>
                  <TableCell>{schedule.retention_count || 'Unlimited'} backups</TableCell>
                  <TableCell>
                    <Chip
                      label={schedule.is_active ? 'Active' : 'Paused'}
                      color={schedule.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    {schedule.next_run ? formatDate(schedule.next_run) : 'N/A'}
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title={schedule.is_active ? 'Pause' : 'Enable'}>
                      <IconButton
                        size="small"
                        onClick={() => handleToggle(schedule.id, schedule.is_active)}
                      >
                        {schedule.is_active ? <DisableIcon /> : <EnableIcon />}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit">
                      <IconButton
                        size="small"
                        onClick={() => handleEdit(schedule)}
                      >
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDelete(schedule.id)}
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
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {editingSchedule ? 'Edit Schedule' : 'Add Schedule'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Schedule Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                select
                label="Target VM"
                value={formData.vm_id || ''}
                onChange={(e) => setFormData({ ...formData, vm_id: e.target.value ? Number(e.target.value) : null, container_id: null })}
                helperText="Select VM or Container (not both)"
              >
                <MenuItem value="">None</MenuItem>
                {vms.map((vm) => (
                  <MenuItem key={vm.id} value={vm.id}>
                    {vm.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                select
                label="Target Container"
                value={formData.container_id || ''}
                onChange={(e) => setFormData({ ...formData, container_id: e.target.value ? Number(e.target.value) : null, vm_id: null })}
                helperText="Select VM or Container (not both)"
              >
                <MenuItem value="">None</MenuItem>
                {containers.map((container) => (
                  <MenuItem key={container.id} value={container.id}>
                    {container.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                select
                label="Cron Preset"
                onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                helperText="Or enter custom cron expression below"
              >
                {cronPresets.map((preset) => (
                  <MenuItem key={preset.value} value={preset.value}>
                    {preset.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Cron Expression"
                value={formData.cron_expression}
                onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                helperText="Format: minute hour day month weekday"
                required
              />
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                select
                label="Storage Backend"
                value={formData.storage_backend_id}
                onChange={(e) => setFormData({ ...formData, storage_backend_id: Number(e.target.value) })}
                required
              >
                {storageBackends.map((backend) => (
                  <MenuItem key={backend.id} value={backend.id}>
                    {backend.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                type="number"
                label="Retention Count"
                value={formData.retention_count}
                onChange={(e) => setFormData({ ...formData, retention_count: Number(e.target.value) })}
                helperText="Number of backups to keep (0 = unlimited)"
              />
            </Grid>

            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                }
                label="Active"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!formData.name || !formData.cron_expression || (!formData.vm_id && !formData.container_id)}
          >
            {editingSchedule ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Schedules;
