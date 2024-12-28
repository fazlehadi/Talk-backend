from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from bson import ObjectId

class MessageCreate(BaseModel):
  content: str
  reply_to_id: Optional[str] = None

class Message(BaseModel):
  content: str
  sender_id: ObjectId
  receiver_id: List[ObjectId]
  reply_to_id: Optional[ObjectId] = None
  chat_id: ObjectId
  created_at: datetime = datetime.utcnow()
  sequence: int

  class Config:
    arbitrary_types_allowed = True
