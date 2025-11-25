/**
 * Jobs & Logs Page
 *
 * Displays job tracking and log viewing with real-time WebSocket updates.
 * Three tabs: Active Jobs, Job History, System Logs
 */
import React, { useState, useEffect, useCallback } from 'react';
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
  Tabs,
  Tab,
  TextField,
  MenuItem,
  Collapse,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  PlayArrow as RunningIcon,
  CheckCircle as CompletedIcon,
  Error as ErrorIcon,
  Cancel as CancelIcon,
  Pending as PendingIcon,
  History as HistoryIcon,
  Terminal as LogIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  Info as InfoIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { format, formatDistanceToNow } from 'date-fns';
import { useSnackbar } from 'notistack';
import { jobsAPI, logsAPI, handleApiError } from '../services/api';
import type { Job, JobStatus, ApplicationLog } from '../types';
import { JobDetailsModal } from '../components/jobs/JobDetailsModal';

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

// Status icon mapping
const statusIcons: Record<string, React.ReactNode> = {
  pending: <PendingIcon sx={{ color: 'grey.500' }} />,
  running: <RunningIcon sx={{ color: 'primary.main' }} />,
  completed: <CompletedIcon sx={{ color: 'success.main' }} />,
  failed: <ErrorIcon sx={{ color: 'error.main' }} />,
  cancelled: <CancelIcon sx={{ color: 'warning.main' }} />,
};

// Status chip colors
const statusColors: Record<string, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
  pending: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
};

// Log level colors
const levelColors: Record<string, string> = {
  DEBUG: '#9e9e9e',
  INFO: '#2196f3',
  WARNING: '#ff9800',
  ERROR: '#f44336',
  CRITICAL: '#d32f2f',
};

const JobsLogs: React.FC = () => {
  const [tabValue, setTabValue] = useState(0);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Jobs & Logs
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Monitor backup jobs and view system logs
      </Typography>

      <Paper>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="Active Jobs" icon={<RunningIcon />} iconPosition="start" />
          <Tab label="Job History" icon={<HistoryIcon />} iconPosition="start" />
          <Tab label="System Logs" icon={<LogIcon />} iconPosition="start" />
        </Tabs>

        <Box sx={{ p: 3 }}>
          <TabPanel value={tabValue} index={0}>
            <ActiveJobsTab />
          </TabPanel>
          <TabPanel value={tabValue} index={1}>
            <JobHistoryTab />
          </TabPanel>
          <TabPanel value={tabValue} index={2}>
            <SystemLogsTab />
          </TabPanel>
        </Box>
      </Paper>
    </Box>
  );
};

// ============================================================================
// ACTIVE JOBS TAB
// ============================================================================
const ActiveJobsTab: React.FC = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      setIsLoading(true);
      // Fetch running and pending jobs
      const [runningRes, pendingRes] = await Promise.all([
        jobsAPI.list({ status: 'running' as JobStatus, limit: 100 }),
        jobsAPI.list({ status: 'pending' as JobStatus, limit: 100 }),
      ]);
      const allJobs = [...runningRes.data.jobs, ...pendingRes.data.jobs];
      // Sort by created_at descending
      allJobs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setJobs(allJobs);
      setError(null);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const handleCancelJob = async (job: Job) => {
    try {
      await jobsAPI.cancel(job.id);
      enqueueSnackbar('Job cancelled successfully', { variant: 'success' });
      fetchJobs();
    } catch (err) {
      enqueueSnackbar(handleApiError(err), { variant: 'error' });
    }
  };

  const handleRowClick = (job: Job) => {
    setSelectedJob(job);
    setModalOpen(true);
  };

  const getDuration = (job: Job) => {
    if (!job.started_at) return '-';
    const start = new Date(job.started_at);
    return formatDistanceToNow(start, { addSuffix: false });
  };

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="subtitle1">
          {jobs.length} active job{jobs.length !== 1 ? 's' : ''}
        </Typography>
        <Button
          startIcon={isLoading ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={fetchJobs}
          disabled={isLoading}
        >
          Refresh
        </Button>
      </Box>

      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Started</TableCell>
              <TableCell>Duration</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                    No active jobs
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((job) => (
                <TableRow
                  key={job.id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => handleRowClick(job)}
                >
                  <TableCell>#{job.id}</TableCell>
                  <TableCell>
                    <Chip label={job.type} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {statusIcons[job.status]}
                      <Chip
                        label={job.status}
                        color={statusColors[job.status]}
                        size="small"
                      />
                    </Box>
                  </TableCell>
                  <TableCell>
                    {job.started_at
                      ? format(new Date(job.started_at), 'MMM d, HH:mm:ss')
                      : '-'}
                  </TableCell>
                  <TableCell>{getDuration(job)}</TableCell>
                  <TableCell>
                    <Tooltip title="Cancel job">
                      <IconButton
                        size="small"
                        color="warning"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCancelJob(job);
                        }}
                      >
                        <CancelIcon />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <JobDetailsModal
        open={modalOpen}
        job={selectedJob}
        onClose={() => {
          setModalOpen(false);
          setSelectedJob(null);
        }}
      />
    </>
  );
};

// ============================================================================
// JOB HISTORY TAB
// ============================================================================
const JobHistoryTab: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  // Pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const fetchJobs = useCallback(async () => {
    try {
      setIsLoading(true);
      const params: any = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };
      if (statusFilter) params.status = statusFilter;
      if (typeFilter) params.job_type = typeFilter;

      const response = await jobsAPI.list(params);
      setJobs(response.data.jobs);
      setTotal(response.data.total);
      setError(null);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, [page, rowsPerPage, statusFilter, typeFilter]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const handleRowClick = (job: Job) => {
    setSelectedJob(job);
    setModalOpen(true);
  };

  const getDuration = (job: Job) => {
    if (!job.started_at || !job.completed_at) return '-';
    const start = new Date(job.started_at);
    const end = new Date(job.completed_at);
    const seconds = Math.floor((end.getTime() - start.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <>
      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          select
          size="small"
          label="Status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="completed">Completed</MenuItem>
          <MenuItem value="failed">Failed</MenuItem>
          <MenuItem value="cancelled">Cancelled</MenuItem>
        </TextField>

        <TextField
          select
          size="small"
          label="Job Type"
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="backup">Backup</MenuItem>
          <MenuItem value="restore">Restore</MenuItem>
          <MenuItem value="verification">Verification</MenuItem>
          <MenuItem value="cleanup">Cleanup</MenuItem>
        </TextField>

        <Box sx={{ flex: 1 }} />

        <Button
          startIcon={isLoading ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={fetchJobs}
          disabled={isLoading}
        >
          Refresh
        </Button>
      </Box>

      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Started</TableCell>
              <TableCell>Completed</TableCell>
              <TableCell>Duration</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <CircularProgress size={24} />
                </TableCell>
              </TableRow>
            ) : jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                    No jobs found
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((job) => (
                <TableRow
                  key={job.id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => handleRowClick(job)}
                >
                  <TableCell>#{job.id}</TableCell>
                  <TableCell>
                    <Chip label={job.type} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {statusIcons[job.status]}
                      <Chip
                        label={job.status}
                        color={statusColors[job.status]}
                        size="small"
                      />
                    </Box>
                  </TableCell>
                  <TableCell>
                    {job.started_at
                      ? format(new Date(job.started_at), 'MMM d, yyyy HH:mm')
                      : '-'}
                  </TableCell>
                  <TableCell>
                    {job.completed_at
                      ? format(new Date(job.completed_at), 'MMM d, yyyy HH:mm')
                      : '-'}
                  </TableCell>
                  <TableCell>{getDuration(job)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={(_, newPage) => setPage(newPage)}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={(e) => {
          setRowsPerPage(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[25, 50, 100]}
      />

      <JobDetailsModal
        open={modalOpen}
        job={selectedJob}
        onClose={() => {
          setModalOpen(false);
          setSelectedJob(null);
        }}
      />
    </>
  );
};

// ============================================================================
// SYSTEM LOGS TAB
// ============================================================================
const SystemLogsTab: React.FC = () => {
  const [logs, setLogs] = useState<ApplicationLog[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  // Filters
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [searchText, setSearchText] = useState<string>('');

  // Pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  const fetchLogs = useCallback(async () => {
    try {
      setIsLoading(true);
      const params: any = {
        limit: rowsPerPage,
        offset: page * rowsPerPage,
      };
      if (levelFilter) params.level = levelFilter;
      if (searchText) params.search = searchText;

      const response = await logsAPI.getApplicationLogs(params);
      setLogs(response.data.logs || []);
      setTotal(response.data.total || 0);
      setError(null);
    } catch (err) {
      setError(handleApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, [page, rowsPerPage, levelFilter, searchText]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const toggleExpand = (logId: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(logId)) {
        next.delete(logId);
      } else {
        next.add(logId);
      }
      return next;
    });
  };

  const getLevelIcon = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR':
      case 'CRITICAL':
        return <ErrorIcon sx={{ color: levelColors[level.toUpperCase()], fontSize: 18 }} />;
      case 'WARNING':
        return <WarningIcon sx={{ color: levelColors[level.toUpperCase()], fontSize: 18 }} />;
      case 'INFO':
        return <InfoIcon sx={{ color: levelColors[level.toUpperCase()], fontSize: 18 }} />;
      default:
        return null;
    }
  };

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <>
      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          select
          size="small"
          label="Level"
          value={levelFilter}
          onChange={(e) => {
            setLevelFilter(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="DEBUG">Debug</MenuItem>
          <MenuItem value="INFO">Info</MenuItem>
          <MenuItem value="WARNING">Warning</MenuItem>
          <MenuItem value="ERROR">Error</MenuItem>
          <MenuItem value="CRITICAL">Critical</MenuItem>
        </TextField>

        <TextField
          size="small"
          label="Search"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              setPage(0);
              fetchLogs();
            }
          }}
          placeholder="Search messages..."
          sx={{ minWidth: 250 }}
        />

        <Box sx={{ flex: 1 }} />

        <Button
          startIcon={isLoading ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={fetchLogs}
          disabled={isLoading}
        >
          Refresh
        </Button>
      </Box>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell width={40}></TableCell>
              <TableCell width={180}>Timestamp</TableCell>
              <TableCell width={100}>Level</TableCell>
              <TableCell width={200}>Logger</TableCell>
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <CircularProgress size={24} />
                </TableCell>
              </TableRow>
            ) : logs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
                    No logs found
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              logs.map((log) => (
                <React.Fragment key={log.id}>
                  <TableRow
                    hover
                    sx={{
                      cursor: log.exception ? 'pointer' : 'default',
                      bgcolor: log.level === 'ERROR' || log.level === 'CRITICAL'
                        ? 'error.main'
                        : 'inherit',
                      '& td': {
                        color: log.level === 'ERROR' || log.level === 'CRITICAL'
                          ? 'error.contrastText'
                          : 'inherit',
                      },
                    }}
                    onClick={() => log.exception && toggleExpand(log.id)}
                  >
                    <TableCell>
                      {log.exception && (
                        <IconButton size="small">
                          {expandedRows.has(log.id) ? <CollapseIcon /> : <ExpandIcon />}
                        </IconButton>
                      )}
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {format(new Date(log.timestamp), 'MMM d HH:mm:ss.SSS')}
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        {getLevelIcon(log.level)}
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: log.level === 'ERROR' || log.level === 'CRITICAL'
                              ? 'bold'
                              : 'normal',
                          }}
                        >
                          {log.level}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {log.logger}
                    </TableCell>
                    <TableCell
                      sx={{
                        maxWidth: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <Tooltip title={log.message}>
                        <span>{log.message}</span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                  {log.exception && (
                    <TableRow>
                      <TableCell colSpan={5} sx={{ p: 0 }}>
                        <Collapse in={expandedRows.has(log.id)}>
                          <Box
                            sx={{
                              p: 2,
                              bgcolor: '#1e1e1e',
                              fontFamily: 'monospace',
                              fontSize: '0.75rem',
                              color: '#d4d4d4',
                              whiteSpace: 'pre-wrap',
                              maxHeight: 300,
                              overflow: 'auto',
                            }}
                          >
                            {log.exception}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={(_, newPage) => setPage(newPage)}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={(e) => {
          setRowsPerPage(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[25, 50, 100]}
      />
    </>
  );
};

export default JobsLogs;
