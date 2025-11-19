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
import { useSnackbar } from 'notistack';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import api, { handleApiError } from '../services/api';
import type { Schedule, VM, Container, StorageBackend } from '../types';
import { scheduleSchema, type ScheduleFormData } from '../utils/validationSchemas';

const Schedules: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [vms, setVMs] = useState<VM[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [storageBackends, setStorageBackends] = useState<StorageBackend[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [scheduleToDelete, setScheduleToDelete] = useState<Schedule | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isValid },
  } = useForm<ScheduleFormData>({
    resolver: zodResolver(scheduleSchema),
    mode: 'onChange',
    defaultValues: {
      name: '',
      cron_expression: '0 2 * * *',
      vm_id: null,
      container_id: null,
      storage_backend_id: 1,
      retention_count: 7,
      compression_algorithm: 'gzip',
      is_active: true,
    },
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
    reset({
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
    reset({
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

  const onSubmit = async (data: ScheduleFormData) => {
    try {
      if (editingSchedule) {
        await api.put(`/schedules/${editingSchedule.id}`, data);
        enqueueSnackbar('Schedule updated successfully', { variant: 'success' });
      } else {
        await api.post('/schedules', data);
        enqueueSnackbar('Schedule created successfully', { variant: 'success' });
      }
      setDialogOpen(false);
      await fetchSchedules();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to save schedule', { variant: 'error' });
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

  const handleDeleteClick = (schedule: Schedule) => {
    setScheduleToDelete(schedule);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!scheduleToDelete) return;

    try {
      await api.delete(`/schedules/${scheduleToDelete.id}`);
      enqueueSnackbar('Schedule deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setScheduleToDelete(null);
      await fetchSchedules();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to delete schedule', { variant: 'error' });
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
                        onClick={() => handleDeleteClick(schedule)}
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
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogTitle>
            {editingSchedule ? 'Edit Schedule' : 'Add Schedule'}
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  label="Schedule Name"
                  required
                  error={!!errors.name}
                  helperText={errors.name?.message}
                  {...register('name')}
                />
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  select
                  label="Target VM"
                  defaultValue=""
                  error={!!errors.vm_id}
                  helperText={errors.vm_id?.message || 'Select VM or Container (not both)'}
                  {...register('vm_id', {
                    setValueAs: (v) => (v === '' ? null : Number(v)),
                    onChange: (e) => {
                      if (e.target.value) {
                        setValue('container_id', null);
                      }
                    },
                  })}
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
                  defaultValue=""
                  error={!!errors.container_id}
                  helperText={errors.container_id?.message || 'Select VM or Container (not both)'}
                  {...register('container_id', {
                    setValueAs: (v) => (v === '' ? null : Number(v)),
                    onChange: (e) => {
                      if (e.target.value) {
                        setValue('vm_id', null);
                      }
                    },
                  })}
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
                  defaultValue=""
                  onChange={(e) => setValue('cron_expression', e.target.value, { shouldValidate: true })}
                  helperText="Or enter custom cron expression below"
                >
                  <MenuItem value="">Custom</MenuItem>
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
                  required
                  error={!!errors.cron_expression}
                  helperText={errors.cron_expression?.message || 'Format: minute hour day month weekday'}
                  {...register('cron_expression')}
                />
              </Grid>

              <Grid size={{ xs: 12, md: 6 }}>
                <TextField
                  fullWidth
                  select
                  label="Storage Backend"
                  required
                  defaultValue={1}
                  error={!!errors.storage_backend_id}
                  helperText={errors.storage_backend_id?.message}
                  {...register('storage_backend_id', { valueAsNumber: true })}
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
                  error={!!errors.retention_count}
                  helperText={errors.retention_count?.message || 'Number of backups to keep (0 = unlimited)'}
                  {...register('retention_count', { valueAsNumber: true })}
                />
              </Grid>

              <Grid size={{ xs: 12 }}>
                <FormControlLabel
                  control={
                    <Switch
                      defaultChecked
                      {...register('is_active')}
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
              type="submit"
              variant="contained"
              disabled={!isValid}
            >
              {editingSchedule ? 'Update' : 'Create'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Schedule</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{scheduleToDelete?.name}</strong>?
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

export default Schedules;
