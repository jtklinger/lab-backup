# Lab Backup System - Frontend

React-based web interface for the Lab Backup System.

## Features

- **Dashboard**: System statistics and overview
- **Backups Management**: List, filter, and manage backups
- **Authentication**: Secure login with JWT tokens
- **Dark Mode**: Toggle between light and dark themes
- **Responsive Design**: Mobile-friendly layout
- **Material-UI**: Modern, professional interface

## Technology Stack

- **React 18**: Modern React with hooks
- **TypeScript**: Type-safe development
- **Material-UI v7**: Component library
- **Vite**: Fast build tool and dev server
- **React Router**: Client-side routing
- **Axios**: HTTP client for API calls
- **date-fns**: Date formatting

## Development

### Prerequisites

- Node.js 20+ and npm
- Backend API running on https://localhost:8443

### Installation

```bash
cd frontend
npm install
```

### Development Server

```bash
npm run dev
```

The development server will start on http://localhost:3000 with hot module replacement.

### Building for Production

```bash
npm run build
```

The production build will be created in the dist/ directory.

## Docker Deployment

The frontend is containerized with nginx for production deployment.

See main docker-compose.yml for deployment configuration.
