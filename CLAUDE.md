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
- Tests: pytest in backend/tests/ (32 tests). Run: `cd backend && python3 -m pytest tests/ -v`

## Module Boundaries
- garmin_sync/ → legacy FIT file parsing (unused, garmin_client.py imported by sync.py only)
- ai_engine/ → ride analysis prompts, chat context builder
- backend/ → FastAPI API server, orchestrates everything
  - backend/app/core/garth_client.py → ALL Garmin API calls go through garmin_api_call()
  - backend/app/services/trends.py → CTL/ATL/TSB computation (Coggan EWMA, cycling-only)
  - backend/app/services/ride_metrics.py → decoupling (Pw:Hr) + HR recovery computation
  - backend/app/routers/workout.py → workout interpret (AI) + upload to Garmin + weekly plan
  - backend/app/routers/trends.py → GET /api/trends endpoint
  - backend/app/routers/ride_records.py → GET /api/rides/{id}/records (second-by-second data)
- frontend/ → React SPA, consumes API, renders UI

## Garmin Integration — CRITICAL RULES
- Auth: garth library (email/password based, NOT OAuth)
- ALL Garmin API calls MUST go through `garmin_api_call()` in garth_client.py
- Never call garth.connectapi() directly from routers — always use the async wrappers
- `async_fetch_activities()`, `async_fetch_activity_details()` for sync
- `async_upload_workout()`, `async_schedule_workout()` for workout upload
- `garmin_api_call()` for any other Garmin endpoint
- All operations serialized through `_garmin_lock` (asyncio.Lock) — no race conditions
- All blocking calls wrapped in `asyncio.to_thread` — never block the event loop
- Rate limit: 2s minimum between calls, exponential backoff on 429/timeout/ConnectionError
- Auth backoff: exponential 5min → 10min → 20min → 1hr max on auth failures
- Never fallback to fresh login after a failed refresh (causes 429 on second endpoint)
- Tokens: GARTH_TOKENS env var (base64 bundle) on Railway, /tmp/garth_tokens on disk
- On container restart: tokens must be re-injected via POST /garmin/auth/inject-tokens (requires JWT auth)
- Upload workouts: DB-first architecture. Save to scheduled_workouts table FIRST, then attempt Garmin upload as best-effort. Never crash on Garmin failure.
- Garmin data sampling: ~25-40s intervals (NOT per-second). A 3h ride has ~277 records.

## Workout System
- POST /garmin/workout/interpret → AI interprets natural language to structured workout
- POST /garmin/workout/upload → saves to DB + uploads to Garmin (best-effort)
- GET /garmin/workout/week → returns current week's scheduled workouts (Mon-Sun)
- Interpreter prompt reads FTP/zones dynamically from AthleteProfile DB
- Garmin workout format: targetTypeId=2 for power, zoneNumber for zone targets, targetValueOne/Two for range. secondaryTargetType for cadence (key="cadence", NOT "cadence.zone")
- Workout upload uses raw dicts (not garminconnect Pydantic models) to support secondaryTargetType

## Training Metrics
- CTL/ATL/TSB: Coggan EWMA (42d/7d), cycling-only filter, seeded at 0
- Decoupling (Pw:Hr): splits ride in two halves, compares power/HR ratio. <3% ottimo, 3-5% buono, >5% da migliorare
- HR Recovery: finds hardest effort segment, measures HR drop at ~30s and ~60s after. >30bpm ottimo, 20-30 buono, <20 da migliorare
- POST /garmin/backfill-metrics: computes decoupling + HR recovery for existing rides
- Chat AI context includes decoupling and HR recovery for recent rides

## Frontend Design System
- Dark theme, glassmorphism cards (G component in ui.jsx)
- Font: monospace everywhere, uppercase labels at 11px
- Colors: amber-500 primary, slate-400 secondary, cyan TSB/form, red fatigue/HR
- Zone colors: Z1=gray(#475569), Z2=blue(#3b82f6), Z3=green(#22c55e), Z4=amber(#f59e0b), Z5=orange(#f97316), Z6=red(#ef4444), Z7=purple(#8b5cf6)
- Cards: rounded-[14px], backdrop-blur(12px), 1px border rgba(148,163,184,0.08)
- Italian copy for all user-facing text
- DESIGN.md exists with full design system documentation

## Frontend Components — Key Patterns
- Power blocks chart (ActivityDetailPage): time-proportional flex bars + HR curve SVG overlay + click-to-select popup
  - NEVER put overflow-hidden on the chart container (clips popups)
  - HR curve: cubic bezier SVG with Y clamped to chart area, overflow-hidden on SVG element only
  - Bars: width proportional to lap duration, height proportional to power
  - Click a bar: shows popup with metrics, other bars dim. Click outside to dismiss.
- Piano Settimanale (SeasonPage): workout cards with intensity-height step bars
  - Step bar height based on zone intensity (Z1=15%, Z7=100%)
  - Step bar width proportional to duration
  - Zone colors match the global ZONE_COLORS array
  - Week resets automatically: backend returns only current Mon-Sun window
- TrendsChart: Recharts LineChart with CTL/ATL/TSB, custom tooltip
- WeeklySummary: rolling 7-day card with TSS, CTL delta, form badge

## Deployment
- Backend: Railway (Dockerfile in backend/, auto-deploys on push to master)
- Frontend: Vercel (from frontend/ dir, `cd frontend && npx vercel --prod --yes && npx vercel deploy --prod --yes`)
- After Railway restart: inject fresh Garmin tokens via /garmin/auth/inject-tokens
- Vercel sometimes needs force deploy if CDN caches old bundle

## Learnings & Gotchas
- Garmin 429 is account-level, not IP-level. Can last hours. Only token refresh via connectapi.garmin.com may work when sso.garmin.com is blocked.
- garth.client is the HTTP session, NOT the garminconnect API client. For upload_workout/schedule_workout, create a garminconnect.Garmin() instance and assign garth.client to it.
- Pydantic models with required int fields crash when AI returns null. Always make AI-facing fields Optional with auto-computation fallback.
- DB pool_pre_ping=True is needed for Railway (containers sleep, connections go stale).
- Settings class needs `extra = "ignore"` to handle unknown .env vars without crashing.
- garmin_client.py (OAuth1 version) still exists, imported by sync.py. Don't delete without migrating sync.py first.

## When Working On a Module
1. Read the relevant contract(s) in contracts/
2. Check ARCHITECTURE.md section for that module
3. Use tests/test_data.json for development
4. Commit with module prefix: "backend: fix workout upload"
5. Run tests before committing: `cd backend && python3 -m pytest tests/ -v`
6. After frontend changes: build (`npm run build`) then deploy to Vercel

## gstack

Use the /browse skill from gstack for all web browsing.
If gstack skills aren't working, run: cd .claude/skills/gstack && ./setup
