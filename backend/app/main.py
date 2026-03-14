from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, profile, rides, chat, sync

app = FastAPI(title="PedalMind API", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(rides.router, prefix="/api/rides", tags=["rides"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
