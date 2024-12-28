from motor.motor_asyncio import AsyncIOMotorClient
from .settings import settings

# Create the MongoDB client
client = AsyncIOMotorClient(settings.DATABASE_CONNECTION_URL)

# Get the database
db = client["talk-app-db"]

def get_db():
  return db
