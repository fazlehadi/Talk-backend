from pydantic import BaseModel, Field, constr, root_validator, EmailStr
from datetime import datetime
from typing import List, Dict, Optional, Any
from bson import ObjectId

class UserCreate(BaseModel):
  username: constr(min_length=3, max_length=16)
  email: EmailStr
  password: constr(min_length=8, max_length=16)

  class Config:
    arbitrary_types_allowed = True

class UserLogin(BaseModel):
  username: constr(min_length=3, max_length=16)
  password: constr(min_length=8, max_length=16)

  class Config:
    arbitrary_types_allowed = True

class UserUpdate(BaseModel):
  username: Optional[constr(min_length=3, max_length=16)] = None
  email: Optional[EmailStr] = None
  description: Optional[constr(max_length=60)] = None
  old_password: Optional[constr(min_length=8, max_length=16)] = None
  new_password: Optional[constr(min_length=8, max_length=16)] = None
  profile_image: Optional[str] = None

  @root_validator(pre=True)
  def check_at_least_one_field(cls, values):
    if not any(values.values()):
      raise ValueError('At least one field must be provided')

    if 'new_password' in values or 'old_password' in values:
      if values.get('new_password') is None or values.get('old_password') is None:
        raise ValueError('Both new_password and old_password must be provided when changing password')

    return values

  class Config:
    arbitrary_types_allowed = True

class User(BaseModel):
  username: str
  email: str
  password: str
  description: Optional[str] = None
  status: Optional[str] = None
  created_at: datetime = Field(default_factory=datetime.utcnow)
  profile_image: Optional[str] = None  # URL or path to profile picture
  inbox: Dict[str, List[Dict[str, Any]]] = Field(
    default_factory=lambda: {"chats": [], "groups": []}
  )

  class Config:
    arbitrary_types_allowed = True
