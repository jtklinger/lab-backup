/**
 * VMs Management Page
 *
 * Lists virtual machines from KVM hosts with sync and backup capabilities.
 * Related: Issue #16 - React Frontend
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  TablePagination,
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
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Refresh as RefreshIcon,
  Backup as BackupIcon,
  Computer as ComputerIcon,
  Sync as SyncIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import api, { handleApiError } from '../services/api';
import type { VM, KVMHost, PaginatedResponse } from '../types';

const VMs: React.FC = () => {
  const navigate = useNavigate();
  const [vms, setVMs] = useState<VM[]>([]);
  const [hosts, setHosts] = useState<KVMHost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncingHost, setSyncingHost] = useState<number | null>(null);
  const [selectedVM, setSelectedVM] = useState<VM | null>(null);
  const [backupDialogOpen, setBackupDialogOpen] = useState(false);

  const fetchVMs = async () => {
    try {
      setIsLoading(true);
      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };

      const response = await api.get<PaginatedResponse<VM>>('/kvm/vms', { params });
      setVMs(response.data.items);
      setTotal(response.data.total);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const fetchHosts = async () => {
    try {
      const response = await api.get<KVMHost[]>('/kvm/hosts');
      setHosts(response.data);
    } catch (err) {
      console.error('Failed to fetch KVM hosts:', err);
    }
  };

  useEffect(() => {
    fetchVMs();
    fetchHosts();
  }, [page, rowsPerPage]);

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSyncHost = async (hostId: number) => {
    try {
      setSyncingHost(hostId);
      await api.post(`/kvm/hosts/${hostId}/refresh`);
      await fetchVMs();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSyncingHost(null);
    }
  };

  const handleBackupVM = (vm: VM) => {
    // Navigate to backup wizard with pre-selected VM
    navigate('/backups/create', { state: { sourceType: 'vm', vmId: vm.id } });
  };

  const handleCreateBackup = async () => {
    if (!selectedVM) return;

    try {
      await api.post('/backups/trigger', {
        source_type: 'vm',
        source_id: selectedVM.id,
        backup_mode: 'full',
        storage_backend_id: 1, // TODO: Allow selection
        encryption_enabled: false,
      });
      setBackupDialogOpen(false);
      setSelectedVM(null);
      // Navigate to backups page
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const getStateColor = (state?: string): 'success' | 'error' | 'warning' | 'default' => {
    if (!state) return 'default';
    if (state.toLowerCase().includes('running')) return 'success';
    if (state.toLowerCase().includes('stopped') || state.toLowerCase().includes('shut')) return 'error';
    if (state.toLowerCase().includes('paused')) return 'warning';
    return 'default';
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  if (error) {
    return (
      <Box>
        <Alert severity="error" action={
          <Button color="inherit" size="small" onClick={fetchVMs}>
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
        <Typography variant="h4">Virtual Machines</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchVMs}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {/* KVM Hosts Overview */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          KVM Hosts
        </Typography>
        <Grid container spacing={2}>
          {hosts.map((host) => (
            <Grid key={host.id} size={{ xs: 12, md: 6, lg: 4 }}>
              <Box
                sx={{
                  p: 2,
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Box>
                  <Typography variant="subtitle1">{host.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {host.hostname}:{host.port}
                  </Typography>
                  <Chip
                    label={host.is_active ? 'Active' : 'Inactive'}
                    color={host.is_active ? 'success' : 'default'}
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={syncingHost === host.id ? <CircularProgress size={16} /> : <SyncIcon />}
                  onClick={() => handleSyncHost(host.id)}
                  disabled={syncingHost === host.id}
                >
                  Sync
                </Button>
              </Box>
            </Grid>
          ))}
          {hosts.length === 0 && (
            <Grid size={{ xs: 12 }}>
              <Alert severity="info">
                No KVM hosts configured. Add a KVM host in the Admin panel to discover VMs.
              </Alert>
            </Grid>
          )}
        </Grid>
      </Paper>

      {/* VMs Table */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>KVM Host</TableCell>
              <TableCell>State</TableCell>
              <TableCell>Last Updated</TableCell>
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
            ) : vms.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Box sx={{ py: 4 }}>
                    <ComputerIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No virtual machines found. Sync a KVM host to discover VMs.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              vms.map((vm) => (
                <TableRow key={vm.id} hover>
                  <TableCell>
                    <Typography variant="body2">{vm.name}</Typography>
                  </TableCell>
                  <TableCell>{vm.kvm_host_name}</TableCell>
                  <TableCell>
                    <Chip
                      label={vm.state || 'Unknown'}
                      color={getStateColor(vm.state)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{formatDate(vm.updated_at)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Create Backup">
                      <IconButton
                        size="small"
                        onClick={() => handleBackupVM(vm)}
                      >
                        <BackupIcon />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={total}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
        />
      </TableContainer>

      {/* Backup Confirmation Dialog */}
      <Dialog open={backupDialogOpen} onClose={() => setBackupDialogOpen(false)}>
        <DialogTitle>Create Backup</DialogTitle>
        <DialogContent>
          <Typography>
            Create a backup of <strong>{selectedVM?.name}</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            This will start a backup job that you can monitor in the Backups page.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBackupDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateBackup} variant="contained">
            Create Backup
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default VMs;
