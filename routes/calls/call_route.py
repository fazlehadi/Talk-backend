from bson import ObjectId
from schemas.calls.call_schema import SignalingMessage
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from helpers.utils.websocket_connection_manager import websocket_connection_manager
from helpers.utils.redis_pubsub_connection_manager import generate_websocket_id
from helpers.utils.redis_pubsub import publish_message
from helpers.middleware.authentication import validate_token_for_websockets
from fastapi import APIRouter
from core.database import db
import json

router = APIRouter()

@router.websocket("/call/{call_type}/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, call_type: str, chat_id: str):
  auth_token = websocket.query_params.get('authToken')
  user_id = await validate_token_for_websockets(websocket, auth_token)

  if user_id is None:
    await websocket.close(code=4000, reason="Invalid token")
    return

  chat_id = ObjectId(chat_id)

  chat = await db.chats.find_one({"_id": chat_id})

  if not chat:
    await websocket.close(code=4000, reason="Chat not found")
    return

  websocket_id = generate_websocket_id()
  await websocket_connection_manager.connect(websocket, str(chat_id), websocket_id)

  try:
    while True:
      data = json.loads(await websocket.receive_text())
      signaling_message = SignalingMessage.parse_raw(data)

      # Publish the signaling message to Redis
      await publish_message(chat_id, signaling_message.dict())
  except WebSocketDisconnect:
    await websocket_connection_manager.disconnect(websocket, chat_id)
  except Exception as e:
    print(f"Unexpected error: {e}")
    await websocket.close(code=1011, reason=str(e))
