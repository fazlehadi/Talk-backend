from pydantic_settings import BaseSettings

class Settings(BaseSettings):
  DATABASE_CONNECTION_URL: str
  REDIS_CONNECTION_URL: str
  JWT_SECRET_KEY: str
  JWT_ALGORITHM: str
  JWT_TOKEN_LIFETIME: int
  CLOUDINARY_CLOUD_NAME: str
  CLOUDINARY_API_KEY: int
  CLOUDINARY_API_SECRET: str

  class Config:
    env_file = ".env"

settings = Settings()
