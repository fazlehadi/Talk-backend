from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from helpers.utils.websocket_connection_manager import websocket_connection_manager
from helpers.utils.redis_pubsub import publish_message
from helpers.middleware.authentication import validate_token, validate_token_for_websockets
from helpers.utils.convert_to_json_serializeble_object import convert_to_json_serializeble_object
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from core.database import get_db, db
from core.redis import redis
from bson import ObjectId
from datetime import datetime
import json
from uuid import uuid4

router = APIRouter()

async def get_message_sequence_plus_one(chat_id: str) -> int:
  redis_key = f"chat:{chat_id}:messages"
  last_message = await redis.lindex(redis_key, -1)  # Get the last message
  if last_message:
    last_message = json.loads(last_message)
    return last_message['message_sequence'] + 1
  else:
    return 0  # If no messages exist, start with sequence 0

@router.websocket("/continue-chat/{chat_id}")
async def websocket_chat_endpoint(websocket: WebSocket, chat_id: str):
  auth_token = websocket.query_params.get('authToken')
  user_id = await validate_token_for_websockets(websocket, auth_token)

  if user_id is None:
    await websocket.close(code=4000, reason="Invalid token")
    return

  chat_id = ObjectId(chat_id)

  chat = await db.chats.find_one({"_id": chat_id}) # checks if the chat is in the database or not
  participant_id = next(participant_id for participant_id in chat['participants'] if participant_id != user_id)

  if not chat or (user_id and participant_id not in chat['participants']):
    await websocket.close(code=4000, reason="Chat not found or user is not in the chat")
    return

  websocket_id = str(uuid4())

  await websocket_connection_manager.connect(websocket, str(chat_id), websocket_id)

  try:
    while True:
      data = json.loads(await websocket.receive_text())

      # Handle new message creation
      message_data = {
        "id": data['id'],
        "sender_id": str(user_id),
        "reply_to_id": data['reply_to_id'] if data['reply_to_id'] else None,
        "reply_to_content": data['reply_to_content'] if data['reply_to_content'] else None,
        "content": data['content'],
        "message_sequence": await get_message_sequence_plus_one(str(chat_id)),
        "seen": False,
        "seen_timestamp": None,
        "action": data['action'],
        "created_at": data['created_at'],
      }

      await redis.rpush(f"chat:{chat_id}:messages", json.dumps(message_data))
      await publish_message(chat_id, message_data)

      last_message_data = {
        "content": data['content'],
        "sent_by": str(user_id),
        "created_at": data['created_at']
      }

      # Update for the user who sent the message
      await db.users.update_one(
        {"_id": user_id, "inbox.chats.chat_id": chat_id},
        {"$set": {
          "inbox.chats.$.last_message": last_message_data
        }}
      )

      # Update for the participant receiving the message
      await db.users.update_one(
        {"_id": participant_id, "inbox.chats.chat_id": chat_id},
        {"$set": {
          "inbox.chats.$.last_message": last_message_data
        }}
      )

  except WebSocketDisconnect:
    websocket_connection_manager.disconnect(websocket, chat_id)
  except Exception as e:
    print(f"Unexpected error: {e}")
    await websocket.close(code=1011, reason=str(e))

@router.post("/mark-as-seen/{chat_id}/{seen_timestamp}")
async def mark_as_seen(
  chat_id: str,
  seen_timestamp: str,
  user_id: str = Depends(validate_token),
  db: AsyncIOMotorDatabase = Depends(get_db)
):
  try:
    # Validate user’s participation in chat
    chat = await db.chats.find_one(
      {"_id": ObjectId(chat_id), "participants": user_id},
      {"_id": 1}
    )
    if not chat:
      return JSONResponse(status_code=404, content={"error": "Chat not found or Unauthorized"})

    redis_chat_key = f"chat:{chat_id}:messages"
    unseen_flag_key = f"chat:{chat_id}:unseen_in_mongo"

    # Step 1: Check for unseen_in_mongo flag, update MongoDB if it’s set
    if await redis.exists(unseen_flag_key):
      await db.messages.update_many(
        {
          "chat_id": chat_id,
          "messages": {
            "$elemMatch": {
              "sender_id": {"$ne": user_id},
              "seen": False
            }
          }
        },
        {
          "$set": {
            "messages.$[msg].seen": True,
            "messages.$[msg].seen_timestamp": seen_timestamp
          }
        },
        array_filters=[{"msg.sender_id": {"$ne": user_id}, "msg.seen": False}]
      )
      # Clear the unseen flag
      await redis.delete(unseen_flag_key)

    # Step 2: Update Redis messages as seen
    messages_in_redis = await redis.lrange(redis_chat_key, 0, -1)

    for index, msg in enumerate(messages_in_redis):
      message_data = json.loads(msg)
      if (
        message_data["sender_id"] != user_id and
        not message_data.get("seen", False)
      ):
        # Update message as seen
        message_data["seen"] = True
        message_data["seen_timestamp"] = seen_timestamp
        await redis.lset(redis_chat_key, index, json.dumps(message_data))

    # Optionally broadcast the seen event if needed
    await publish_message(
      chat_id,
      {"action": "seen", "seen_timestamp": seen_timestamp}
    )

    return JSONResponse(status_code=200, content={"success": "Messages marked as seen"})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.post("/create-chat/{participant_id}")
async def create_chat(
  participant_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  participant_id = ObjectId(participant_id)

  if participant_id == user_id:
    return JSONResponse(status_code=400, content={"error": "Participant ID cannot be the same as user ID"})

  # Validate if the participants are actual users
  validate_participant = await db.users.find_one({"_id": participant_id})

  # validate participant and return error if not successfull
  if not validate_participant:
    return JSONResponse(status_code=400, content={"error": "Participant is not a valid user"})

  # Check if the user has deleted the chat with the specific participant_id
  has_user_deleted_chat = await db.users.find_one(
    {
      "_id": user_id,
      "inbox.chats": {
        "$elemMatch": {
          "participant_id": participant_id,
          "deleted": True
        }
      }
    }
  )

  try:
    if has_user_deleted_chat: # we check if the chat is already created and is also deleted or not
      '''
      e.g:
      inbox: {
        chats: [ this is what the chat object looks like and we can get the chat object using the participant_id and than easily get the chat_id also from it
          {
            chat_id
            participant_id
            deleted: true or the field is not present at all
          },
          {
            chat_id
            participant_id
            deleted: true or the field is not present at all
          },
          ...
        ]
      }
      '''

      await db.users.update_one( # remove the deleted mark from the current user chat object in chats array which is in the inbox object
        {
          "_id": user_id,
          "inbox.chats.participant_id": participant_id
        },
        {
          "$unset": {"inbox.chats.$.deleted": ""}
        }
      )

      return JSONResponse(status_code=200, content={"success": "User added in chat successfully"})

    else: # if the current user hasn't deleted the chat than this else block will be run
      does_chat_exist = await db.chats.find_one({"participants": {"$all": [user_id, participant_id]}})

      if does_chat_exist:
        # Ensure the '_id' is retrieved properly
        return JSONResponse(status_code=409, content={"chat_id": str(does_chat_exist["_id"])})

      # make new chat
      new_chat = await db.chats.insert_one({
        "participants": [user_id, participant_id],
        "created_at": datetime.utcnow().isoformat()
      })

      # Add chat to user A inbox.chats array
      await db.users.update_one(
        {"_id": user_id},
        {"$addToSet": {
            "inbox.chats": {
              "chat_id": new_chat.inserted_id,
              "participant_id": participant_id
            }
          }
        }
      )

      # Add chat to participant B inbox.chats array
      await db.users.update_one(
        {"_id": participant_id},
        {"$addToSet": {
            "inbox.chats": {
              "chat_id": new_chat.inserted_id,
              "participant_id": user_id
            }
          }
        }
      )

      return JSONResponse(status_code=201, content={"success": str(new_chat.inserted_id)})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.delete("/unsend-recent-message/{chat_id}/{message_id}")
async def unsend_recent_message(
  chat_id: str,
  message_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    chat_id = ObjectId(chat_id)
    chat_key = f"chat:{chat_id}:messages"

    # Fetch all messages in the chat
    messages = await redis.lrange(chat_key, 0, -1)

    # Variable to track if the message was removed from Redis
    removed_from_redis = 0

    # Find and remove the message with the given message_id
    # Collect updates to be made
    updates = []
    for index, message in enumerate(messages):
      message_data = json.loads(message)

      if message_data['id'] == message_id and message_data['sender_id'] == str(user_id):
        # Mark the message for deletion
        updates.append((index, None))
      elif message_data['reply_to_id'] == message_id:
        # Update reply_to_id and reply_to_content to None
        message_data['reply_to_id'] = None
        message_data['reply_to_content'] = None
        updates.append((index, json.dumps(message_data)))

    # Apply updates
    for index, new_message in updates:
      if new_message is None:
        # Remove the message by setting a unique placeholder
        removed_from_redis = await redis.lset(chat_key, index, "__deleted__")
      else:
        # Update the message in place
        removed_from_redis = await redis.lset(chat_key, index, new_message)

    # Step 3: Clean up placeholders
    await redis.lrem(chat_key, 0, "__deleted__")

    if removed_from_redis > 0:
      message_deletion_data = {
        "action": "delete",
        "message_id": message_id
      }

      await publish_message(chat_id, message_deletion_data)

      # If we successfully removed the message, proceed with MongoDB updates
      chat_data = await db.chats.find_one({"_id": chat_id})

      # Get the participant other than the user who sent the message
      participant_id = next((participant for participant in chat_data['participants'] if participant != ObjectId(user_id)), None)

      if participant_id is None:
        return JSONResponse(status_code=404, content={"error": "Participant not found"})

      # Fetch all messages in the chat
      messages = await redis.lrange(chat_key, 0, -1)

      # Update last message in MongoDB (for both sender and recipient)
      if len(messages) >= 1:
        last_message_data = json.loads(messages[-1])  # Parse the second last message as the new "last message"
        last_message_update = {
          "content": last_message_data['content'],
          "sent_by": last_message_data['sender_id'],
          "created_at": last_message_data['created_at']
        }
      else:
        # No more messages left in the chat after deletion
        last_message_update = {"content": "", "sent_by": "", "created_at": None}

      # Update the last message for the user who sent the message
      await db.users.update_one(
        {"_id": ObjectId(user_id), "inbox.chats.chat_id": chat_id},
        {"$set": {
          "inbox.chats.$.last_message": last_message_update
        }}
      )

      # Update the last message for the participant
      await db.users.update_one(
        {"_id": participant_id, "inbox.chats.chat_id": chat_id},
        {"$set": {
          "inbox.chats.$.last_message": last_message_update
        }}
      )

      return JSONResponse(status_code=200, content={"success": "Message unsent successfully from redis"})
    else:
      return JSONResponse(status_code=404, content={"error": "Message not found in Redis"})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.delete("/unsend-older-message/{chat_id}/{message_id}/{message_bucket_sequence}")
async def unsend_older_message(
  chat_id: str,
  message_id: str,
  message_bucket_sequence: int,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    # Step 1: Remove the target message
    result = await db.messages.update_one(
      {
        "chat_id": chat_id,
        "message_bucket_sequence": message_bucket_sequence,
        "messages.id": message_id,
        "messages.sender_id": str(user_id)
      },
      {
        "$pull": {
          "messages": {"id": message_id}
        }
      }
    )

    # Check if any document was modified
    if result.modified_count == 0:
      raise HTTPException(
        status_code=404,
        detail="Message not found or you do not have permission to delete it"
      )

    # Step 2: Nullify reply_to_id and reply_to_content for messages referencing the deleted one
    await db.messages.update_many(
      {
        "chat_id": chat_id,
        "messages.reply_to_id": message_id
      },
      {
        "$set": {
          "messages.$[elem].reply_to_id": None,
          "messages.$[elem].reply_to_content": None
        }
      },
      array_filters=[{"elem.reply_to_id": message_id}]
    )

    message_deletion_data = {
      "action": "delete",
      "message_id": message_id
    }

    await publish_message(chat_id, message_deletion_data)

    return JSONResponse(status_code=200, content={"success": "Message unsent successfully from MongoDB"})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.get("/fetch-recent-chat/{chat_id}")
async def fetch_recent_chat(
  chat_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  chat_id = ObjectId(chat_id)

  try:
    chat = await db.chats.find_one({"_id": chat_id})

    if not chat:
      return JSONResponse(status_code=404, content={"error": "Chat not found"})

    if user_id not in chat['participants']:
      return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # Fetch messages from Redis
    redis_key = f"chat:{chat_id}:messages"
    messages = await redis.lrange(redis_key, 0, -1)
    messages = [json.loads(message) for message in messages]

    if not messages:  # Check if the messages list is empty
      return JSONResponse(status_code=404, content={"error": "No messages found"})

    return JSONResponse(status_code=200, content={"messages": messages})
  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.get("/fetch-older-chat/{chat_id}/{message_bucket_sequence}")
async def fetch_older_messages(
  chat_id: str,
  message_bucket_sequence: int,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  chat_id = ObjectId(chat_id)

  try:
    chat = await db.chats.find_one({"_id": chat_id})

    if not chat:
      return JSONResponse(status_code=404, content={"error": "Chat not found"})

    if user_id not in chat['participants']:
      return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # Fetch the latest message bucket to determine the range
    latest_bucket = await db.messages.find_one(
      {"chat_id": str(chat_id)},
      sort=[("message_bucket_sequence", -1)]
    )

    if not latest_bucket:
      return JSONResponse(status_code=404, content={"error": "No messages found"})

    # Subtract message_bucket_sequence from the latest one
    latest_sequence = latest_bucket['message_bucket_sequence']
    target_sequence = latest_sequence - message_bucket_sequence

    # Fetch the target older message bucket
    message_bucket = await db.messages.find_one({
      "chat_id": str(chat_id),
      "message_bucket_sequence": target_sequence
    })

    if not message_bucket:
      return JSONResponse(status_code=404, content={"error": "Older message bucket not found"})

    return JSONResponse(status_code=200, content={"bucket": convert_to_json_serializeble_object(message_bucket)})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.delete("/delete-chat/{chat_id}")
async def delete_chat(
  chat_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    chat_id = ObjectId(chat_id)

    # Fetch the existing chat
    chat = await db.chats.find_one({"_id": chat_id})

    # Check if the user is a participant
    if chat and user_id not in chat.get("participants", []):
      return JSONResponse(status_code=403, content={"error": "User is not a participant of this chat"})

    user_a = await db.users.find_one(
      {
        "_id": user_id,
        "inbox.chats": {
          "$elemMatch": {
            "chat_id": chat_id,
            "deleted": True
          }
        }
      },
      {
        "inbox.chats.$": 1  # Project only the matched element in the array
      }
    )
    participant_id = next(participant for participant in chat['participants'] if participant != user_id)
    user_b = await db.users.find_one(
      {
        "_id": participant_id,
        "inbox.chats": {
          "$elemMatch": {
            "chat_id": chat_id,
            "deleted": True
          }
        }
      },
      {
        "inbox.chats.$": 1  # Project only the matched element in the array
      }
    )

    if user_b and not user_a:
      # logic to remove the chat, messages, chat obj's, redis.
      await db.chats.delete_one({"_id": chat_id})

      await db.users.update_one(
        {
          "_id": user_id
        },
        {
          "$pull": {"inbox.chats": {"chat_id": chat_id}}
        }
      )

      await db.users.update_one(
        {
          "_id": participant_id
        },
        {
          "$pull": {"inbox.chats": {"chat_id": chat_id}}
        }
      )

      await db.messages.delete_many({"chat_id": chat_id})

      await redis.delete(f"chat:{chat_id}:messages")

      return JSONResponse(status_code=200, content={"success": "Chat deleted successfully"})
    elif not user_b:
      await db.users.update_one(
        {
          "_id": user_id,
          "inbox.chats.chat_id": chat_id
        },
        {
          "$set": {"inbox.chats.$.deleted": True}  # Adds the 'deleted' field with a value of True
        }
      )

      return JSONResponse(status_code=200, content={"success": "Chat marked as deleted for the user"})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e
