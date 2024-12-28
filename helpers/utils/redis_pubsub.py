from core.redis import redis
import json
from bson import ObjectId
from .websocket_connection_manager import websocket_connection_manager

async def publish_message(chat_or_group_id: ObjectId, message: dict, is_group: bool = False, is_call: bool = False):
  if is_group:
    await redis.publish(f'group:{chat_or_group_id}', json.dumps(message))
  elif is_call:
    await redis.publish(f'call:{chat_or_group_id}', json.dumps(message))
  else:
    await redis.publish(f'chat:{chat_or_group_id}', json.dumps(message))

async def redis_subscriber():
  pubsub = redis.pubsub()
  await pubsub.psubscribe('chat:*')  # Subscribe to all chat channels
  await pubsub.psubscribe('group:*')  # Subscribe to all group channels
  await pubsub.psubscribe('call:*')  # Subscribe to all call channels
  async for message in pubsub.listen():
    if message['type'] == 'pmessage':
      chat_or_group_id = message['channel'].decode('utf-8').split(':')[1]
      data = json.loads(message['data'])
      await websocket_connection_manager.broadcast(str(chat_or_group_id), data)
