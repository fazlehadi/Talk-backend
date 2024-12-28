from helpers.middleware.authentication import validate_token
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from core.database import get_db
from bson import ObjectId

router = APIRouter()

def serialize_mongo_doc(doc):
    if doc:
        doc['_id'] = str(doc['_id'])  # Convert ObjectId to string
    return doc  

@router.get("/search-users", status_code=200)
async def search_users(
  db: AsyncIOMotorDatabase = Depends(get_db),
  user_id: int = Depends(validate_token),
  username: str = Query(..., description="Username to search for")
):
  try:
    # Construct the Atlas Search query using the vector search index
    search_pipeline = [
        {
          "$search": {
            "index": "username_idx",
            "compound": {
              "should": [
                {
                  "text": {
                    "query": username,
                    "path": "username",
                    "fuzzy": {
                      "maxEdits": 2  # Allow for more typos
                    }
                  }
                }
              ],
              "minimumShouldMatch": 1
            }
          }
        },
        {
          "$project": {
            "username": 1,
            "profile_image": 1
          }
        },
        {
          "$limit": 10
        }
      ]

    # Execute the search query
    cursor = db.users.aggregate(search_pipeline)
    results = await cursor.to_list(length=10)

    # Convert ObjectId to string for each document
    results = [serialize_mongo_doc(doc) for doc in results]

    return JSONResponse(content={"results": results})

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e