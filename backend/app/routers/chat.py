from fastapi import APIRouter
router = APIRouter()

@router.get("/conversations")
async def list_conversations():
    return {"conversations": []}

@router.post("/conversations")
async def create_conversation():
    return {"message": "not implemented"}

@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str):
    return {"message": "not implemented"}

@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    return {"messages": []}
