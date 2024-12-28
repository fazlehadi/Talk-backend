import uvicorn
import logging
from routes.main import app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
  host = "0.0.0.0"
  port = 8000
  logger.info(f"Starting server at http://{host}:{port}")
  uvicorn.run(app, host=host, port=port)
