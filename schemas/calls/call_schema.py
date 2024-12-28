from pydantic import BaseModel

class SignalingMessage(BaseModel):
  type: str  # e.g., 'offer', 'answer', 'ice-candidate'
  data: dict  # Contains the actual offer, answer, or ICE candidate
