/**
 * Backups List Page
 *
 * Displays all backups with filtering, searching, and pagination.
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
  TextField,
  MenuItem,
  CircularProgress,
  Alert,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  RestorePage as RestoreIcon,
  Delete as DeleteIcon,
  Lock as LockIcon,
  Gavel as LegalHoldIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useSnackbar } from 'notistack';
import api, { handleApiError } from '../services/api';
import type { Backup, PaginatedResponse } from '../types';
import { BackupStatus } from '../types';

const Backups: React.FC = () => {
  const navigate = useNavigate();
  const { enqueueSnackbar } = useSnackbar();
  const [backups, setBackups] = useState<Backup[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [backupToDelete, setBackupToDelete] = useState<Backup | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchFilter, setSearchFilter] = useState<string>('');

  const fetchBackups = async () => {
    try {
      setIsLoading(true);
      const params: Record<string, any> = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };

      if (statusFilter) {
        params.status = statusFilter;
      }

      if (searchFilter) {
        params.search = searchFilter;
      }

      const response = await api.get<PaginatedResponse<Backup>>('/backups', { params });
      setBackups(response.data.items);
      setTotal(response.data.total);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBackups();
  }, [page, rowsPerPage, statusFilter, searchFilter]);

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchFilter(event.target.value);
    setPage(0);
  };

  const handleStatusFilterChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setStatusFilter(event.target.value);
    setPage(0);
  };

  const handleDeleteClick = (backup: Backup) => {
    setBackupToDelete(backup);
    setDeleteDialogOpen(true);
  };

  const handleDeleteCancel = () => {
    setDeleteDialogOpen(false);
    setBackupToDelete(null);
  };

  const handleDeleteConfirm = async () => {
    if (!backupToDelete) return;

    try {
      await api.delete(`/backups/${backupToDelete.id}`);
      enqueueSnackbar('Backup deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setBackupToDelete(null);
      // Refresh the list
      fetchBackups();
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const getStatusColor = (status: BackupStatus): 'success' | 'error' | 'warning' | 'info' | 'default' => {
    switch (status) {
      case BackupStatus.COMPLETED:
        return 'success';
      case BackupStatus.FAILED:
        return 'error';
      case BackupStatus.RUNNING:
        return 'info';
      case BackupStatus.PENDING:
        return 'warning';
      default:
        return 'default';
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

  if (error) {
    return (
      <Box>
        <Alert severity="error" action={
          <Button color="inherit" size="small" onClick={fetchBackups}>
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
        <Typography variant="h4">Backups</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchBackups}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => navigate('/backups/create')}
          >
            Create Backup
          </Button>
        </Box>
      </Box>

      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField
              fullWidth
              label="Search"
              placeholder="Search by VM or container name..."
              value={searchFilter}
              onChange={handleSearchChange}
              size="small"
            />
          </Grid>
          <Grid size={{ xs: 12, md: 3 }}>
            <TextField
              fullWidth
              select
              label="Status"
              value={statusFilter}
              onChange={handleStatusFilterChange}
              size="small"
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value={BackupStatus.COMPLETED}>Completed</MenuItem>
              <MenuItem value={BackupStatus.RUNNING}>Running</MenuItem>
              <MenuItem value={BackupStatus.PENDING}>Pending</MenuItem>
              <MenuItem value={BackupStatus.FAILED}>Failed</MenuItem>
            </TextField>
          </Grid>
        </Grid>
      </Paper>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Source</TableCell>
              <TableCell>Storage Backend</TableCell>
              <TableCell>Size</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
              <TableCell>Encryption</TableCell>
              <TableCell>Protection</TableCell>
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
            ) : backups.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <Typography variant="body2" color="text.secondary">
                    No backups found
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              backups.map((backup) => (
                <TableRow key={backup.id} hover>
                  <TableCell>
                    <Typography variant="body2">
                      {backup.source_name || backup.vm_name || backup.container_name || 'Unknown'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {backup.source_type === 'vm' ? 'VM' : backup.source_type === 'container' ? 'Container' : (backup.vm_id ? 'VM' : 'Container')}
                    </Typography>
                  </TableCell>
                  <TableCell>{backup.storage_backend_name}</TableCell>
                  <TableCell>{formatBytes(backup.size || 0)}</TableCell>
                  <TableCell>
                    <Chip
                      label={backup.status}
                      color={getStatusColor(backup.status)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{backup.created_at ? formatDate(backup.created_at) : backup.started_at ? formatDate(backup.started_at) : 'N/A'}</TableCell>
                  <TableCell>
                    {backup.storage_encryption_type && backup.storage_encryption_type !== 'NONE' ? (
                      <Tooltip title={backup.storage_encryption_type}>
                        <LockIcon fontSize="small" color="primary" />
                      </Tooltip>
                    ) : (
                      <Typography variant="caption" color="text.secondary">
                        None
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                      {backup.is_immutable && (
                        <Tooltip title={`Immutable until ${backup.immutable_until ? formatDate(backup.immutable_until) : 'forever'}`}>
                          <LockIcon fontSize="small" color="warning" />
                        </Tooltip>
                      )}
                      {backup.legal_hold_enabled && (
                        <Tooltip title={`Legal Hold: ${backup.legal_hold_reason || 'Active'}`}>
                          <LegalHoldIcon fontSize="small" color="error" />
                        </Tooltip>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Restore">
                      <IconButton
                        size="small"
                        onClick={() => navigate(`/backups/${backup.id}/restore`)}
                        disabled={backup.status !== BackupStatus.COMPLETED}
                      >
                        <RestoreIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDeleteClick(backup)}
                        disabled={backup.is_immutable || backup.legal_hold_enabled}
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

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
      >
        <DialogTitle>Delete Backup</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete the backup of{' '}
            <strong>
              {backupToDelete?.source_name || backupToDelete?.vm_name || backupToDelete?.container_name}
            </strong>?
            This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteCancel}>Cancel</Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Backups;
