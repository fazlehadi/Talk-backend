from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from typing import Dict, List
import json

class ConnectionManager:
  def __init__(self):
    # Dictionary to store active connections: {chat_id: [{websocket_id, websocket_obj}]}
    self.active_connections: Dict[str, List[Dict]] = {}

  async def connect(self, websocket: WebSocket, chat_or_group_id: str, websocket_id: str):
    try:
      # Accept the WebSocket connection
      await websocket.accept()

      # Initialize the connection list if this is the first connection for the chat_id
      if chat_or_group_id not in self.active_connections:
        self.active_connections[chat_or_group_id] = []

      # Append the connection details to active connections
      self.active_connections[chat_or_group_id].append({
        "id": websocket_id,
        "websocket_obj": websocket
      })
    except Exception:
      pass

  def disconnect(self, chat_or_group_id: str, websocket_id: str):
    """
    Disconnect a WebSocket by its ID, and remove from active connections.
    """
    if chat_or_group_id in self.active_connections:
      updated_connections = [
        conn for conn in self.active_connections[chat_or_group_id]
        if conn['id'] != websocket_id
      ]

      if updated_connections:
        self.active_connections[chat_or_group_id] = updated_connections
      else:
        del self.active_connections[chat_or_group_id]

  async def broadcast(self, chat_or_group_id: str, message: dict):
    """
    Send a message to all connected WebSockets for a given chat ID.
    """
    if chat_or_group_id in self.active_connections:
      for connection in self.active_connections[chat_or_group_id][:]:  # Copy list to safely remove disconnected websockets
        websocket = connection['websocket_obj']
        try:
          # Only send if WebSocket is connected
          if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps(message))
          else:
            # Remove the connection if it's no longer connected
            self.disconnect(chat_or_group_id, connection['id'])
        except WebSocketDisconnect:
          # If disconnected during send, clean up the connection
          self.disconnect(chat_or_group_id, connection['id'])
        except Exception:
          pass

websocket_connection_manager = ConnectionManager()
