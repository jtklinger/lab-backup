/**
 * SSH Key Management Component
 *
 * Manage SSH keys for KVM hosts - upload, generate, view, and delete keys.
 * Related: Issue #[missing-frontend-features]
 */
import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Chip,
  Typography,
  Tabs,
  Tab,
  MenuItem,
  Alert,
  CircularProgress,
  Tooltip,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  VpnKey as KeyIcon,
  ContentCopy as CopyIcon,
  Upload as UploadIcon,
  AutoAwesome as GenerateIcon,
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import { sshKeyAPI, handleApiError } from '../../services/api';
import type { SSHKey } from '../../types';

interface SSHKeyManagementProps {
  hostId: number;
  hostName: string;
  open: boolean;
  onClose: () => void;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sshkey-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  );
}

const SSHKeyManagement: React.FC<SSHKeyManagementProps> = ({ hostId, hostName, open, onClose }) => {
  const { enqueueSnackbar } = useSnackbar();
  const [keys, setKeys] = useState<SSHKey[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [keyToDelete, setKeyToDelete] = useState<SSHKey | null>(null);
  const [viewPublicKeyDialog, setViewPublicKeyDialog] = useState(false);
  const [selectedPublicKey, setSelectedPublicKey] = useState('');

  // Upload key form
  const [uploadKeyName, setUploadKeyName] = useState('');
  const [uploadKeyContent, setUploadKeyContent] = useState('');

  // Generate key form
  const [generateKeyName, setGenerateKeyName] = useState('');
  const [generateKeyType, setGenerateKeyType] = useState('rsa');
  const [generateKeySize, setGenerateKeySize] = useState(4096);
  const [generatedKeys, setGeneratedKeys] = useState<{ public_key: string; private_key: string } | null>(null);

  const fetchKeys = async () => {
    try {
      setIsLoading(true);
      const response = await sshKeyAPI.list(hostId);
      setKeys(response.data);
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchKeys();
    }
  }, [open, hostId]);

  const handleUploadKey = async () => {
    if (!uploadKeyName || !uploadKeyContent) {
      enqueueSnackbar('Please provide key name and private key content', { variant: 'warning' });
      return;
    }

    try {
      await sshKeyAPI.upload(hostId, {
        name: uploadKeyName,
        private_key: uploadKeyContent,
      });
      enqueueSnackbar('SSH key uploaded successfully', { variant: 'success' });
      setUploadKeyName('');
      setUploadKeyContent('');
      setTabValue(0); // Switch to list view
      fetchKeys();
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleGenerateKey = async () => {
    if (!generateKeyName) {
      enqueueSnackbar('Please provide a key name', { variant: 'warning' });
      return;
    }

    try {
      const response = await sshKeyAPI.generate(hostId, {
        name: generateKeyName,
        key_type: generateKeyType,
        key_size: generateKeySize,
      });
      setGeneratedKeys(response.data);
      enqueueSnackbar('SSH key pair generated successfully', { variant: 'success' });
      fetchKeys();
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleViewPublicKey = async (key: SSHKey) => {
    try {
      const response = await sshKeyAPI.getPublicKey(hostId, key.id);
      setSelectedPublicKey(response.data.public_key);
      setViewPublicKeyDialog(true);
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleCopyPublicKey = () => {
    navigator.clipboard.writeText(selectedPublicKey);
    enqueueSnackbar('Public key copied to clipboard', { variant: 'success' });
  };

  const handleDeleteKey = async () => {
    if (!keyToDelete) return;

    try {
      await sshKeyAPI.delete(hostId, keyToDelete.id);
      enqueueSnackbar('SSH key deleted successfully', { variant: 'success' });
      setDeleteDialogOpen(false);
      setKeyToDelete(null);
      fetchKeys();
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleClose = () => {
    setTabValue(0);
    setUploadKeyName('');
    setUploadKeyContent('');
    setGenerateKeyName('');
    setGeneratedKeys(null);
    onClose();
  };

  return (
    <>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>SSH Key Management - {hostName}</DialogTitle>
        <DialogContent>
          <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
            <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)}>
              <Tab icon={<KeyIcon />} label="Keys" />
              <Tab icon={<UploadIcon />} label="Upload" />
              <Tab icon={<GenerateIcon />} label="Generate" />
            </Tabs>
          </Box>

          {/* List Keys Tab */}
          <TabPanel value={tabValue} index={0}>
            {isLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                <CircularProgress />
              </Box>
            ) : keys.length === 0 ? (
              <Alert severity="info">No SSH keys configured for this host</Alert>
            ) : (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Name</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Fingerprint</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {keys.map((key) => (
                      <TableRow key={key.id}>
                        <TableCell>{key.name}</TableCell>
                        <TableCell>
                          <Chip label={key.key_type.toUpperCase()} size="small" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                            {key.fingerprint}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="View Public Key">
                            <IconButton size="small" onClick={() => handleViewPublicKey(key)}>
                              <KeyIcon />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => {
                                setKeyToDelete(key);
                                setDeleteDialogOpen(true);
                              }}
                            >
                              <DeleteIcon />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>

          {/* Upload Key Tab */}
          <TabPanel value={tabValue} index={1}>
            <Typography variant="body2" color="text.secondary" paragraph>
              Upload an existing SSH private key. The public key will be extracted automatically.
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                fullWidth
                label="Key Name"
                value={uploadKeyName}
                onChange={(e) => setUploadKeyName(e.target.value)}
                placeholder="e.g., my-kvm-key"
              />
              <TextField
                fullWidth
                multiline
                rows={10}
                label="Private Key"
                value={uploadKeyContent}
                onChange={(e) => setUploadKeyContent(e.target.value)}
                placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                sx={{ fontFamily: 'monospace' }}
              />
              <Button
                variant="contained"
                startIcon={<UploadIcon />}
                onClick={handleUploadKey}
              >
                Upload Key
              </Button>
            </Box>
          </TabPanel>

          {/* Generate Key Tab */}
          <TabPanel value={tabValue} index={2}>
            <Typography variant="body2" color="text.secondary" paragraph>
              Generate a new SSH key pair. Save the private key securely before closing this dialog.
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                fullWidth
                label="Key Name"
                value={generateKeyName}
                onChange={(e) => setGenerateKeyName(e.target.value)}
                placeholder="e.g., production-kvm"
              />
              <TextField
                select
                fullWidth
                label="Key Type"
                value={generateKeyType}
                onChange={(e) => setGenerateKeyType(e.target.value)}
              >
                <MenuItem value="rsa">RSA</MenuItem>
                <MenuItem value="ed25519">Ed25519</MenuItem>
              </TextField>
              {generateKeyType === 'rsa' && (
                <TextField
                  select
                  fullWidth
                  label="Key Size"
                  value={generateKeySize}
                  onChange={(e) => setGenerateKeySize(Number(e.target.value))}
                >
                  <MenuItem value={2048}>2048 bits</MenuItem>
                  <MenuItem value={4096}>4096 bits (Recommended)</MenuItem>
                </TextField>
              )}
              <Button
                variant="contained"
                startIcon={<GenerateIcon />}
                onClick={handleGenerateKey}
                disabled={!!generatedKeys}
              >
                Generate Key Pair
              </Button>

              {generatedKeys && (
                <Box sx={{ mt: 2 }}>
                  <Alert severity="success" sx={{ mb: 2 }}>
                    Key pair generated successfully! Save the private key securely - it won't be shown again.
                  </Alert>
                  <TextField
                    fullWidth
                    multiline
                    rows={8}
                    label="Private Key (Save this!)"
                    value={generatedKeys.private_key}
                    InputProps={{ readOnly: true }}
                    sx={{ fontFamily: 'monospace', mb: 2 }}
                  />
                  <TextField
                    fullWidth
                    multiline
                    rows={4}
                    label="Public Key"
                    value={generatedKeys.public_key}
                    InputProps={{ readOnly: true }}
                    sx={{ fontFamily: 'monospace' }}
                  />
                </Box>
              )}
            </Box>
          </TabPanel>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* View Public Key Dialog */}
      <Dialog open={viewPublicKeyDialog} onClose={() => setViewPublicKeyDialog(false)} maxWidth="md" fullWidth>
        <DialogTitle>Public Key</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" paragraph>
            Copy this public key and add it to the target host's ~/.ssh/authorized_keys file.
          </Typography>
          <TextField
            fullWidth
            multiline
            rows={6}
            value={selectedPublicKey}
            InputProps={{ readOnly: true }}
            sx={{ fontFamily: 'monospace' }}
          />
        </DialogContent>
        <DialogActions>
          <Button startIcon={<CopyIcon />} onClick={handleCopyPublicKey}>
            Copy to Clipboard
          </Button>
          <Button onClick={() => setViewPublicKeyDialog(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete SSH Key?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete the SSH key "<strong>{keyToDelete?.name}</strong>"?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDeleteKey} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default SSHKeyManagement;
