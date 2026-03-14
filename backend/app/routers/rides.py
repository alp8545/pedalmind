from fastapi import APIRouter
router = APIRouter()

@router.get("")
async def list_rides():
    return {"rides": []}

@router.get("/{ride_id}")
async def get_ride(ride_id: str):
    return {"message": "not implemented"}

@router.post("/{ride_id}/reanalyze")
async def reanalyze_ride(ride_id: str):
    return {"message": "not implemented"}
