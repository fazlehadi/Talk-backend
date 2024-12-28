from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from bson import ObjectId

class Chat(BaseModel):
  participants: List[ObjectId]
  created_at: datetime = Field(default_factory=datetime.utcnow)

  class Config:
    arbitrary_types_allowed = True
