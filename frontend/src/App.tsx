/**
 * Main Application Component
 *
 * Sets up routing, theme, and authentication context.
 * Related: Issue #16 - React Frontend
 */
import React, { useState, useMemo } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { lightTheme, darkTheme } from './utils/theme';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Backups from './pages/Backups';
import VMs from './pages/VMs';
import Containers from './pages/Containers';
import Storage from './pages/Storage';
import Schedules from './pages/Schedules';
import BackupWizard from './pages/BackupWizard';
import RestoreWizard from './pages/RestoreWizard';

// Protected Route wrapper
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Main App Content (with access to AuthContext)
const AppContent: React.FC = () => {
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode');
    return saved ? JSON.parse(saved) : false;
  });

  const theme = useMemo(() => (darkMode ? darkTheme : lightTheme), [darkMode]);

  const toggleDarkMode = () => {
    setDarkMode((prev: boolean) => {
      const newMode = !prev;
      localStorage.setItem('darkMode', JSON.stringify(newMode));
      return newMode;
    });
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainLayout darkMode={darkMode} toggleDarkMode={toggleDarkMode} />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="backups" element={<Backups />} />
            <Route path="backups/create" element={<BackupWizard />} />
            <Route path="backups/:backupId/restore" element={<RestoreWizard />} />
            <Route path="vms" element={<VMs />} />
            <Route path="containers" element={<Containers />} />
            <Route path="storage" element={<Storage />} />
            <Route path="schedules" element={<Schedules />} />
            <Route path="admin" element={<div>Admin Page (Coming Soon)</div>} />
          </Route>
        </Routes>
      </Router>
    </ThemeProvider>
  );
};

// Main App wrapper with providers
const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
