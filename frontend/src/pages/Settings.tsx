/**
 * Settings Management Page
 *
 * Manage system settings including Email, Retention, Alerts, Security, and Logging.
 * Related: Issue #[missing-frontend-features]
 */
import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  TextField,
  CircularProgress,
  Alert,
  Tab,
  Tabs,
  Switch,
  FormControlLabel,
  InputAdornment,
  IconButton,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Save as SaveIcon,
  Refresh as RefreshIcon,
  Visibility,
  VisibilityOff,
} from '@mui/icons-material';
import { useSnackbar } from 'notistack';
import { settingsAPI, handleApiError } from '../services/api';

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
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const Settings: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [tabValue, setTabValue] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Email Settings
  const [emailSettings, setEmailSettings] = useState({
    'email.enabled': 'false',
    'email.smtp_host': '',
    'email.smtp_port': '587',
    'email.smtp_user': '',
    'email.smtp_password': '',
    'email.use_tls': 'true',
    'email.from_address': '',
  });

  // Retention Settings
  const [retentionSettings, setRetentionSettings] = useState({
    'retention.keep_daily': '7',
    'retention.keep_weekly': '4',
    'retention.keep_monthly': '12',
    'retention.keep_yearly': '5',
  });

  // Alert Settings
  const [alertSettings, setAlertSettings] = useState({
    'alerts.enabled': 'false',
    'alerts.on_success': 'false',
    'alerts.on_failure': 'true',
    'alerts.on_warning': 'true',
  });

  // Security Settings
  const [securitySettings, setSecuritySettings] = useState({
    'security.require_https': 'true',
    'security.session_timeout': '3600',
    'security.max_login_attempts': '5',
  });

  // Logging Settings
  const [loggingSettings, setLoggingSettings] = useState({
    'logging.level': 'INFO',
    'logging.max_file_size': '10485760',
    'logging.backup_count': '5',
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setIsLoading(true);
      const categories = ['email', 'retention', 'alerts', 'security', 'logging'];

      for (const category of categories) {
        const response = await settingsAPI.getByCategory(category);
        const settings: Record<string, string> = {};
        response.data.forEach((setting: any) => {
          settings[setting.key] = setting.value;
        });

        if (category === 'email') setEmailSettings(prev => ({ ...prev, ...settings }));
        else if (category === 'retention') setRetentionSettings(prev => ({ ...prev, ...settings }));
        else if (category === 'alerts') setAlertSettings(prev => ({ ...prev, ...settings }));
        else if (category === 'security') setSecuritySettings(prev => ({ ...prev, ...settings }));
        else if (category === 'logging') setLoggingSettings(prev => ({ ...prev, ...settings }));
      }
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveEmail = async () => {
    try {
      await settingsAPI.bulkUpdate(emailSettings);
      enqueueSnackbar('Email settings saved successfully', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleSaveRetention = async () => {
    try {
      await settingsAPI.bulkUpdate(retentionSettings);
      enqueueSnackbar('Retention settings saved successfully', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleSaveAlerts = async () => {
    try {
      await settingsAPI.bulkUpdate(alertSettings);
      enqueueSnackbar('Alert settings saved successfully', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleSaveSecurity = async () => {
    try {
      await settingsAPI.bulkUpdate(securitySettings);
      enqueueSnackbar('Security settings saved successfully', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleSaveLogging = async () => {
    try {
      await settingsAPI.bulkUpdate(loggingSettings);
      enqueueSnackbar('Logging settings saved successfully', { variant: 'success' });
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Paper sx={{ mt: 2 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)}>
            <Tab label="Email / SMTP" />
            <Tab label="Retention" />
            <Tab label="Alerts" />
            <Tab label="Security" />
            <Tab label="Logging" />
          </Tabs>
        </Box>

        {/* Email Settings Tab */}
        <TabPanel value={tabValue} index={0}>
          <Typography variant="h6" gutterBottom>
            Email / SMTP Configuration
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={emailSettings['email.enabled'] === 'true'}
                    onChange={(e) =>
                      setEmailSettings({ ...emailSettings, 'email.enabled': String(e.target.checked) })
                    }
                  />
                }
                label="Enable Email Notifications"
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="SMTP Host"
                value={emailSettings['email.smtp_host']}
                onChange={(e) => setEmailSettings({ ...emailSettings, 'email.smtp_host': e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="SMTP Port"
                type="number"
                value={emailSettings['email.smtp_port']}
                onChange={(e) => setEmailSettings({ ...emailSettings, 'email.smtp_port': e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="SMTP Username"
                value={emailSettings['email.smtp_user']}
                onChange={(e) => setEmailSettings({ ...emailSettings, 'email.smtp_user': e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="SMTP Password"
                type={showPassword ? 'text' : 'password'}
                value={emailSettings['email.smtp_password']}
                onChange={(e) => setEmailSettings({ ...emailSettings, 'email.smtp_password': e.target.value })}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton onClick={() => setShowPassword(!showPassword)} edge="end">
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="From Address"
                type="email"
                value={emailSettings['email.from_address']}
                onChange={(e) => setEmailSettings({ ...emailSettings, 'email.from_address': e.target.value })}
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={emailSettings['email.use_tls'] === 'true'}
                    onChange={(e) =>
                      setEmailSettings({ ...emailSettings, 'email.use_tls': String(e.target.checked) })
                    }
                  />
                }
                label="Use TLS"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveEmail}>
                  Save Email Settings
                </Button>
                <Button startIcon={<RefreshIcon />} onClick={loadSettings}>
                  Reset
                </Button>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Retention Settings Tab */}
        <TabPanel value={tabValue} index={1}>
          <Typography variant="h6" gutterBottom>
            Backup Retention Policy
          </Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            Configure how many backups to keep for each time period. Set to 0 to disable that retention period.
          </Alert>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Keep Daily Backups"
                type="number"
                value={retentionSettings['retention.keep_daily']}
                onChange={(e) =>
                  setRetentionSettings({ ...retentionSettings, 'retention.keep_daily': e.target.value })
                }
                helperText="Number of daily backups to retain"
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Keep Weekly Backups"
                type="number"
                value={retentionSettings['retention.keep_weekly']}
                onChange={(e) =>
                  setRetentionSettings({ ...retentionSettings, 'retention.keep_weekly': e.target.value })
                }
                helperText="Number of weekly backups to retain"
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Keep Monthly Backups"
                type="number"
                value={retentionSettings['retention.keep_monthly']}
                onChange={(e) =>
                  setRetentionSettings({ ...retentionSettings, 'retention.keep_monthly': e.target.value })
                }
                helperText="Number of monthly backups to retain"
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Keep Yearly Backups"
                type="number"
                value={retentionSettings['retention.keep_yearly']}
                onChange={(e) =>
                  setRetentionSettings({ ...retentionSettings, 'retention.keep_yearly': e.target.value })
                }
                helperText="Number of yearly backups to retain"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveRetention}>
                  Save Retention Settings
                </Button>
                <Button startIcon={<RefreshIcon />} onClick={loadSettings}>
                  Reset
                </Button>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Alert Settings Tab */}
        <TabPanel value={tabValue} index={2}>
          <Typography variant="h6" gutterBottom>
            Alert Configuration
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={alertSettings['alerts.enabled'] === 'true'}
                    onChange={(e) =>
                      setAlertSettings({ ...alertSettings, 'alerts.enabled': String(e.target.checked) })
                    }
                  />
                }
                label="Enable Alerts"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={alertSettings['alerts.on_success'] === 'true'}
                    onChange={(e) =>
                      setAlertSettings({ ...alertSettings, 'alerts.on_success': String(e.target.checked) })
                    }
                  />
                }
                label="Alert on Successful Backups"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={alertSettings['alerts.on_failure'] === 'true'}
                    onChange={(e) =>
                      setAlertSettings({ ...alertSettings, 'alerts.on_failure': String(e.target.checked) })
                    }
                  />
                }
                label="Alert on Failed Backups"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={alertSettings['alerts.on_warning'] === 'true'}
                    onChange={(e) =>
                      setAlertSettings({ ...alertSettings, 'alerts.on_warning': String(e.target.checked) })
                    }
                  />
                }
                label="Alert on Warnings"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveAlerts}>
                  Save Alert Settings
                </Button>
                <Button startIcon={<RefreshIcon />} onClick={loadSettings}>
                  Reset
                </Button>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Security Settings Tab */}
        <TabPanel value={tabValue} index={3}>
          <Typography variant="h6" gutterBottom>
            Security Configuration
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={securitySettings['security.require_https'] === 'true'}
                    onChange={(e) =>
                      setSecuritySettings({ ...securitySettings, 'security.require_https': String(e.target.checked) })
                    }
                  />
                }
                label="Require HTTPS"
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Session Timeout (seconds)"
                type="number"
                value={securitySettings['security.session_timeout']}
                onChange={(e) =>
                  setSecuritySettings({ ...securitySettings, 'security.session_timeout': e.target.value })
                }
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Max Login Attempts"
                type="number"
                value={securitySettings['security.max_login_attempts']}
                onChange={(e) =>
                  setSecuritySettings({ ...securitySettings, 'security.max_login_attempts': e.target.value })
                }
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveSecurity}>
                  Save Security Settings
                </Button>
                <Button startIcon={<RefreshIcon />} onClick={loadSettings}>
                  Reset
                </Button>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Logging Settings Tab */}
        <TabPanel value={tabValue} index={4}>
          <Typography variant="h6" gutterBottom>
            Logging Configuration
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                select
                label="Log Level"
                value={loggingSettings['logging.level']}
                onChange={(e) => setLoggingSettings({ ...loggingSettings, 'logging.level': e.target.value })}
                SelectProps={{ native: true }}
              >
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
                <option value="CRITICAL">CRITICAL</option>
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <TextField
                fullWidth
                label="Max File Size (bytes)"
                type="number"
                value={loggingSettings['logging.max_file_size']}
                onChange={(e) =>
                  setLoggingSettings({ ...loggingSettings, 'logging.max_file_size': e.target.value })
                }
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <TextField
                fullWidth
                label="Backup Count"
                type="number"
                value={loggingSettings['logging.backup_count']}
                onChange={(e) =>
                  setLoggingSettings({ ...loggingSettings, 'logging.backup_count': e.target.value })
                }
                helperText="Number of log file backups to keep"
              />
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSaveLogging}>
                  Save Logging Settings
                </Button>
                <Button startIcon={<RefreshIcon />} onClick={loadSettings}>
                  Reset
                </Button>
              </Box>
            </Grid>
          </Grid>
        </TabPanel>
      </Paper>
    </Box>
  );
};

export default Settings;
