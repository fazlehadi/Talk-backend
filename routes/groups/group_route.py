from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from helpers.utils.websocket_connection_manager import websocket_connection_manager
from helpers.utils.redis_pubsub import publish_message
from helpers.utils.generate_unique_id import generate_unique_id
from helpers.middleware.authentication import validate_token, validate_token_for_websockets
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi.responses import JSONResponse
from core.database import get_db, db
from bson import ObjectId
from schemas.groups.group_schema import Group, GroupCreate, GroupUpdate
from core.redis import redis
import json
from datetime import datetime
from uuid import uuid4

router = APIRouter()

async def get_message_sequence_plus_one(group_id: str) -> int:
  redis_key = f"group:{group_id}:messages"
  last_message = await redis.lindex(redis_key, -1)  # Get the last message
  if last_message:
    last_message = json.loads(last_message)
    return last_message['message_sequence'] + 1
  else:
    return 0  # If no messages exist, start with sequence 0

@router.websocket("/continue-group-chat/{group_id}")
async def websocket_group_chat_endpoint(websocket: WebSocket, group_id: str):
  auth_token = websocket.query_params.get('authToken')
  user_id = await validate_token_for_websockets(websocket, auth_token)

  if user_id is None:
    await websocket.close(code=4000, reason="Invalid token")
    return

  group_id = ObjectId(group_id)

  # Check if the user is a participant in the group
  group = await db.groups.find_one({"_id": group_id})

  if group:
    if user_id not in group["participants"]:
      await websocket.close(code=4000, reason="User is not a participant in the group")
      return

    websocket_id = str(uuid4())
    await websocket_connection_manager.connect(websocket, str(group_id), websocket_id)
    # await store_connection(group_id, websocket_id, user_id, is_group=True)
  else:
    await websocket.close(code=4000, reason="Group not found")
    return

  try:
    while True:
      data = json.loads(await websocket.receive_text())
      message_data = {
        "id": generate_unique_id(), # generates 6 bit random id
        "sender_id": str(user_id),
        "reply_to_id": data['reply_to_id'] if data['reply_to_id'] else None,
        "content": data['content'],
        "message_sequence": await get_message_sequence_plus_one(str(group_id)),
        "created_at": datetime.now().isoformat()
      }

      await redis.rpush(f"group:{group_id}:messages", json.dumps(message_data))
      await publish_message(group_id, message_data, is_group=True)
  except WebSocketDisconnect:
    websocket_connection_manager.disconnect(websocket, group_id)
    # await remove_connection(group_id, websocket_id, is_group=True)
  except Exception as e:
    print(f"Unexpected error: {e}")
    await websocket.close(code=1011, reason=str(e))

@router.post("/create-group")
async def create_group(
  req_body: GroupCreate,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  # Ensure participants is a list and convert to ObjectId
  if not isinstance(req_body.participants, list):
    return JSONResponse(status_code=400, content={"error": "Participants should be a list"})

  req_body.participants = [ObjectId(participant) for participant in req_body.participants]

  if user_id in req_body.participants:
    return JSONResponse(status_code=400, content={"error": "Current user cannot be added as a participant"})

  # Add the current user to the participants list
  req_body.participants.append(user_id)

  # Validate if the participants are actual users
  users_cursor = db.users.find({"_id": {"$in": req_body.participants}})
  valid_users = [user async for user in users_cursor]
  if len(valid_users) != len(req_body.participants):
    return JSONResponse(status_code=400, content={"error": "Some participants are not valid users"})

  try:
    new_group = Group(
      group_name=req_body.group_name,
      group_image=req_body.group_image,
      group_description=req_body.group_description,
      participants=req_body.participants,
      group_admin=user_id
    )

    # Insert the new group into the database
    group_insert_result = await db.groups.insert_one(new_group.dict())
    group_id = group_insert_result.inserted_id

    group_info = {
      "group_id": group_id
    }

    # Update users' inbox.groups field
    await db.users.update_many(
      {"_id": {"$in": req_body.participants}},
      {"$addToSet": {"inbox.groups": group_info}}
    )

    return JSONResponse(status_code=201, content={"success": "Group created successfully"})
  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.put("/update-group/{group_id}")
async def update_group(
  group_id: str,
  req_body: GroupUpdate,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    update_fields = {}
    group_id = ObjectId(group_id)

    # Fetch the existing group chat
    existing_group = await db.groups.find_one({"_id": group_id})
    if not existing_group:
      return JSONResponse(status_code=404, content={"error": "Group chat not found"})

    # Check if the current user is the group admin
    if existing_group.get("group_admin") != user_id:
      return JSONResponse(status_code=403, content={"error": "Only the group admin can update the group chat"})

    # Ensure participants is a list and convert to ObjectId
    if req_body.participants is not None:
      req_body.participants = [ObjectId(participant) for participant in req_body.participants]

      # Validate if the new participants are actual users
      users_cursor = db.users.find({"_id": {"$in": req_body.participants}})
      valid_users = [user async for user in users_cursor]
      if len(valid_users) != len(req_body.participants):
        return JSONResponse(status_code=400, content={"error": "Some participants are not valid users"})

      # Merge new participants with existing participants
      new_participants = set(req_body.participants)
      existing_participants = set(existing_group.get("participants", []))
      participants_to_add = new_participants - existing_participants
      participants_to_remove = existing_participants - new_participants
      update_fields["participants"] = list(existing_participants | new_participants - participants_to_remove)

    if req_body.group_name:
      update_fields["group_name"] = req_body.group_name

    if req_body.group_image:
      update_fields["group_image"] = req_body.group_image

    if req_body.group_description:
      update_fields["group_description"] = req_body.group_description

    if not update_fields:
      return JSONResponse(status_code=400, content={"error": "No valid participants or group details provided to update"})

    # Ensure the chat does not end up with no participants
    if "participants" in update_fields and len(update_fields["participants"]) == 0:
      return JSONResponse(status_code=400, content={"error": "Cannot reduce group chat to no participants"})

    # Perform the update
    await db.groups.update_one(
      {"_id": group_id},
      {"$set": update_fields}
    )

    # Update group info in the users' inbox.groups field
    group_info = {
      "group_id": group_id
    }

    # Add group info for new participants
    if participants_to_add:
      await db.users.update_many(
        {"_id": {"$in": list(participants_to_add)}},
        {"$addToSet": {"inbox.groups": group_info}}
      )

    # Remove group info for removed participants
    if participants_to_remove:
      await db.users.update_many(
        {"_id": {"$in": list(participants_to_remove)}},
        {"$pull": {"inbox.groups": {"group_id": str(group_id)}}}
      )

    return JSONResponse(status_code=200, content={"success": "Group updated successfully"})
  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.delete("/delete-group/{group_id}")
async def delete_group(
  group_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    group_id = ObjectId(group_id)

    # Fetch the existing group chat
    existing_group = await db.groups.find_one({"_id": group_id})
    if not existing_group:
      return JSONResponse(status_code=404, content={"error": "Group chat not found"})

    # Check if the current user is the group admin
    if existing_group.get("group_admin") != user_id:
      return JSONResponse(status_code=403, content={"error": "Only the group admin can delete the group chat"})

    # Perform the deletion
    await db.groups.delete_one({"_id": group_id})

    # delete all the message buckets of the group
    await db.messages.delete_many({"group_id": group_id})

    # Remove the group info from all participants' chats field
    await db.users.update_many(
      {"_id": {"$in": existing_group["participants"]}},
      {"$pull": {"inbox.groups": {"group_id": group_id}}}
    )

    return JSONResponse(status_code=200, content={"success": "Group deleted successfully"})
  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e

@router.delete("/leave-group/{group_id}")
async def leave_group(
  group_id: str,
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: str = Depends(validate_token)
):
  try:
    group_id = ObjectId(group_id)

    # Fetch the existing group chat
    existing_group = await db.groups.find_one({"_id": group_id})
    if not existing_group:
      return JSONResponse(status_code=404, content={"error": "Group chat not found"})

    # Check if the user is a participant
    if user_id not in existing_group.get("participants", []):
      return JSONResponse(status_code=403, content={"error": "User is not a participant of this group"})

    # Check if the user is the group admin
    if existing_group.get("group_admin") == user_id:
      # If the user is the group admin, check the number of remaining participants
      remaining_participants = existing_group.get("participants", [])
      remaining_participants.remove(user_id)
      if len(remaining_participants) > 0:
        return JSONResponse(status_code=403, content={"error": "Group admin cannot leave the group if there are other participants remaining"})

    # Remove the user from the group's participants list
    await db.groups.update_one(
      {"_id": group_id},
      {"$pull": {"participants": user_id}}
    )

    # If the user was the group admin and they are the only participant left, delete the group
    group = await db.groups.find_one({"_id": group_id})
    if group and group.get("group_admin") == user_id and len(group.get("participants", [])) == 0:
      await db.groups.delete_one({"_id": group_id})
      return JSONResponse(status_code=200, content={"success": "Group deleted successfully"})

    # Remove the group info from the user's inbox.groups field
    await db.users.update_one(
      {"_id": user_id},
      {"$pull": {"inbox.groups": {"id": group_id}}}
    )

    return JSONResponse(status_code=200, content={"success": "Successfully left the group"})
  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e
