/**
 * Containers Management Page
 *
 * Lists containers from Podman hosts with sync and backup capabilities.
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
  ViewInAr as ContainerIcon,
  Sync as SyncIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import api, { handleApiError } from '../services/api';
import type { Container, PodmanHost, PaginatedResponse } from '../types';

const Containers: React.FC = () => {
  const navigate = useNavigate();
  const [containers, setContainers] = useState<Container[]>([]);
  const [hosts, setHosts] = useState<PodmanHost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncingHost, setSyncingHost] = useState<number | null>(null);
  const [selectedContainer, setSelectedContainer] = useState<Container | null>(null);
  const [backupDialogOpen, setBackupDialogOpen] = useState(false);

  const fetchContainers = async () => {
    try {
      setIsLoading(true);
      const params = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };

      const response = await api.get<PaginatedResponse<Container>>('/podman/containers', { params });
      setContainers(response.data.items);
      setTotal(response.data.total);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  const fetchHosts = async () => {
    try {
      const response = await api.get<PodmanHost[]>('/podman/hosts');
      setHosts(response.data);
    } catch (err) {
      console.error('Failed to fetch Podman hosts:', err);
    }
  };

  useEffect(() => {
    fetchContainers();
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
      await api.post(`/podman-hosts/${hostId}/sync`);
      await fetchContainers();
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setSyncingHost(null);
    }
  };

  const handleBackupContainer = (container: Container) => {
    setSelectedContainer(container);
    setBackupDialogOpen(true);
  };

  const handleCreateBackup = async () => {
    if (!selectedContainer) return;

    try {
      await api.post('/backups/trigger', {
        source_type: 'container',
        source_id: selectedContainer.id,
        backup_mode: 'full',
        storage_backend_id: 1, // TODO: Allow selection
        encryption_enabled: false,
      });
      setBackupDialogOpen(false);
      setSelectedContainer(null);
      navigate('/backups');
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const getStateColor = (state?: string): 'success' | 'error' | 'warning' | 'default' => {
    if (!state) return 'default';
    if (state.toLowerCase().includes('running') || state.toLowerCase().includes('up')) return 'success';
    if (state.toLowerCase().includes('stopped') || state.toLowerCase().includes('exited')) return 'error';
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
          <Button color="inherit" size="small" onClick={fetchContainers}>
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
        <Typography variant="h4">Containers</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchContainers}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {/* Podman Hosts Overview */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          Podman Hosts
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
                No Podman hosts configured. Add a Podman host in the Admin panel to discover containers.
              </Alert>
            </Grid>
          )}
        </Grid>
      </Paper>

      {/* Containers Table */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Podman Host</TableCell>
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
            ) : containers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Box sx={{ py: 4 }}>
                    <ContainerIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No containers found. Sync a Podman host to discover containers.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              containers.map((container) => (
                <TableRow key={container.id} hover>
                  <TableCell>
                    <Typography variant="body2">{container.name}</Typography>
                  </TableCell>
                  <TableCell>{container.podman_host_name}</TableCell>
                  <TableCell>
                    <Chip
                      label={container.state || 'Unknown'}
                      color={getStateColor(container.state)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{formatDate(container.updated_at)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Create Backup">
                      <IconButton
                        size="small"
                        onClick={() => handleBackupContainer(container)}
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
            Create a backup of container <strong>{selectedContainer?.name}</strong>?
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

export default Containers;
