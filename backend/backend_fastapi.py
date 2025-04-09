from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, Any
import json
import os
import redis
from redis.cluster import RedisCluster
from redis.exceptions import LockError
import time
import fcntl
from dataset.annotation import collect_annotations, DatasetMetadata, RLEAnnotationWithMaskPath, get_part_suffix
from render_mask import router as render_mask_router
import logging
import coloredlogs

logger = logging.getLogger(__name__)
coloredlogs.install(level='INFO')

# Paths
PARTONOMY_DIR = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/partonomy'
DATA_DIR = '/shared/nas2/blume5/sp25/annotator/data'
ANNOTATION_FILE = os.path.join(DATA_DIR, 'annotations.json')

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Redis lock timeout in seconds
LOCK_TIMEOUT = 300  # 5 minutes
LOCK_RETRY_TIMES = 3  # Number of times to retry acquiring a lock
LOCK_RETRY_DELAY = 1  # Delay between retries in seconds
LOCK_BLOCKING_TIMEOUT = 30  # 30 seconds

# Redis keys
ANNOTATION_STATE_KEY = 'annotation_state'
IMAGE_QUEUE_KEY = 'image_queue'
IMAGE_LOCK_PREFIX = 'lock:'
IMAGE_ANNOTATED_PREFIX = 'annotated:'
ANNOTATION_STATE_LOCK_KEY = 'annotation_state_lock'
IMAGE_QUEUE_LOCK_KEY = 'image_queue_lock'

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    annotation_state = load_annotation_state()
    initialize_queue(annotation_state)
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)
app.include_router(render_mask_router, prefix='/api') # Include the render_mask endpoints

# Allow local frontend to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Redis client for concurrency-safe queueing
try:
    # Try to use Redis Cluster for better locking support
    r = RedisCluster(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        skip_full_coverage_check=True
    )
    logger.info("Connected to Redis Cluster")
except Exception as e:
    # Fall back to regular Redis if cluster is not available
    logger.warning(f"Failed to connect to Redis Cluster: {e}. Falling back to regular Redis.")
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )

class AnnotationStateError(Exception):
    """Exception raised when there's an issue with the annotation state."""
    pass

class LockAcquisitionError(Exception):
    """Exception raised when a lock cannot be acquired after retries."""
    pass

class PartAnnotation(BaseModel):
    name: str
    rles: list[RLEAnnotationWithMaskPath] = []

    was_checked: bool = False
    is_poor_quality: bool = False
    is_incorrect: bool = False

class ImageAnnotation(BaseModel):
    image_path: str
    parts: list[PartAnnotation]

class AnnotationState(BaseModel):
    checked: dict[str, ImageAnnotation]
    unchecked: dict[str, ImageAnnotation]

class ImageQualityUpdate(BaseModel):
    image_path: str
    is_poor_quality: bool = False
    is_incorrect: bool = False

def get_annotation_state() -> AnnotationState:
    """Get the current annotation state from Redis.

    Raises:
        AnnotationStateError: If the annotation state is missing or invalid.
    """
    annotation_state_json = r.get(ANNOTATION_STATE_KEY)
    if not annotation_state_json:
        raise AnnotationStateError("Annotation state is missing. The system may not be properly initialized.")

    try:
        return AnnotationState.model_validate_json(annotation_state_json)
    except Exception as e:
        raise AnnotationStateError(f"Failed to parse annotation state: {e}")

def save_annotation_state(annotation_state: AnnotationState, to_file: bool = True) -> None:
    """Save the annotation state to Redis and the file with proper locking."""
    # Save to Redis first (atomic operation)
    r.set(ANNOTATION_STATE_KEY, annotation_state.model_dump_json())

    if to_file: # Save to file with file locking
        with open(ANNOTATION_FILE, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Acquire exclusive lock
            try:
                json.dump(annotation_state.model_dump(), f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

def load_annotation_state():
    # Load annotations
    annotations: DatasetMetadata = collect_annotations(
        os.path.join(PARTONOMY_DIR, 'images'),
        os.path.join(PARTONOMY_DIR, 'masks')
    )

    img_paths_to_rle_dicts = annotations.img_paths_to_rle_dicts
    r.set('img_paths_to_rle_dicts', json.dumps(img_paths_to_rle_dicts))
    part_labels = set(annotations.part_labels)

    img_path_to_label = {
        path : label
        for label, paths in annotations.img_paths_by_label.items()
        for path in paths
    }
    r.set('img_path_to_label', json.dumps(img_path_to_label))

    # Load existing annotations
    if os.path.exists(ANNOTATION_FILE):
        with open(ANNOTATION_FILE) as f:
            try:
                annotation_state_data = json.load(f)
                annotation_state = AnnotationState.model_validate(annotation_state_data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Error loading existing annotations: {e}. Starting fresh.")
                annotation_state = AnnotationState(checked={}, unchecked={})
    else: # No existing annotations
        checked = {}
        unchecked = {}
        for img_path, label_to_rle_dicts in img_paths_to_rle_dicts.items():
            for label, rle_dicts in label_to_rle_dicts.items():
                if label in part_labels: # Only validate part annotations, not objects
                    unchecked[img_path] = ImageAnnotation(
                        image_path=img_path,
                        parts=[PartAnnotation(name=label, rles=rle_dicts)]
                    )

        annotation_state = AnnotationState(checked=checked, unchecked=unchecked)

    return annotation_state

# Load image metadata into Redis queue (one-time initialization)
def initialize_queue(annotation_state: AnnotationState):
    image_queue = list(annotation_state.unchecked.values())
    r.set(IMAGE_QUEUE_KEY, json.dumps([img.model_dump() for img in image_queue]))

@app.post('/api/reload-queue')
def reload_queue():
    try:
        queue_lock = acquire_image_queue_lock()
        annotation_state_lock = acquire_annotation_state_lock()
        if not queue_lock or not annotation_state_lock:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not obtain necessary locks. Please try again later."
            )
        try:
            # Reload annotation state internally
            annotation_state = get_annotation_state()
            initialize_queue(annotation_state)
            return {"status": "success", "message": "Image queue reloaded successfully"}
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

@app.get('/api/next-image')
def get_next_image():
    """Get the next image from the queue without locking it."""
    while r.llen(IMAGE_QUEUE_KEY) > 0:
        image_json = r.lpop(IMAGE_QUEUE_KEY)
        if image_json:
            image_data = json.loads(image_json)
            try:
                image_lock = acquire_image_lock(image_data["image_path"])
                if not image_lock:
                    # If we can't acquire the lock, skip this image and try the next one
                    logger.warning(f"Could not acquire lock for image {image_data['image_path']}, skipping")
                    continue

                try:
                    if not is_image_annotated(image_data["image_path"]):
                        return image_data
                finally:
                    release_lock(image_lock)
            except LockAcquisitionError:
                # If we can't acquire the lock, skip this image and try the next one
                logger.warning(f"Could not acquire lock for image {image_data['image_path']}, skipping")
                continue
    return {}

@app.post('/api/save-annotation')
def save_annotation(annotation: ImageAnnotation):
    """Save an annotation with proper locking."""
    # First, try to acquire a lock for this specific image
    try:
        image_lock = acquire_image_lock(annotation.image_path)
        if not image_lock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Image annotation is currently being saved by another user"
            )

        try:
            # Then, try to acquire a lock for the entire annotation state
            state_lock = acquire_annotation_state_lock()
            if not state_lock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Annotation state is currently being updated by another user"
                )

            try:
                # Get current annotation state
                annotation_state = get_annotation_state()

                # Move from unchecked to checked
                if annotation.image_path in annotation_state.unchecked:
                    del annotation_state.unchecked[annotation.image_path]

                # Add to checked
                annotation_state.checked[annotation.image_path] = annotation

                # Save updated state
                save_annotation_state(annotation_state)

                # Mark image as annotated
                mark_image_as_annotated(annotation.image_path)

                return {'status': 'saved'}
            finally:
                # Always release the annotation state lock
                release_lock(state_lock)
        finally:
            # Always release the image lock
            release_lock(image_lock)
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

@app.get('/api/annotation-state')
def get_annotation_state_endpoint():
    """Get the current annotation state."""
    try:
        annotation_state = get_annotation_state()
        return annotation_state.model_dump()
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get('/api/annotation-stats')
def get_annotation_stats():
    """Get statistics about the annotation progress."""
    try:
        annotation_state = get_annotation_state()
        checked_count = len(annotation_state.checked)
        unchecked_count = len(annotation_state.unchecked)
        total_count = checked_count + unchecked_count

        return {
            "total_images": total_count,
            "checked_images": checked_count,
            "unchecked_images": unchecked_count,
            "progress_percentage": round((checked_count / total_count) * 100) if total_count > 0 else 0
        }
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get('/api/image-annotation/{image_path:path}')
def get_image_annotation(image_path: str):
    """Get a specific image annotation by its path."""
    try:
        annotation_state = get_annotation_state()

        # Check in both checked and unchecked dictionaries
        if image_path in annotation_state.checked:
            return annotation_state.checked[image_path].model_dump()
        elif image_path in annotation_state.unchecked:
            return annotation_state.unchecked[image_path].model_dump()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image annotation not found: {image_path}"
        )
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post('/api/update-image-quality')
def update_image_quality(update: ImageQualityUpdate):
    """Update the quality status of an image with proper locking."""
    # First, try to acquire a lock for this specific image
    try:
        image_lock = acquire_image_lock(update.image_path)
        if not image_lock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Image is currently being edited by another user"
            )

        try:
            # Then, try to acquire a lock for the entire annotation state
            state_lock = acquire_annotation_state_lock()
            if not state_lock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Annotation state is currently being updated by another user"
                )

            try:
                annotation_state = get_annotation_state()

                # Find the image in either checked or unchecked
                image_found = False
                for state_dict in [annotation_state.checked, annotation_state.unchecked]:
                    if update.image_path in state_dict:
                        image_annotation = state_dict[update.image_path]
                        # Update all parts
                        for part in image_annotation.parts:
                            part.is_poor_quality = update.is_poor_quality
                            part.is_incorrect = update.is_incorrect
                            part.was_checked = True
                        image_found = True
                        break

                if not image_found:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Image not found: {update.image_path}"
                    )

                # Save updated state
                save_annotation_state(annotation_state)

                return {"status": "success"}
            finally:
                # Always release the annotation state lock
                release_lock(state_lock)
        finally:
            # Always release the image lock
            release_lock(image_lock)
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

def acquire_lock(lock_name: str, with_retry: bool = False, blocking: bool = True) -> Optional[Any]:
    """
    Acquire a Redis lock. If with_retry is True, the lock will be acquired with retry logic. If blocking is True, the lock will be acquired blocking until it is acquired.
    Only one of with_retry or blocking can be True.

    Args:
        lock_name: The name of the lock to acquire
        with_retry: Whether to retry acquiring the lock
        blocking: Whether to block until the lock is acquired

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    """
    assert with_retry ^ blocking, "with_retry and blocking must be mutually exclusive"

    if with_retry:
        return acquire_lock_with_retry(lock_name)
    else:
        return acquire_lock_blocking(lock_name)

def acquire_lock_blocking(lock_name: str, timeout: int = LOCK_TIMEOUT, blocking_timeout: int = LOCK_BLOCKING_TIMEOUT) -> Optional[Any]:
    """Acquire a Redis lock blocking until it is acquired.

    Args:
        lock_name: The name of the lock to acquire
        timeout: The timeout for the lock in seconds
    """
    try:
        lock = r.lock(lock_name, timeout=timeout)
        if lock.acquire(blocking=True, blocking_timeout=blocking_timeout):
            return lock
    except LockError as e:
        logger.error(f"Error acquiring lock {lock_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error acquiring lock {lock_name}: {e}")
        return None

    raise LockAcquisitionError(f"Failed to acquire lock {lock_name} after {timeout} seconds")

def acquire_lock_with_retry(lock_name: str, timeout: int = LOCK_TIMEOUT, retry_times: int = LOCK_RETRY_TIMES, retry_delay: float = LOCK_RETRY_DELAY) -> Optional[Any]:
    """Acquire a Redis lock with retry logic.

    Args:
        lock_name: The name of the lock to acquire
        timeout: The timeout for the lock in seconds
        retry_times: The number of times to retry acquiring the lock
        retry_delay: The delay between retries in seconds

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    """
    for attempt in range(retry_times):
        try:
            # Try to acquire the lock
            lock = r.lock(lock_name, timeout=timeout)
            if lock.acquire(blocking=False):
                logger.debug(f"Acquired lock {lock_name} on attempt {attempt + 1}")
                return lock
        except LockError as e:
            logger.warning(f"Lock error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error acquiring lock {lock_name}: {e}")

        # Wait before retrying
        if attempt < retry_times - 1:
            time.sleep(retry_delay)

    # If we get here, we failed to acquire the lock after all retries
    raise LockAcquisitionError(f"Failed to acquire lock {lock_name} after {retry_times} attempts")

def release_lock(lock: Any) -> None:
    """Release a Redis lock.

    Args:
        lock: The lock object to release
    """
    try:
        lock.release()
    except Exception as e:
        logger.error(f"Error releasing lock: {e}")

def acquire_annotation_state_lock() -> Optional[Any]:
    """Try to acquire a lock for the annotation state with retry logic.

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    """
    return acquire_lock(ANNOTATION_STATE_LOCK_KEY)

def acquire_image_lock(image_path: str) -> Optional[Any]:
    """Try to acquire a lock for an image with retry logic.

    Args:
        image_path: The path of the image to lock

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    """
    lock_name = f'{IMAGE_LOCK_PREFIX}{image_path}'
    return acquire_lock(lock_name)

def acquire_image_queue_lock() -> Optional[Any]:
    """Try to acquire a lock for the image queue with retry logic.

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    """
    return acquire_lock(IMAGE_QUEUE_LOCK_KEY)

def mark_image_as_annotated(image_path: str) -> None:
    """Mark an image as annotated in Redis."""
    r.set(f'{IMAGE_ANNOTATED_PREFIX}{image_path}', 1)

def is_image_annotated(image_path: str) -> bool:
    """Check if an image is already annotated."""
    return r.exists(f'{IMAGE_ANNOTATED_PREFIX}{image_path}')