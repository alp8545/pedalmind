from fastapi import APIRouter
router = APIRouter()

@router.post("/trigger")
async def trigger_sync():
    return {"message": "not implemented"}

@router.get("/status")
async def sync_status():
    return {"last_sync": None, "pending": 0}
