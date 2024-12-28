from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security, WebSocket, Request, HTTPException, status
from datetime import datetime
from core.settings import settings
import jwt
from bson import ObjectId
from typing import Optional

async def validate_token(request: Request, credentials: HTTPAuthorizationCredentials = Security(HTTPBearer())):
  try:
    token = credentials.credentials

    # Decode the token to get the payload
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    # Check if the token is expired
    exp = datetime.fromtimestamp(payload['exp'])
    if exp < datetime.utcnow():
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is expired")  # Token is expired

    return ObjectId(payload['user_id'])
  except jwt.ExpiredSignatureError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is expired")  # Token is expired
  except jwt.InvalidTokenError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token invalid or not given")  # Token is invalid

async def validate_token_for_websockets(websocket: WebSocket, authToken: Optional[str] = None):
  # Extract the token from the query parameters
  token = authToken

  # If no token is provided, close the WebSocket with an error code
  if not token:
    await websocket.close(code=1008, reason="Access token is required")
    return None

  try:
    # Decode the token to get the payload
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    # Check if the token is expired
    exp = datetime.fromtimestamp(payload['exp'])
    if exp < datetime.utcnow():
      await websocket.close(code=1008, reason="Access token is expired")
      return None

    return ObjectId(payload['user_id'])
  except jwt.ExpiredSignatureError:
    await websocket.close(code=1008, reason="Access token is expired")
    return None
  except jwt.InvalidTokenError:
    await websocket.close(code=1008, reason="Access token invalid or not given")
    return None
