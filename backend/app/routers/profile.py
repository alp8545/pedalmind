from fastapi import APIRouter
router = APIRouter()

@router.get("")
async def get_profile():
    return {"message": "not implemented"}

@router.put("")
async def update_profile():
    return {"message": "not implemented"}
