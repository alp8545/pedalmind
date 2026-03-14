from fastapi import APIRouter
router = APIRouter()

@router.post("/register")
async def register():
    return {"message": "not implemented"}

@router.post("/login")
async def login():
    return {"message": "not implemented"}

@router.get("/garmin/connect")
async def garmin_connect():
    return {"message": "not implemented"}

@router.get("/garmin/callback")
async def garmin_callback():
    return {"message": "not implemented"}
