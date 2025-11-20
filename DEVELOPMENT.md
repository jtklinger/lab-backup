# Development Guide

Guide for developing and contributing to the Lab Backup System.

## Table of Contents
- [Development Environment Setup](#development-environment-setup)
- [Frontend Development](#frontend-development)
- [Backend Development](#backend-development)
- [Database Development](#database-development)
- [Running Tests](#running-tests)
- [Code Style and Standards](#code-style-and-standards)
- [Debugging](#debugging)
- [Contributing](#contributing)

---

## Development Environment Setup

### Prerequisites

- **Docker Desktop** (Windows/Mac) or **Docker** (Linux)
- **Git**
- **Node.js 20+** (for frontend development)
- **Python 3.12+** (for backend development)
- **Code Editor** (VS Code recommended)

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jtklinger/lab-backup.git
   cd lab-backup
   ```

2. **Start infrastructure services:**
   ```bash
   docker-compose up -d postgres redis
   ```

3. **Choose your development path:**
   - Frontend only: See [Frontend Development](#frontend-development)
   - Backend only: See [Backend Development](#backend-development)
   - Full stack: Do both!

---

## Frontend Development

The frontend is a React 18+ application with TypeScript, Material-UI, and Vite.

### Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment:**

   Create `frontend/.env.local`:
   ```env
   VITE_API_URL=https://localhost:8443
   ```

4. **Start development server:**
   ```bash
   npm run dev
   ```

   The frontend will be available at: http://localhost:5173 (Vite dev server)

### Frontend Structure

```
frontend/
├── src/
│   ├── components/       # Reusable React components
│   ├── views/            # Page-level components
│   ├── api/              # API client and endpoints
│   ├── contexts/         # React Context providers
│   ├── hooks/            # Custom React hooks
│   ├── types/            # TypeScript type definitions
│   ├── utils/            # Utility functions
│   ├── App.tsx           # Main application component
│   └── main.tsx          # Application entry point
├── public/               # Static assets
├── package.json          # Dependencies and scripts
├── vite.config.ts        # Vite configuration
├── tsconfig.json         # TypeScript configuration
└── Dockerfile            # Production build configuration
```

### Key Technologies

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Material-UI (MUI)** - Component library
- **React Router** - Routing
- **Axios** - HTTP client
- **Vite** - Build tool and dev server

### Available Scripts

```bash
npm run dev       # Start development server (hot reload)
npm run build     # Build for production
npm run preview   # Preview production build
npm run lint      # Run ESLint
npm run type-check # Run TypeScript compiler check
```

### Development Workflow

1. **Make changes** to `src/` files
2. **Hot reload** - Changes appear instantly in browser
3. **Check TypeScript errors** in your IDE
4. **Test in browser** - http://localhost:5173
5. **Build for production** when ready:
   ```bash
   npm run build
   ```

### Adding New Features

**Example: Add a new page**

1. **Create view component:**
   ```typescript
   // src/views/MyNewPage.tsx
   export function MyNewPage() {
     return <div>My New Page</div>;
   }
   ```

2. **Add route:**
   ```typescript
   // src/App.tsx
   import { MyNewPage } from './views/MyNewPage';

   <Route path="/my-new-page" element={<MyNewPage />} />
   ```

3. **Add navigation** (if needed):
   ```typescript
   // Update sidebar navigation
   ```

**Example: Add new API endpoint**

1. **Add to API client:**
   ```typescript
   // src/api/client.ts
   export const api = {
     // ... existing endpoints

     myNewEndpoint: {
       list: () => client.get('/api/v1/my-endpoint'),
       create: (data: MyData) => client.post('/api/v1/my-endpoint', data),
     },
   };
   ```

2. **Use in component:**
   ```typescript
   import { api } from '../api/client';

   const data = await api.myNewEndpoint.list();
   ```

### Common Issues

**CORS errors:**
- Ensure backend is running with correct CORS settings
- Check VITE_API_URL points to correct backend URL

**SSL certificate errors:**
- Accept the certificate at https://localhost:8443
- Or configure backend to use HTTP in development

**Hot reload not working:**
- Restart Vite dev server
- Check file watcher limits (Linux)

---

## Backend Development

The backend is a FastAPI application with SQLAlchemy, Celery, and PostgreSQL.

### Setup

1. **Create virtual environment:**
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Linux/Mac
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Configure environment:**

   Create `.env` file:
   ```env
   # Database
   DATABASE_URL=postgresql+asyncpg://labbackup:changeme@localhost:5432/lab_backup

   # Redis
   REDIS_URL=redis://localhost:6379/0
   CELERY_BROKER_URL=redis://localhost:6379/1
   CELERY_RESULT_BACKEND=redis://localhost:6379/2

   # Security
   SECRET_KEY=dev-secret-key-change-in-production

   # Development
   DEBUG=true
   LOG_LEVEL=debug
   ```

4. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

5. **Start development server:**
   ```bash
   # API server (with auto-reload)
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

   # Or with SSL (production-like)
   python -m backend.main
   ```

6. **Start Celery worker** (in separate terminal):
   ```bash
   celery -A backend.worker worker --loglevel=info
   ```

7. **Start Celery beat** (in separate terminal):
   ```bash
   celery -A backend.worker beat --loglevel=info
   ```

### Backend Structure

```
backend/
├── api/
│   └── v1/               # API version 1 endpoints
│       ├── auth.py       # Authentication endpoints
│       ├── kvm.py        # KVM host management
│       ├── podman.py     # Podman host management
│       ├── storage.py    # Storage backend management
│       ├── backups.py    # Backup operations
│       ├── schedules.py  # Backup schedules
│       └── jobs.py       # Job management
├── core/
│   ├── config.py         # Configuration management
│   ├── security.py       # Authentication and security
│   ├── database.py       # Database connection
│   └── encryption.py     # Encryption utilities
├── models/               # SQLAlchemy models
├── schemas/              # Pydantic schemas
├── services/             # Business logic
│   ├── kvm.py            # KVM backup service
│   ├── podman.py         # Podman backup service
│   ├── storage.py        # Storage backend service
│   └── scheduler.py      # Backup scheduler
├── worker.py             # Celery worker configuration
└── main.py               # FastAPI application
```

### Key Technologies

- **FastAPI** - Web framework
- **SQLAlchemy 2.0** - ORM (async)
- **Alembic** - Database migrations
- **Celery** - Distributed task queue
- **Pydantic** - Data validation
- **libvirt-python** - KVM integration
- **boto3** - S3 integration

### Development Workflow

1. **Make changes** to `backend/` files
2. **Auto-reload** - FastAPI reloads automatically
3. **Test endpoints** - http://localhost:8000/docs (Swagger UI)
4. **Check logs** - Terminal shows request logs
5. **Run tests** - See [Running Tests](#running-tests)

### Adding New Features

**Example: Add new API endpoint**

1. **Create endpoint:**
   ```python
   # backend/api/v1/my_endpoint.py
   from fastapi import APIRouter, Depends
   from sqlalchemy.ext.asyncio import AsyncSession
   from backend.core.database import get_db

   router = APIRouter()

   @router.get("/my-endpoint")
   async def list_items(db: AsyncSession = Depends(get_db)):
       return {"items": []}
   ```

2. **Register router:**
   ```python
   # backend/main.py
   from backend.api.v1.my_endpoint import router as my_router

   app.include_router(my_router, prefix="/api/v1", tags=["my-endpoint"])
   ```

**Example: Add database model**

1. **Create model:**
   ```python
   # backend/models/my_model.py
   from sqlalchemy import Column, Integer, String
   from backend.core.database import Base

   class MyModel(Base):
       __tablename__ = "my_table"

       id = Column(Integer, primary_key=True)
       name = Column(String, nullable=False)
   ```

2. **Create migration:**
   ```bash
   alembic revision --autogenerate -m "Add my_model"
   alembic upgrade head
   ```

**Example: Add Celery task**

1. **Create task:**
   ```python
   # backend/worker.py
   @celery_app.task(name="my_task")
   def my_background_task(param1, param2):
       # Do background work
       return {"status": "completed"}
   ```

2. **Call task from API:**
   ```python
   from backend.worker import my_background_task

   task = my_background_task.delay(param1, param2)
   return {"task_id": task.id}
   ```

---

## Database Development

### Creating Migrations

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "Description of changes"

# Review the generated migration file in database/versions/

# Apply migration
alembic upgrade head

# Rollback one version
alembic downgrade -1

# View migration history
alembic history
```

### Database Access

**Via Docker:**
```bash
docker exec -it lab-backup-db psql -U labbackup -d lab_backup
```

**Direct connection:**
```bash
psql postgresql://labbackup:changeme@localhost:5432/lab_backup
```

**Useful SQL queries:**
```sql
-- List all tables
\dt

-- Describe table
\d users

-- View all users
SELECT * FROM users;

-- View recent backups
SELECT id, vm_id, status, created_at FROM backups ORDER BY created_at DESC LIMIT 10;
```

---

## Running Tests

### Backend Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run specific test
pytest tests/test_auth.py::test_login
```

### Frontend Tests

```bash
cd frontend

# Install test dependencies (if not already installed)
npm install

# Run tests (when implemented)
npm run test

# Run with coverage
npm run test:coverage
```

---

## Code Style and Standards

### Python (Backend)

**Style guide:** PEP 8

**Tools:**
```bash
# Format code with black
black backend/

# Sort imports
isort backend/

# Lint with flake8
flake8 backend/

# Type checking with mypy
mypy backend/
```

**Standards:**
- Use type hints for all functions
- Write docstrings for public functions
- Use async/await for database operations
- Follow REST API conventions

### TypeScript (Frontend)

**Style guide:** Airbnb TypeScript Style Guide (relaxed)

**Tools:**
```bash
cd frontend

# Lint
npm run lint

# Format with Prettier (if configured)
npm run format

# Type check
npm run type-check
```

**Standards:**
- Use TypeScript strict mode
- Define interfaces for all data types
- Use functional components with hooks
- Follow Material-UI best practices

---

## Debugging

### Frontend Debugging

**Browser DevTools:**
- F12 to open DevTools
- Console tab: View console.log() and errors
- Network tab: Inspect API calls
- React DevTools extension: Inspect component state

**VS Code debugging:**
```json
// .vscode/launch.json
{
  "type": "chrome",
  "request": "launch",
  "name": "Launch Chrome",
  "url": "http://localhost:5173",
  "webRoot": "${workspaceFolder}/frontend/src"
}
```

### Backend Debugging

**VS Code debugging:**
```json
// .vscode/launch.json
{
  "type": "python",
  "request": "launch",
  "name": "FastAPI",
  "module": "uvicorn",
  "args": [
    "backend.main:app",
    "--reload",
    "--host", "0.0.0.0",
    "--port", "8000"
  ],
  "jinja": true
}
```

**Print debugging:**
```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.error("Error message")
```

**pdb debugger:**
```python
import pdb; pdb.set_trace()  # Breakpoint
```

### Celery Debugging

**View worker logs:**
```bash
celery -A backend.worker worker --loglevel=debug
```

**Monitor tasks with Flower:**
```bash
celery -A backend.worker flower
# Visit http://localhost:5555
```

**Inspect task:**
```python
from backend.worker import my_task
result = my_task.apply_async(args=[param1])
print(result.status)
print(result.result)
```

---

## Contributing

### Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/lab-backup.git
   cd lab-backup
   git remote add upstream https://github.com/jtklinger/lab-backup.git
   ```

3. **Create a feature branch:**
   ```bash
   git checkout -b feature/my-new-feature
   ```

4. **Make your changes** following the code standards
5. **Test your changes** thoroughly
6. **Commit your changes:**
   ```bash
   git add .
   git commit -m "Add my new feature"
   ```

7. **Push to your fork:**
   ```bash
   git push origin feature/my-new-feature
   ```

8. **Create a Pull Request** on GitHub

### Pull Request Guidelines

- **Clear description** of what the PR does
- **Reference any related issues** (#123)
- **Include tests** for new features
- **Update documentation** if needed
- **Follow code style** guidelines
- **Ensure CI passes** (when set up)

### Commit Message Format

```
<type>: <short summary>

<detailed description>

<footer>
```

**Types:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting)
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

**Example:**
```
feat: Add support for LXC container backups

- Add LXC connection handling
- Implement backup and restore for LXC
- Add LXC models and API endpoints

Closes #45
```

---

## Development Tips

### Performance

- Use React DevTools Profiler to identify slow renders
- Use SQLAlchemy query profiling for slow database queries
- Monitor Celery task execution times in Flower
- Use browser Network tab to identify slow API calls

### Security

- Never commit `.env` files or secrets
- Use environment variables for sensitive data
- Always validate user input on backend
- Use parameterized SQL queries (SQLAlchemy does this automatically)
- Keep dependencies updated: `npm audit`, `pip-audit`

### Testing

- Write tests for critical functionality
- Test both success and error cases
- Use factories for test data
- Mock external services (KVM, S3, etc.)

### Documentation

- Document complex functions and classes
- Keep README.md and documentation up to date
- Add inline comments for non-obvious code
- Update API documentation (docstrings update Swagger automatically)

---

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Material-UI Documentation](https://mui.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [TypeScript Documentation](https://www.typescriptlang.org/docs/)

---

## Getting Help

- **Documentation:** Check [README.md](README.md) and other docs
- **Issues:** Search existing [GitHub Issues](https://github.com/jtklinger/lab-backup/issues)
- **Questions:** Open a new issue with the "question" label
- **Discussions:** Use GitHub Discussions for general questions

Happy coding! 🚀
