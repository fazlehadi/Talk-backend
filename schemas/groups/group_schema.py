from pydantic import BaseModel, Field, root_validator, constr
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

class GroupCreate(BaseModel):
  group_name: str
  group_image: Optional[str] = None
  group_description: Optional[constr(max_length=60)] = None
  participants: List[str]

  class Config:
    arbitrary_types_allowed = True

class GroupUpdate(BaseModel):
  group_name: Optional[str] = None
  group_image: Optional[str] = None
  group_description: Optional[constr(max_length=60)] = None
  participants: Optional[List[str]] = None

  @root_validator(pre=True)
  def check_at_least_one_field(cls, values):
    if not any(values.values()):
      raise ValueError('At least one field must be provided')
    return values

  class Config:
    arbitrary_types_allowed = True

class Group(BaseModel):
  group_admin: ObjectId
  group_name: str
  group_description: Optional[constr(max_length=60)] = None
  group_image: Optional[str] = None
  participants: List[ObjectId]
  created_at: datetime = Field(default_factory=datetime.utcnow)

  class Config:
    arbitrary_types_allowed = True
