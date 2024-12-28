from datetime import datetime
import asyncio
import json
from core.redis import redis
from core.database import db

async def get_last_message_bucket_sequence(group_or_chat_id: str, is_group: bool) -> int:
  latest_chat = await db.messages.find_one(
    {"group_id": group_or_chat_id} if is_group else {"chat_id": group_or_chat_id},
    sort=[("message_bucket_sequence", -1)]
  )
  if latest_chat and "message_bucket_sequence" in latest_chat:
    return latest_chat["message_bucket_sequence"] + 1
  else:
    return 0

async def batch_save_messages():
  while True:
    await asyncio.sleep(100)  # Run every 15 minutes

    # Process chat messages
    chat_keys = await redis.keys("chat:*")
    chat_keys = [key.decode('utf-8') for key in chat_keys]

    for key in chat_keys:
      chat_id = key.split(":")[1]
      messages = await redis.lrange(key, 0, -1)
      messages = [json.loads(message.decode('utf-8')) for message in messages]

      if len(messages) > 250:
        messages_to_save = messages[:-50]
        remaining_messages = messages[-50:]

        # Check for unseen messages in the batch
        has_unseen = any(msg for msg in messages_to_save if not msg.get("seen", False))

        # Update Redis with the unseen flag if needed
        if has_unseen:
          await redis.set(f"chat:{chat_id}:unseen_in_mongo", 1)

        # Move messages to MongoDB
        message_bucket_sequence = await get_last_message_bucket_sequence(chat_id, False)
        document = {
          "chat_id": chat_id,
          "messages": messages_to_save,
          "message_bucket_sequence": message_bucket_sequence,
          "created_at": datetime.now().isoformat()
        }
        await db.messages.insert_one(document)

        # Clear and repopulate Redis with remaining messages
        await redis.delete(key)
        for message in remaining_messages:
          await redis.rpush(f"chat:{chat_id}:messages", json.dumps(message))

    # Process group messages
    group_keys = await redis.keys("group:*")
    group_keys = [key.decode('utf-8') for key in group_keys]

    for key in group_keys:
      group_id = key.split(":")[1]
      messages = await redis.lrange(key, 0, -1)
      messages = [json.loads(message.decode('utf-8')) for message in messages]

      if len(messages) > 300:
        messages_to_save = messages[:-100]
        remaining_messages = messages[-100:]

        # Check for unseen messages in the batch
        has_unseen = any(msg for msg in messages_to_save if not msg.get("seen", False))

        # Update Redis with the unseen flag if needed
        if has_unseen:
          await redis.set(f"group:{group_id}:unseen_in_mongo", 1)

        # Move messages to MongoDB
        message_bucket_sequence = await get_last_message_bucket_sequence(group_id, True)
        document = {
          "group_id": group_id,
          "messages": messages_to_save,
          "message_bucket_sequence": message_bucket_sequence,
          "created_at": datetime.now().isoformat()
        }
        await db.messages.insert_one(document)

        # Clear and repopulate Redis with remaining messages
        await redis.delete(key)
        for message in remaining_messages:
          await redis.rpush(f"group:{group_id}:messages", json.dumps(message))
