from schemas.users.user_schema import UserCreate, UserLogin, UserUpdate, User
from helpers.utils.generate_jwt_token import generate_jwt_token
from helpers.middleware.authentication import validate_token
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from core.database import get_db
from bson import ObjectId
from typing import Optional

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/fetch-user", status_code=200)
async def fetch_user(
    profile_id: Optional[str] = Query(
        None, description="ID of the user profile to fetch"
    ),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user_id: int = Depends(validate_token),
):
    try:
        # If profile_id is provided, fetch the summary of that user profile
        if profile_id:
            profile_id = ObjectId(profile_id)
            db_user = await db.users.find_one(
                {"_id": profile_id}, {"username": 1, "profile_image": 1}
            )

            if not db_user:
                return JSONResponse(
                    status_code=404, content={"error": "Profile not found"}
                )

            db_user["_id"] = str(db_user["_id"])
            return db_user

        # If profile_id is not provided, fetch the full user details for the authenticated user
        db_user = await db.users.find_one({"_id": user_id})

        if not db_user:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        del db_user["password"]
        db_user["_id"] = str(db_user["_id"])

        # Convert ObjectId fields in inbox.chats to strings
        if "inbox" in db_user and "chats" in db_user["inbox"]:
            for chat in db_user["inbox"]["chats"]:
                if "chat_id" in chat and isinstance(chat["chat_id"], ObjectId):
                    chat["chat_id"] = str(chat["chat_id"])
                if "participant_id" in chat and isinstance(
                    chat["participant_id"], ObjectId
                ):
                    chat["participant_id"] = str(chat["participant_id"])

        return db_user

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error",
        ) from e


@router.post("/signup")
async def signup(req_body: UserCreate, db: AsyncIOMotorDatabase = Depends(get_db)):
    # Check if user with the same username already exists
    existing_user = await db.users.find_one({"username": req_body.username})

    if existing_user:
        return JSONResponse(
            status_code=400, content={"error": "Username already registered"}
        )

    # Hash the password
    hashed_password = pwd_context.hash(req_body.password)

    # Create a new user instance
    new_user = User(
        username=req_body.username, email=req_body.email, password=hashed_password
    )

    await db.users.insert_one(new_user.dict())

    return JSONResponse(
        status_code=201, content={"success": "User created successfully"}
    )


@router.post("/login")
async def login(req_body: UserLogin, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        db_user = await db.users.find_one({"username": req_body.username})

        if not db_user:
            return JSONResponse(
                status_code=400, content={"error": "Invalid username or password"}
            )

        if not pwd_context.verify(req_body.password, db_user["password"]):
            # Password is incorrect
            return JSONResponse(
                status_code=400, content={"error": "Invalid username or password"}
            )

        token = generate_jwt_token(db_user)

        return JSONResponse(status_code=200, content={"access_token": token})
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error",
        ) from e


@router.put("/update-user")
async def update_user(
    req_body: UserUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user_id: str = Depends(validate_token),
):
    try:
        update_data = {}

        if req_body.username:
            update_data["username"] = req_body.username

        if req_body.email:
            update_data["email"] = req_body.email

        if req_body.old_password and req_body.new_password:
            db_user = await db.users.find_one({"_id": user_id})

            if pwd_context.verify(req_body.old_password, db_user["password"]):
                update_data["password"] = pwd_context.hash(req_body.new_password)
            else:
                return JSONResponse(
                    status_code=401, content={"error": "Incorrect old password"}
                )

        if req_body.description:
            update_data["description"] = req_body.description

        if req_body.profile_image:
            update_data["profile_image"] = req_body.profile_image

        if update_data:
            db_user = await db.users.find_one_and_update(
                {"_id": user_id}, {"$set": update_data}
            )

            if not db_user:
                return JSONResponse(
                    status_code=404, content={"error": "User not found"}
                )

        return JSONResponse(
            status_code=200, content={"success": "User updated successfully"}
        )
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error",
        ) from e
