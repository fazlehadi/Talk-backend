import jwt
from datetime import datetime, timedelta
from core.settings import settings

def generate_jwt_token(user):
  payload = {
    'user_id': str(user['_id']),
    'exp': datetime.utcnow() + timedelta(weeks=settings.JWT_TOKEN_LIFETIME),
    'iat': datetime.utcnow(),
    'token_type': 'access'
  }
  return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
