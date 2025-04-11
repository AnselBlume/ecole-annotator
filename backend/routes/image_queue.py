import json
from fastapi import HTTPException, status, APIRouter
from services.image_queue import acquire_image_queue_lock, initialize_queue, IMAGE_QUEUE_KEY
from services.annotator import (
    get_annotation_state,
    AnnotationStateError,
    is_image_annotated,
    acquire_annotation_state_lock,
    acquire_image_lock
)
from services.redis_client import r, release_lock, LockAcquisitionError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post('/reload-queue')
def reload_queue():
    try:
        queue_lock = acquire_image_queue_lock()
        annotation_state_lock = acquire_annotation_state_lock()
        if not queue_lock or not annotation_state_lock:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Could not obtain necessary locks. Please try again later.'
            )
        try:
            # Reload annotation state internally
            annotation_state = get_annotation_state()
            initialize_queue(annotation_state)
            return {'status': 'success', 'message': 'Image queue reloaded successfully'}
        finally:
            release_lock(queue_lock)
            release_lock(annotation_state_lock)
    except LockAcquisitionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get('/next-image')
def get_next_image():
    '''Get the next image from the queue without locking it.'''
    while r.llen(IMAGE_QUEUE_KEY) > 0:
        image_json = r.lpop(IMAGE_QUEUE_KEY)
        if image_json:
            image_data = json.loads(image_json)
            try:
                image_lock = acquire_image_lock(image_data['image_path'])
                if not image_lock:
                    # If we can't acquire the lock, skip this image and try the next one
                    logger.warning(f'Could not acquire lock for image {image_data['image_path']}, skipping')
                    continue

                try:
                    if not is_image_annotated(image_data['image_path']):
                        return image_data
                finally:
                    release_lock(image_lock)
            except LockAcquisitionError:
                # If we can't acquire the lock, skip this image and try the next one
                logger.warning(f'Could not acquire lock for image {image_data['image_path']}, skipping')
                continue
    return {}