/**
 * Schedules Management Page
 *
 * Manage automated backup schedules with cron expressions.
 * Related: Issue #16 - React Frontend
 */
import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Alert,
} from '@mui/material';
import {
  Schedule as ScheduleIcon,
} from '@mui/icons-material';

const Schedules: React.FC = () => {
  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Backup Schedules</Typography>
      </Box>

      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <ScheduleIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
        <Typography variant="h6" gutterBottom>
          Schedule Management Coming Soon
        </Typography>
        <Alert severity="info" sx={{ mt: 2, maxWidth: 600, mx: 'auto' }}>
          The Schedules feature is currently being updated to match the backend API schema.
          This page will allow you to create automated backup schedules with cron expressions.
        </Alert>
      </Paper>
    </Box>
  );
};

export default Schedules;
