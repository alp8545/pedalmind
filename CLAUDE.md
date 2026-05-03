# CLAUDE.md — Instructions for Claude Code

Read ARCHITECTURE.md first. It is the single source of truth.

## Project: PedalMind
AI-powered cycling training analytics. Single-user (Alessio), deployed on **Render** (backend) + **Neon** (DB) + Vercel (frontend). Truly free-tier across the stack.

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
- Tokens: GARTH_TOKENS env var (base64 bundle) on Render, /tmp/garth_tokens on disk
- On container restart: tokens must be re-injected via POST /garmin/auth/inject-tokens (requires JWT auth) OR by updating GARTH_TOKENS env in Render dashboard (auto-restarts service)
- Token regen recipe (when sso.garmin.com is 429): use `garth.resume(old_dir) + garth.client.refresh_oauth2()` — connectapi.garmin.com accepts refresh even when SSO is blocked
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
- **Backend: Render** Free (Docker, Frankfurt) — `pedalmind.onrender.com` — service id `srv-d7riorjt6lks73fspdkg`
  - Auto-deploys on push to master (GitHub integration)
  - Config: `backend/render.yaml` (Blueprint). Secrets via Render dashboard, NEVER in repo.
  - Free-tier behavior: container sleeps after 15 min idle, ~30-50s cold start
  - Cold start mitigated by frontend `useEffect` warmup ping in `src/App.jsx` + GitHub Actions cron every 14 min (`.github/workflows/health-check.yml`)
- **Database: Neon** Free (Postgres 16, eu-central-1 Frankfurt) — project `super-glade-26059416`, org `org-lively-sea-25076563`
  - DSN: pooled endpoint `ep-calm-leaf-alv5njig-pooler.c-3.eu-central-1.aws.neon.tech`
  - Driver format: `postgresql+asyncpg://...?ssl=require` (NOT `sslmode=require`, asyncpg rejects it; NOT `ssl=true`, also rejected)
  - Scale-to-zero after ~5 min idle, +0.3-0.8s on first query (acceptable for personal use)
  - Storage 0.5 GB (room for years), compute 191h/mo (never sfored)
- **Frontend: Vercel** Hobby — `pedalmind-web.vercel.app`
  - From `frontend/` dir: `npm run build && npx vercel --prod --yes && npx vercel deploy --prod --yes`
  - `vercel.json` rewrites `/api/*` → Render backend
  - Vercel sometimes caches old bundle — use `vercel --prod --force` if needed
- **Health monitoring**: `.github/workflows/health-check.yml` cron `*/14 * * * *` doubles as keep-warm + verify
- After backend restart: inject fresh Garmin tokens via /garmin/auth/inject-tokens or by editing `GARTH_TOKENS` env var in Render (auto-restarts)

## Learnings & Gotchas
- Garmin 429 is account-level, not IP-level. Can last hours. Only token refresh via connectapi.garmin.com may work when sso.garmin.com is blocked.
- garth.client is the HTTP session, NOT the garminconnect API client. For upload_workout/schedule_workout, create a garminconnect.Garmin() instance and assign garth.client to it.
- Pydantic models with required int fields crash when AI returns null. Always make AI-facing fields Optional with auto-computation fallback.
- DB pool_pre_ping=True is needed for sleepy containers (Render free-tier sleeps; Neon scales to zero) — connections go stale.
- Settings class needs `extra = "ignore"` to handle unknown .env vars without crashing.
- garmin_client.py (OAuth1 version) still exists, imported by sync.py. Don't delete without migrating sync.py first.
- **Neon DSN with asyncpg**: must use `?ssl=require`. Both `?sslmode=require` (asyncpg rejects) and `?ssl=true` (asyncpg rejects) fail. Update `config.py` validator if you switch back to non-asyncpg drivers.
- **Render health check ≠ readiness**: `/api/health` must be liveness-only (no DB ping). Use `/api/health/ready` for DB pings, expose to monitoring only. If you bind Render's healthcheck to a DB-dependent endpoint, Neon cold-start will fail the check and trigger restart loops.
- **Lifespan must not block boot**: wrap DB migration in `asyncio.timeout()` and run `proactive_token_refresh()` as a fire-and-forget `asyncio.create_task`. Otherwise a Garmin or Neon hiccup at boot causes Render's healthcheck timeout.
- **Garmin auth backoff** kept at 1 min base / 10 min max (in `garth_client.py`). The original 5min/1hr was too aggressive for a personal app where the user retries quickly.
- **Backfill timeout**: `/garmin/backfill-metrics` has a hard 120s `asyncio.timeout` ceiling and default `limit=10`. Hits Render's request budget cleanly.
- **GitHub OAuth `workflow` scope**: `gh auth refresh -s workflow,repo` requires the device flow to fully complete (paste code, authorize, wait for "Authentication complete"). If you just close the browser, the token is unchanged. Fallback: PAT with `workflow,repo` scopes, one-shot push via `git push https://USER:PAT@github.com/...`, then revoke.

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
Note: on Ubuntu 24+ (AppArmor unprivileged-userns restrictions), set `CONTAINER=1` before invoking the browse binary so Playwright passes `--no-sandbox` to chrome-headless-shell.

## Migration history — Railway → Render+Neon (2026-05-03)

**Cause**: Railway's $5 trial credit ran out. Project + DB deleted by Railway after extended inactivity. Frontend Vercel was always up but `/api/*` rewrites returned 404 from a dead backend, making the app appear fully broken.

**Trigger**: Railway has had no recurring free tier since Aug 2023. Hobby plan = $5/mo minimum. Same for Fly.io since Oct 2024 ($5/mo Hobby min).

**New stack** (truly free for ever):
- Backend: Render Free (Docker, Frankfurt, sleeps 15min idle, 30-50s cold start)
- DB: Neon Free (Postgres 16, Frankfurt, scale-to-zero, 0.5GB, 191h compute/mo)
- Frontend: Vercel Hobby (unchanged, ~400MB/mo bandwidth on a 100GB limit)
- Anthropic: pay-per-use (separate, ~$5-10/mo for personal usage)

**Migration steps that were executed end-to-end**:
1. Refreshed Garmin tokens locally via `garth.resume + refresh_oauth2()` (sso.garmin.com was 429, but connectapi accepted refresh)
2. Created Neon project via API (need org_id; use `/users/me/organizations` first)
3. Deployed backend to Render via API (POST `/v1/services` with full env block) — first deploy took ~6 build polls (~3 min)
4. Updated `vercel.json` rewrite to point at `pedalmind.onrender.com`, redeployed Vercel
5. Backfill 1 year via `POST /api/garmin/sync/weeks/52` — 982s, 100 activities (63 road_biking, 19 running, 13 indoor_cycling, 3 cyclocross), 78 with power
6. Added `.github/workflows/health-check.yml` cron */14min for keep-warm + monitoring

**Code changes shipped during migration**:
- `backend/app/main.py`: split `/api/health` (liveness, no DB) vs `/api/health/ready` (DB ping)
- `backend/app/main.py`: lifespan wrapped in `asyncio.timeout(20)`, `proactive_token_refresh()` as fire-and-forget task
- `backend/app/core/garth_client.py`: backoff base 5min→1min, max 1h→10min
- `backend/app/routers/garmin_sync.py`: `backfill-metrics` default limit 30→10, hard 120s `asyncio.timeout`
- `backend/render.yaml`: NEW Blueprint (sync:false on all secrets)
- `frontend/src/App.jsx`: `useEffect` warmup ping `/api/health` on mount
- `frontend/vercel.json` + `frontend/.env.production`: Render URL
- `backend/railway.toml`: REMOVED

**Data lost in migration**: chat_conversations, chat_messages, ride_analyses (Anthropic-generated), athlete_profile (FTP/MaxHR/weight need re-entering via /settings). Garmin activities recoverable via re-sync.

**One-time setup post-migration the user must do** (or has done):
- Reset password from `/settings` (initial registration was `testpedal123!`)
- Re-enter athlete profile (FTP, MaxHR, weight) under /settings
- Revoke any API keys that were pasted in chat (Neon, Render, GitHub PAT)
