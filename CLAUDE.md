# CLAUDE.md — Instructions for Claude Code

Read ARCHITECTURE.md first. It is the single source of truth.

## Project: PedalMind
AI-powered cycling training analytics.

## Key Rules
- All data contracts are in contracts/ — read them before modifying related code
- No hard-coded athlete data anywhere — everything from DB or .env
- Python typing + Pydantic models everywhere
- Backend: FastAPI + SQLAlchemy async + PostgreSQL
- Frontend: React + Tailwind + Recharts
- AI: Anthropic SDK, Haiku for analysis, Sonnet for chat
- Test data in tests/test_data.json (real cycling metrics)

## Module Boundaries
- garmin_sync/ → produces RideData JSON
- ai_engine/ → consumes RideData, produces RideAnalysis JSON
- backend/ → orchestrates everything, serves API
- frontend/ → consumes API, renders UI

## When Working On a Module
1. Read the relevant contract(s) in contracts/
2. Check ARCHITECTURE.md section for that module
3. Use tests/test_data.json for development
4. Commit with module prefix: "garmin_sync: add FIT parsing"
