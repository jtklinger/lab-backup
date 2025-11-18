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
} from '@mui/icons-material';
import api, { handleApiError } from '../services/api';
import type { DashboardStats } from '../types';

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

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setIsLoading(true);
        const response = await api.get<DashboardStats>('/dashboard/stats');
        setStats(response.data);
      } catch (err) {
        setError(handleApiError(err));
      } finally {
        setIsLoading(false);
      }
    };

    fetchStats();
  }, []);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
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
    </Box>
  );
};

export default Dashboard;
