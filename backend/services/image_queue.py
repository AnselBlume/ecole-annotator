from model import AnnotationState
from services.redis_client import r, acquire_lock
import json
from typing import Any, Optional

# Redis keys
IMAGE_QUEUE_KEY = 'image_queue'
IMAGE_QUEUE_LOCK_KEY = 'image_queue_lock'

# Load image metadata into Redis queue (one-time initialization)
def initialize_queue(annotation_state: AnnotationState):
    image_queue = [json.dumps(img.model_dump()) for img in annotation_state.unchecked.values()]

    if image_queue:
        r.delete(IMAGE_QUEUE_KEY)  # Clear old data first
        r.rpush(IMAGE_QUEUE_KEY, *image_queue)

def acquire_image_queue_lock() -> Optional[Any]:
    '''Try to acquire a lock for the image queue with retry logic.

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    return acquire_lock(IMAGE_QUEUE_LOCK_KEY)