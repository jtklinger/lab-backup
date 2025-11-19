/**
 * Admin Panel
 *
 * Comprehensive admin interface for user management, host configuration, and audit logs.
 * Related: Issue #16 - React Frontend
 */
import React, { useState, useEffect } from 'react';
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
  TextField,
  MenuItem,
  Tabs,
  Tab,
  FormControlLabel,
  Switch,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Person as PersonIcon,
  Computer as ComputerIcon,
  History as HistoryIcon,
  CheckCircle as TestIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { useSnackbar } from 'notistack';
import api, { handleApiError } from '../services/api';
import type { User, KVMHost, PodmanHost, AuditLog, PaginatedResponse } from '../types';
import { UserRole, KVMAuthType, AuditSeverity } from '../types';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => {
  return (
    <div role="tabpanel" hidden={value !== index}>
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
};

const Admin: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Admin Panel
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Manage users, hosts, and view audit logs
      </Typography>

      <Paper>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="Users" icon={<PersonIcon />} iconPosition="start" />
          <Tab label="KVM Hosts" icon={<ComputerIcon />} iconPosition="start" />
          <Tab label="Podman Hosts" icon={<ComputerIcon />} iconPosition="start" />
          <Tab label="Audit Logs" icon={<HistoryIcon />} iconPosition="start" />
        </Tabs>

        <Box sx={{ p: 3 }}>
          <TabPanel value={tabValue} index={0}>
            <UsersTab />
          </TabPanel>
          <TabPanel value={tabValue} index={1}>
            <KVMHostsTab />
          </TabPanel>
          <TabPanel value={tabValue} index={2}>
            <PodmanHostsTab />
          </TabPanel>
          <TabPanel value={tabValue} index={3}>
            <AuditLogsTab />
          </TabPanel>
        </Box>
      </Paper>
    </Box>
  );
};

// ============================================================================
// USERS TAB
// ============================================================================
const UsersTab: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [userToDelete, setUserToDelete] = useState<User | null>(null);

  const [formData, setFormData] = useState<{
    username: string;
    email: string;
    password: string;
    role: typeof UserRole[keyof typeof UserRole];
    is_active: boolean;
  }>({
    username: '',
    email: '',
    password: '',
    role: UserRole.VIEWER,
    is_active: true,
  });

  const fetchUsers = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<User[]>('/users');
      setUsers(response.data);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleAdd = () => {
    setEditingUser(null);
    setFormData({
      username: '',
      email: '',
      password: '',
      role: UserRole.VIEWER,
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setFormData({
      username: user.username,
      email: user.email,
      password: '',
      role: user.role,
      is_active: user.is_active,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editingUser) {
        await api.put(`/users/${editingUser.id}`, formData);
      } else {
        await api.post('/users', formData);
      }
      setDialogOpen(false);
      await fetchUsers();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDeleteClick = (user: User) => {
    setUserToDelete(user);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!userToDelete) return;

    try {
      await api.delete(`/users/${userToDelete.id}`);
      enqueueSnackbar('User deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setUserToDelete(null);
      await fetchUsers();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to delete user', { variant: 'error' });
    }
  };

  const handleToggleActive = async (user: User) => {
    try {
      await api.patch(`/users/${user.id}`, { is_active: !user.is_active });
      await fetchUsers();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  const getRoleColor = (role: string): 'error' | 'primary' | 'default' => {
    if (role === UserRole.ADMIN) return 'error';
    if (role === UserRole.OPERATOR) return 'primary';
    return 'default';
  };

  if (error) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={fetchUsers}>
          Retry
        </Button>
      }>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6">User Management</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchUsers}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
          >
            Add User
          </Button>
        </Box>
      </Box>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Created</TableCell>
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
            ) : users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Box sx={{ py: 4 }}>
                    <PersonIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No users found. Add a user to get started.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              users.map((user) => (
                <TableRow key={user.id} hover>
                  <TableCell>{user.username}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Chip
                      label={user.role}
                      color={getRoleColor(user.role)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={user.is_active ? 'Active' : 'Inactive'}
                      color={user.is_active ? 'success' : 'default'}
                      size="small"
                      onClick={() => handleToggleActive(user)}
                      sx={{ cursor: 'pointer' }}
                    />
                  </TableCell>
                  <TableCell>{formatDate(user.created_at)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Edit">
                      <IconButton
                        size="small"
                        onClick={() => handleEdit(user)}
                      >
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDeleteClick(user)}
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

      {/* User Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingUser ? 'Edit User' : 'Add User'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                required
                disabled={!!editingUser}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Password"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required={!editingUser}
                helperText={editingUser ? 'Leave blank to keep current password' : ''}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                select
                label="Role"
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as typeof UserRole[keyof typeof UserRole] })}
                required
              >
                <MenuItem value={UserRole.ADMIN}>Admin</MenuItem>
                <MenuItem value={UserRole.OPERATOR}>Operator</MenuItem>
                <MenuItem value={UserRole.VIEWER}>Viewer</MenuItem>
              </TextField>
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
          <Button onClick={handleSubmit} variant="contained" disabled={!formData.username || !formData.email}>
            {editingUser ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete User</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete user <strong>{userToDelete?.username}</strong>?
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

// ============================================================================
// KVM HOSTS TAB
// ============================================================================
const KVMHostsTab: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [hosts, setHosts] = useState<KVMHost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingHost, setEditingHost] = useState<KVMHost | null>(null);
  const [testingHost, setTestingHost] = useState<number | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [hostToDelete, setHostToDelete] = useState<KVMHost | null>(null);

  const [formData, setFormData] = useState<{
    name: string;
    hostname: string;
    port: number;
    username: string;
    auth_type: typeof KVMAuthType[keyof typeof KVMAuthType];
    ssh_key_path: string;
    password: string;
    is_active: boolean;
  }>({
    name: '',
    hostname: '',
    port: 22,
    username: 'root',
    auth_type: KVMAuthType.SSH_KEY,
    ssh_key_path: '',
    password: '',
    is_active: true,
  });

  const fetchHosts = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<KVMHost[]>('/kvm-hosts');
      setHosts(response.data);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHosts();
  }, []);

  const handleAdd = () => {
    setEditingHost(null);
    setFormData({
      name: '',
      hostname: '',
      port: 22,
      username: 'root',
      auth_type: KVMAuthType.SSH_KEY,
      ssh_key_path: '',
      password: '',
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (host: KVMHost) => {
    setEditingHost(host);
    setFormData({
      name: host.name,
      hostname: host.hostname,
      port: host.port,
      username: host.username,
      auth_type: host.auth_type,
      ssh_key_path: host.ssh_key_path || '',
      password: '',
      is_active: host.is_active,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const payload: any = {
        name: formData.name,
        hostname: formData.hostname,
        port: formData.port,
        username: formData.username,
        auth_type: formData.auth_type,
        is_active: formData.is_active,
      };

      if (formData.auth_type === KVMAuthType.SSH_KEY) {
        payload.ssh_key_path = formData.ssh_key_path;
      } else {
        if (formData.password) {
          payload.password = formData.password;
        }
      }

      if (editingHost) {
        await api.put(`/kvm-hosts/${editingHost.id}`, payload);
      } else {
        await api.post('/kvm-hosts', payload);
      }
      setDialogOpen(false);
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDeleteClick = (host: KVMHost) => {
    setHostToDelete(host);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!hostToDelete) return;

    try {
      await api.delete(`/kvm-hosts/${hostToDelete.id}`);
      enqueueSnackbar('KVM host deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setHostToDelete(null);
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to delete KVM host', { variant: 'error' });
    }
  };

  const handleTest = async (id: number) => {
    try {
      setTestingHost(id);
      await api.post(`/kvm-hosts/${id}/test`);
      enqueueSnackbar('Connection test successful!', { variant: 'success' });
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Connection test failed', { variant: 'error' });
    } finally {
      setTestingHost(null);
    }
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  if (error) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={fetchHosts}>
          Retry
        </Button>
      }>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6">KVM Hosts</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchHosts}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
          >
            Add KVM Host
          </Button>
        </Box>
      </Box>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Hostname</TableCell>
              <TableCell>Auth Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Last Connection</TableCell>
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
            ) : hosts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Box sx={{ py: 4 }}>
                    <ComputerIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No KVM hosts configured. Add one to manage VMs.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              hosts.map((host) => (
                <TableRow key={host.id} hover>
                  <TableCell>{host.name}</TableCell>
                  <TableCell>
                    {host.hostname}:{host.port}
                    <Typography variant="caption" display="block" color="text.secondary">
                      {host.username}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={host.auth_type}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={host.is_active ? 'Active' : 'Inactive'}
                      color={host.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    {host.last_connection ? formatDate(host.last_connection) : 'Never'}
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="Test Connection">
                      <IconButton
                        size="small"
                        onClick={() => handleTest(host.id)}
                        disabled={testingHost === host.id}
                      >
                        {testingHost === host.id ? (
                          <CircularProgress size={20} />
                        ) : (
                          <TestIcon />
                        )}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit">
                      <IconButton
                        size="small"
                        onClick={() => handleEdit(host)}
                      >
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDeleteClick(host)}
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

      {/* KVM Host Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingHost ? 'Edit KVM Host' : 'Add KVM Host'}
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
            <Grid size={{ xs: 12, sm: 8 }}>
              <TextField
                fullWidth
                label="Hostname"
                value={formData.hostname}
                onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                label="Port"
                type="number"
                value={formData.port}
                onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                select
                label="Authentication Type"
                value={formData.auth_type}
                onChange={(e) => setFormData({ ...formData, auth_type: e.target.value as typeof KVMAuthType[keyof typeof KVMAuthType] })}
                required
              >
                <MenuItem value={KVMAuthType.SSH_KEY}>SSH Key</MenuItem>
                <MenuItem value={KVMAuthType.PASSWORD}>Password</MenuItem>
              </TextField>
            </Grid>
            {formData.auth_type === KVMAuthType.SSH_KEY ? (
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  label="SSH Key Path"
                  value={formData.ssh_key_path}
                  onChange={(e) => setFormData({ ...formData, ssh_key_path: e.target.value })}
                  required
                  helperText="Path to SSH private key file on the server"
                />
              </Grid>
            ) : (
              <Grid size={{ xs: 12 }}>
                <TextField
                  fullWidth
                  label="Password"
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  required={!editingHost}
                  helperText={editingHost ? 'Leave blank to keep current password' : ''}
                />
              </Grid>
            )}
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
          <Button onClick={handleSubmit} variant="contained" disabled={!formData.name || !formData.hostname}>
            {editingHost ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete KVM Host</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{hostToDelete?.name}</strong>?
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

// ============================================================================
// PODMAN HOSTS TAB
// ============================================================================
const PodmanHostsTab: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [hosts, setHosts] = useState<PodmanHost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingHost, setEditingHost] = useState<PodmanHost | null>(null);
  const [testingHost, setTestingHost] = useState<number | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [hostToDelete, setHostToDelete] = useState<PodmanHost | null>(null);

  const [formData, setFormData] = useState({
    name: '',
    hostname: '',
    port: 22,
    username: 'root',
    ssh_key_path: '',
    is_active: true,
  });

  const fetchHosts = async () => {
    try {
      setIsLoading(true);
      const response = await api.get<PodmanHost[]>('/podman-hosts');
      setHosts(response.data);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHosts();
  }, []);

  const handleAdd = () => {
    setEditingHost(null);
    setFormData({
      name: '',
      hostname: '',
      port: 22,
      username: 'root',
      ssh_key_path: '',
      is_active: true,
    });
    setDialogOpen(true);
  };

  const handleEdit = (host: PodmanHost) => {
    setEditingHost(host);
    setFormData({
      name: host.name,
      hostname: host.hostname,
      port: host.port,
      username: host.username,
      ssh_key_path: host.ssh_key_path || '',
      is_active: host.is_active,
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (editingHost) {
        await api.put(`/podman-hosts/${editingHost.id}`, formData);
      } else {
        await api.post('/podman-hosts', formData);
      }
      setDialogOpen(false);
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
    }
  };

  const handleDeleteClick = (host: PodmanHost) => {
    setHostToDelete(host);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!hostToDelete) return;

    try {
      await api.delete(`/podman-hosts/${hostToDelete.id}`);
      enqueueSnackbar('Podman host deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setHostToDelete(null);
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Failed to delete Podman host', { variant: 'error' });
    }
  };

  const handleTest = async (id: number) => {
    try {
      setTestingHost(id);
      await api.post(`/podman-hosts/${id}/test`);
      enqueueSnackbar('Connection test successful!', { variant: 'success' });
      await fetchHosts();
    } catch (err) {
      setError(handleApiError(err));
      enqueueSnackbar('Connection test failed', { variant: 'error' });
    } finally {
      setTestingHost(null);
    }
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm');
  };

  if (error) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={fetchHosts}>
          Retry
        </Button>
      }>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6">Podman Hosts</Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchHosts}
            sx={{ mr: 1 }}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={handleAdd}
          >
            Add Podman Host
          </Button>
        </Box>
      </Box>

      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Hostname</TableCell>
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
            ) : hosts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Box sx={{ py: 4 }}>
                    <ComputerIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No Podman hosts configured. Add one to manage containers.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              hosts.map((host) => (
                <TableRow key={host.id} hover>
                  <TableCell>{host.name}</TableCell>
                  <TableCell>
                    {host.hostname}:{host.port}
                    <Typography variant="caption" display="block" color="text.secondary">
                      {host.username}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={host.is_active ? 'Active' : 'Inactive'}
                      color={host.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{formatDate(host.created_at)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Test Connection">
                      <IconButton
                        size="small"
                        onClick={() => handleTest(host.id)}
                        disabled={testingHost === host.id}
                      >
                        {testingHost === host.id ? (
                          <CircularProgress size={20} />
                        ) : (
                          <TestIcon />
                        )}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit">
                      <IconButton
                        size="small"
                        onClick={() => handleEdit(host)}
                      >
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDeleteClick(host)}
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

      {/* Podman Host Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingHost ? 'Edit Podman Host' : 'Add Podman Host'}
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
            <Grid size={{ xs: 12, sm: 8 }}>
              <TextField
                fullWidth
                label="Hostname"
                value={formData.hostname}
                onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <TextField
                fullWidth
                label="Port"
                type="number"
                value={formData.port}
                onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                required
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="SSH Key Path"
                value={formData.ssh_key_path}
                onChange={(e) => setFormData({ ...formData, ssh_key_path: e.target.value })}
                required
                helperText="Path to SSH private key file on the server"
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
          <Button onClick={handleSubmit} variant="contained" disabled={!formData.name || !formData.hostname}>
            {editingHost ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Podman Host</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{hostToDelete?.name}</strong>?
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

// ============================================================================
// AUDIT LOGS TAB
// ============================================================================
const AuditLogsTab: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    username: '',
    action: '',
    resource_type: '',
    severity: '',
  });

  const fetchLogs = async () => {
    try {
      setIsLoading(true);
      const params: any = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };

      if (filters.username) params.username = filters.username;
      if (filters.action) params.action = filters.action;
      if (filters.resource_type) params.resource_type = filters.resource_type;
      if (filters.severity) params.severity = filters.severity;

      const response = await api.get<PaginatedResponse<AuditLog>>('/audit-logs', { params });
      setLogs(response.data.items);
      setTotal(response.data.total);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [page, rowsPerPage]);

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleFilter = () => {
    setPage(0);
    fetchLogs();
  };

  const handleClearFilters = () => {
    setFilters({
      username: '',
      action: '',
      resource_type: '',
      severity: '',
    });
    setPage(0);
    setTimeout(fetchLogs, 0);
  };

  const formatDate = (date: string): string => {
    return format(new Date(date), 'MMM dd, yyyy HH:mm:ss');
  };

  const getSeverityColor = (severity: string): 'error' | 'warning' | 'info' | 'success' | 'default' => {
    switch (severity) {
      case AuditSeverity.CRITICAL:
      case AuditSeverity.ERROR:
        return 'error';
      case AuditSeverity.WARNING:
        return 'warning';
      case AuditSeverity.INFO:
        return 'info';
      case AuditSeverity.DEBUG:
        return 'success';
      default:
        return 'default';
    }
  };

  if (error) {
    return (
      <Alert severity="error" action={
        <Button color="inherit" size="small" onClick={fetchLogs}>
          Retry
        </Button>
      }>
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h6">Audit Logs</Typography>
        <Button
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={fetchLogs}
        >
          Refresh
        </Button>
      </Box>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField
              fullWidth
              size="small"
              label="Username"
              value={filters.username}
              onChange={(e) => setFilters({ ...filters, username: e.target.value })}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField
              fullWidth
              size="small"
              label="Action"
              value={filters.action}
              onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 2 }}>
            <TextField
              fullWidth
              size="small"
              label="Resource Type"
              value={filters.resource_type}
              onChange={(e) => setFilters({ ...filters, resource_type: e.target.value })}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 2 }}>
            <TextField
              fullWidth
              size="small"
              select
              label="Severity"
              value={filters.severity}
              onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value={AuditSeverity.DEBUG}>Debug</MenuItem>
              <MenuItem value={AuditSeverity.INFO}>Info</MenuItem>
              <MenuItem value={AuditSeverity.WARNING}>Warning</MenuItem>
              <MenuItem value={AuditSeverity.ERROR}>Error</MenuItem>
              <MenuItem value={AuditSeverity.CRITICAL}>Critical</MenuItem>
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 2 }}>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="contained" onClick={handleFilter} fullWidth>
                Filter
              </Button>
              <Button variant="outlined" onClick={handleClearFilters} fullWidth>
                Clear
              </Button>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* Logs Table */}
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>User</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Resource</TableCell>
              <TableCell>Severity</TableCell>
              <TableCell>IP Address</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <CircularProgress />
                </TableCell>
              </TableRow>
            ) : logs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <Box sx={{ py: 4 }}>
                    <HistoryIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                    <Typography variant="body2" color="text.secondary">
                      No audit logs found.
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              logs.map((log) => (
                <TableRow key={log.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {formatDate(log.created_at)}
                  </TableCell>
                  <TableCell>{log.username || 'System'}</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {log.action}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    {log.resource_type && (
                      <Typography variant="caption" display="block">
                        {log.resource_type}
                        {log.resource_name && `: ${log.resource_name}`}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={log.severity}
                      color={getSeverityColor(log.severity)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{log.ip_address || '-'}</TableCell>
                  <TableCell>
                    {log.response_status && (
                      <Chip
                        label={log.response_status}
                        color={log.response_status < 400 ? 'success' : 'error'}
                        size="small"
                      />
                    )}
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
    </Box>
  );
};

export default Admin;
