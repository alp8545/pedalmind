# PedalMind

AI-powered cycling training analytics. Connect Garmin, get AI coaching insights, chat with your training data.

## Quickstart

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for PostgreSQL)

### 1. Start the database

```bash
make db-up
```

This starts PostgreSQL 16 on `localhost:5432` (user: `pedalmind`, password: `pedalmind`, db: `pedalmind`).

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start the backend

```bash
make backend
```

This installs Python dependencies, creates database tables, and starts the FastAPI server on `http://localhost:8000`.

### 4. Start the frontend

In a new terminal:

```bash
make frontend
```

This installs npm dependencies and starts the Vite dev server on `http://localhost:5173`.

### 5. Create an account

Open `http://localhost:5173`, click Register, and create your account.

### Or start everything at once

```bash
make dev
```

## Importing historical rides

If you have existing Garmin data in `~/garmin-analyzer/results/archivio_completo.json`:

```bash
# 1. Register and get a JWT token
curl -s -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"secret","name":"Your Name"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"

# 2. Run the bridge with the token
python garmin_sync/bridge.py <TOKEN>

# Preview first (dry run):
python garmin_sync/bridge.py <TOKEN> --dry-run
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/auth/me` | Current user |
| GET | `/api/profile` | Get athlete profile |
| PUT | `/api/profile` | Update athlete profile |
| GET | `/api/rides` | List rides (paginated) |
| GET | `/api/rides/:id` | Ride detail + analysis |
| POST | `/api/rides/upload` | Upload RideData JSON |
| POST | `/api/rides/:id/reanalyze` | Re-run AI analysis |
| GET | `/api/chat/conversations` | List conversations |
| POST | `/api/chat/conversations` | Create conversation |
| GET | `/api/chat/conversations/:id/messages` | Get messages |
| POST | `/api/chat/conversations/:id/messages` | Send message |

## Project structure

```
pedalmind/
  backend/         FastAPI + SQLAlchemy + PostgreSQL
  frontend/        React + Tailwind + Recharts
  ai_engine/       Anthropic SDK (Haiku analysis, Sonnet chat)
  garmin_sync/     FIT parsing + Garmin Connect sync
  contracts/       JSON Schema data contracts
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full design documentation.
