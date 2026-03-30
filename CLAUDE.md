# CLAUDE.md — Instructions for Claude Code

Read ARCHITECTURE.md first. It is the single source of truth.

## Project: PedalMind
AI-powered cycling training analytics. Single-user (Alessio), deployed on Railway (backend) + Vercel (frontend).

## Key Rules
- All data contracts are in contracts/ — read them before modifying related code
- No hard-coded athlete data — read FTP/MaxHR/Weight from AthleteProfile DB table
- Python typing + Pydantic models everywhere
- Backend: FastAPI + SQLAlchemy async + PostgreSQL
- Frontend: React + Tailwind + Recharts
- AI: Anthropic SDK, Haiku for workout interpretation, Sonnet for chat
- Test data in tests/test_data.json (real cycling metrics)
- Tests: pytest in backend/tests/ (21 tests). Run: `cd backend && python3 -m pytest tests/ -v`

## Module Boundaries
- garmin_sync/ → legacy FIT file parsing (unused, see TODO)
- ai_engine/ → ride analysis prompts, chat context builder
- backend/ → FastAPI API server, orchestrates everything
  - backend/app/core/garth_client.py → ALL Garmin API calls go through garmin_api_call()
  - backend/app/services/trends.py → CTL/ATL/TSB computation (Coggan EWMA)
  - backend/app/routers/workout.py → workout interpret (AI) + upload to Garmin
- frontend/ → React SPA, consumes API, renders UI

## Garmin Integration
- Auth: garth library (email/password based, NOT OAuth)
- ALL Garmin API calls MUST go through `garmin_api_call()` in garth_client.py
- Never call garth.connectapi() directly from routers
- Rate limit: 2s minimum between calls, exponential backoff on 429
- Tokens: GARTH_TOKENS env var (base64 bundle) on Railway, /tmp/garth_tokens on disk
- On container restart: tokens must be re-injected via POST /garmin/auth/inject-tokens
- Upload workouts: use async_upload_workout() which wraps garminconnect.Garmin client

## Frontend Design System
- Dark theme, glassmorphism cards (G component in ui.jsx)
- Font: monospace everywhere, uppercase labels at 11px
- Colors: amber-500 primary, slate-400 secondary, cyan TSB/form, red fatigue
- Zone colors: Z1=gray(#475569), Z2=blue(#3b82f6), Z3=green(#22c55e), Z4=amber(#f59e0b), Z5=orange(#f97316), Z6=red(#ef4444), Z7=purple(#8b5cf6)
- Cards: rounded-[14px], backdrop-blur(12px), 1px border rgba(148,163,184,0.08)
- Italian copy for all user-facing text

## Deployment
- Backend: Railway (Dockerfile in backend/, auto-deploys on push to master)
- Frontend: Vercel (from frontend/ dir, `cd frontend && npx vercel --prod --yes`)
- After Railway restart: inject fresh Garmin tokens via /garmin/auth/inject-tokens

## When Working On a Module
1. Read the relevant contract(s) in contracts/
2. Check ARCHITECTURE.md section for that module
3. Use tests/test_data.json for development
4. Commit with module prefix: "backend: fix workout upload"
5. Run tests before committing: `cd backend && python3 -m pytest tests/ -v`

## gstack

Use the /browse skill from gstack for all web browsing.
If gstack skills aren't working, run: cd .claude/skills/gstack && ./setup
