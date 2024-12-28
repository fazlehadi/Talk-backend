from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from background_tasks.batch_save_messages import batch_save_messages
from helpers.utils.redis_pubsub import redis_subscriber
from .users.user_route import router as user_router
from .chats.chat_route import router as chat_router
from .groups.group_route import router as group_router
from .upload_image.upload_image_route import router as upload_image_router
from .search.search_route import router as search_router

app = FastAPI()

origins = [
  "http://localhost:5173",  # Allow requests from your frontend domain
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],  # Allow all HTTP methods
  allow_headers=["*"],  # Allow all headers
)

@app.on_event("startup")
async def startup_event():
  asyncio.create_task(batch_save_messages())
  asyncio.create_task(redis_subscriber())

@app.get('/')
async def get_homeage():
  return "meow homeage"

app.include_router(user_router, prefix="/api/user", tags=["users"])
app.include_router(chat_router, prefix="/api/chat", tags=["chats"])
app.include_router(group_router, prefix="/api/group", tags=["groups"])
app.include_router(upload_image_router, prefix="/api/upload", tags=["upload-image"])
app.include_router(search_router, prefix="/api/search", tags=["search"])
