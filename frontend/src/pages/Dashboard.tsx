/**
 * Dashboard Page Component
 *
 * Displays system statistics and recent activity overview.
 * Related: Issue #16 - React Frontend
 */
import React, { useEffect, useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  LinearProgress,
  Button,
} from '@mui/material';
import Grid from '@mui/material/Grid';
import {
  Backup as BackupIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  Storage as StorageIcon,
  Schedule as ScheduleIcon,
  Computer as VMIcon,
  ViewInAr as ContainerIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import api, { handleApiError } from '../services/api';
import type { DashboardStats, StorageBackend, StorageUsage } from '../types';

interface StatCardProps {
  title: string;
  value: number | string;
  icon: React.ReactElement;
  color?: string;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, icon, color = 'primary.main' }) => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box>
          <Typography color="text.secondary" gutterBottom variant="body2">
            {title}
          </Typography>
          <Typography variant="h4">{value}</Typography>
        </Box>
        <Box sx={{ color, fontSize: 48 }}>{icon}</Box>
      </Box>
    </CardContent>
  </Card>
);

interface StorageWarning {
  backend: StorageBackend;
  usage: StorageUsage;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [storageWarnings, setStorageWarnings] = useState<StorageWarning[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);

        // Fetch dashboard stats
        const statsResponse = await api.get<DashboardStats>('/dashboard/stats');
        setStats(statsResponse.data);

        // Fetch storage backends and their usage
        const backendsResponse = await api.get<StorageBackend[]>('/storage');
        const backends = backendsResponse.data;

        // Fetch usage for each backend and find those exceeding threshold
        const warnings: StorageWarning[] = [];
        for (const backend of backends) {
          if (!backend.enabled) continue;
          try {
            const usageRes = await api.get<StorageUsage>(`/storage/${backend.id}/usage`);
            const usage = usageRes.data;
            if (usage.threshold_exceeded) {
              warnings.push({ backend, usage });
            }
          } catch {
            // Skip if can't get usage
          }
        }
        setStorageWarnings(warnings.sort((a, b) => b.usage.used_percent - a.usage.used_percent));
      } catch (err) {
        setError(handleApiError(err));
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const getCapacityColor = (usedPercent: number): string => {
    if (usedPercent >= 95) return '#d32f2f'; // Red - critical
    if (usedPercent >= 90) return '#ff9800'; // Orange - warning
    return '#ffb74d'; // Light orange - threshold exceeded
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!stats) {
    return <Alert severity="info">No data available</Alert>;
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Dashboard
      </Typography>

      <Grid container spacing={3} sx={{ mt: 1 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Total Backups"
            value={stats.total_backups}
            icon={<BackupIcon />}
            color="primary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Successful Backups"
            value={stats.successful_backups}
            icon={<SuccessIcon />}
            color="success.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Failed Backups"
            value={stats.failed_backups}
            icon={<ErrorIcon />}
            color="error.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Storage Used"
            value={formatBytes(stats.total_size_bytes)}
            icon={<StorageIcon />}
            color="info.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Virtual Machines"
            value={stats.total_vms}
            icon={<VMIcon />}
            color="secondary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Containers"
            value={stats.total_containers}
            icon={<ContainerIcon />}
            color="secondary.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Active Schedules"
            value={stats.active_schedules}
            icon={<ScheduleIcon />}
            color="warning.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            title="Active Jobs"
            value={stats.active_jobs}
            icon={<BackupIcon />}
            color="info.main"
          />
        </Grid>
      </Grid>

      {/* Storage Warnings Section */}
      {storageWarnings.length > 0 && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <WarningIcon color="warning" />
            Storage Warnings
          </Typography>
          <Card>
            <CardContent>
              <Alert severity="warning" sx={{ mb: 2 }}>
                {storageWarnings.length} storage backend{storageWarnings.length > 1 ? 's have' : ' has'} exceeded the configured threshold.
              </Alert>
              {storageWarnings.map(({ backend, usage }) => (
                <Box
                  key={backend.id}
                  sx={{
                    p: 2,
                    mb: 2,
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 1,
                    '&:last-child': { mb: 0 },
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="subtitle1" fontWeight="medium">
                      {backend.name}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ color: getCapacityColor(usage.used_percent), fontWeight: 'bold' }}
                    >
                      {usage.used_percent.toFixed(1)}% Used
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(usage.used_percent, 100)}
                    sx={{
                      height: 10,
                      borderRadius: 5,
                      backgroundColor: '#e0e0e0',
                      mb: 1,
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: getCapacityColor(usage.used_percent),
                        borderRadius: 5,
                      },
                    }}
                  />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="body2" color="text.secondary">
                      {formatBytes(usage.used)} / {formatBytes(usage.capacity)}
                      {' '}&middot;{' '}
                      Threshold: {backend.threshold}%
                    </Typography>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => navigate('/storage')}
                    >
                      Manage Storage
                    </Button>
                  </Box>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Box>
      )}
    </Box>
  );
};

export default Dashboard;
