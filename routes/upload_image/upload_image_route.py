import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from helpers.middleware.authentication import validate_token
from core.settings import settings
from fastapi.responses import JSONResponse
from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from nanoid import generate

router = APIRouter()

# Configuration
cloudinary.config( 
  cloud_name = settings.CLOUDINARY_CLOUD_NAME, 
  api_key = settings.CLOUDINARY_API_KEY, 
  api_secret = settings.CLOUDINARY_API_SECRET,
  secure=True
)

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), user_id: str = Depends(validate_token)):
  try:
    # Upload the image
    upload_result = cloudinary.uploader.upload(file.file, public_id=generate(size=21))

    return JSONResponse(status_code=200, content={
      # "secure_url": upload_result["secure_url"],
      "url": upload_result["secure_url"]
    })

  except Exception as e:
    print(f"Error: {str(e)}")
    raise HTTPException(
      status_code=500,
      detail="Internal Server Error",
    ) from e