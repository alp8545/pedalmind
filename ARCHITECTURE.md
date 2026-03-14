# PedalMind — Architecture Document

> **Status**: Pre-MVP | **Last updated**: 2026-03-14
> This file is the single source of truth for the system design.

## 1. Vision
PedalMind transforms Garmin cycling data into AI-powered coaching insights.
User connects Garmin, rides sync and get analyzed automatically,
and they chat with an AI that understands their full training history.

## 2. System Overview
Frontend (React SPA) → Backend (FastAPI) → AI Engine → Anthropic API
Backend also connects to: Garmin Sync worker → Garmin Connect API (OAuth 2.0 PKCE)
Storage: PostgreSQL + S3/Minio

## 3. Modules

### 3.1 garmin_sync/ — Garmin Data Ingestion
- Responsibility: OAuth flow, activity sync, .FIT file download and parsing
- Input: Garmin OAuth tokens, user_id
- Output: RideData (see contracts/ride_data.json)
- Key deps: garminconnect library (v0.2.38), fitparse
- Runs as background worker, not in request path

### 3.2 backend/ — API Server (FastAPI)
- User auth, REST API, serves frontend, orchestrates modules
- Key deps: FastAPI, SQLAlchemy, Pydantic, python-jose (JWT)
- Database: PostgreSQL via SQLAlchemy async

### 3.3 ai_engine/ — AI Analysis Pipeline
- Per-ride analysis, chat with training context
- Input: RideData + AthleteProfile
- Output: RideAnalysis (see contracts/ride_analysis.json)
- Model strategy: Haiku for per-ride analysis (~$0.001/ride), Sonnet for chat (~$0.01/query)
- CRITICAL: AI must ONLY cite data from the actual RideData payload

### 3.4 frontend/ — React SPA
- Pages: Login, Dashboard, Ride Detail, Chat, Settings
- Key deps: React, Tailwind CSS, Recharts

### 3.5 contracts/ — Interface Definitions
- JSON Schema files defining data structures between modules
- These are the law: change contract first, then update code

## 4. Data Flows

### New Ride:
1. Garmin push/poll detects new activity
2. garmin_sync downloads .FIT, parses to RideData JSON
3. Stored in DB + S3, triggers ai_engine analysis (Haiku)
4. RideAnalysis stored in DB, shown on frontend

### Chat:
1. User sends message
2. Backend loads athlete profile + last N rides + analyses
3. ai_engine calls Sonnet with structured prompt
4. Response streamed via SSE

## 5. Database Schema (PostgreSQL)
Tables: users, athlete_profiles, rides, ride_analyses, chat_conversations, chat_messages

## 6. API Endpoints
Auth: POST /api/auth/register, /login, GET /garmin/connect, /garmin/callback
Profile: GET/PUT /api/profile
Rides: GET /api/rides, GET /api/rides/:id, POST /api/rides/:id/reanalyze
Chat: GET/POST /api/chat/conversations, POST /:id/messages, GET /:id/messages
Sync: POST /api/sync/trigger, GET /api/sync/status

## 7. Config
All via environment variables — see backend/.env.example

## 8. Development Rules
1. Read this file first in every Claude Code session
2. Contracts are sacred — change contract first, then code
3. No hard-coded athlete data — everything from DB/config
4. Test each module independently
5. Git commits per module: "garmin_sync: add FIT parsing"
6. Italian comments fine — code, variables, docs in English
7. Typing everywhere — Pydantic models, type hints

## 9. Backlog (Priority Order)
1. Backend scaffolding (FastAPI + DB models + auth)
2. Garmin sync (FIT file parsing, reuse garmin_auto.py logic)
3. AI engine (ride analysis prompt + Haiku integration)
4. Frontend (React SPA with profile + ride list + chat)
5. Integration testing end-to-end
6. Deployment (Railway or Fly.io)
7. Beta launch prep (20-50 users)
