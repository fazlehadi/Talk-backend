from bson import ObjectId
from datetime import datetime

def convert_to_json_serializeble_object(document):
  """Convert MongoDB document to JSON serializable format."""
  if isinstance(document, dict):
    return {k: convert_to_json_serializeble_object(v) for k, v in document.items()}
  elif isinstance(document, list):
    return [convert_to_json_serializeble_object(i) for i in document]
  elif isinstance(document, ObjectId):
    return str(document)
  elif isinstance(document, datetime):
    return document.isoformat()
  else:
    return document
