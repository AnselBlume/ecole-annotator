from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Literal, Dict, List
import json
import os
import redis
from dataset.annotation import collect_annotations, DatasetMetadata, RLEAnnotationWithMaskPath, get_part_suffix
import fcntl
from render_mask import router as render_mask_router
import logging
import coloredlogs

logger = logging.getLogger(__name__)
coloredlogs.install(level='INFO')

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

PARTONOMY_DIR = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/partonomy'
DATA_DIR = '/shared/nas2/blume5/sp25/annotator/data'
ANNOTATION_FILE = os.path.join(DATA_DIR, 'annotations.json')

# Redis client for concurrency-safe queueing
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Redis lock timeout in seconds
LOCK_TIMEOUT = 300  # 5 minutes

# Redis keys
ANNOTATION_STATE_KEY = 'annotation_state'
IMAGE_QUEUE_KEY = 'image_queue'
IMAGE_LOCK_PREFIX = 'lock:'
IMAGE_ANNOTATED_PREFIX = 'annotated:'
ANNOTATION_STATE_LOCK_KEY = 'annotation_state_lock'
IMAGE_QUEUE_LOCK_KEY = 'image_queue_lock'

class AnnotationStateError(Exception):
    """Exception raised when there's an issue with the annotation state."""
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

def mark_image_as_annotated(image_path: str) -> None:
    """Mark an image as annotated in Redis."""
    r.set(f'{IMAGE_ANNOTATED_PREFIX}{image_path}', 1)

def is_image_annotated(image_path: str) -> bool:
    """Check if an image is already annotated."""
    return r.exists(f'{IMAGE_ANNOTATED_PREFIX}{image_path}')

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
@app.post('/api/initialize-queue')
def initialize_queue(annotation_state: AnnotationState):
    # Set up the image queue with unchecked images
    try:
        if not acquire_image_queue_lock():
            return {"status": "error", "message": "Image queue is currently being initialized by another user"}

        image_queue = list(annotation_state.unchecked.values())
        r.set(IMAGE_QUEUE_KEY, json.dumps([img.model_dump() for img in image_queue]))
    finally:
        release_image_queue_lock()

@app.get('/api/next-image')
def get_next_image():
    """Get the next image from the queue without locking it."""
    while r.llen(IMAGE_QUEUE_KEY) > 0:
        image_json = r.lpop(IMAGE_QUEUE_KEY)
        if image_json:
            image_data = json.loads(image_json)
            try:
                acquire_image_lock(image_data["image_path"])
                if not is_image_annotated(image_data["image_path"]):
                    return image_data
            finally:
                release_image_lock(image_data["image_path"])
    return {}

@app.post('/api/save-annotation')
def save_annotation(annotation: ImageAnnotation):
    """Save an annotation with proper locking."""
    # First, try to acquire a lock for this specific image
    if not acquire_image_lock(annotation.image_path):
        return {"status": "error", "message": "Image annotation is currently being saved by another user"}

    try:
        # Then, try to acquire a lock for the entire annotation state
        if not acquire_annotation_state_lock():
            return {"status": "error", "message": "Annotation state is currently being updated by another user"}

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
            release_annotation_state_lock()
    finally:
        # Always release the image lock
        release_image_lock(annotation.image_path)

@app.get('/api/annotation-state')
def get_annotation_state_endpoint():
    """Get the current annotation state."""
    try:
        annotation_state = get_annotation_state()
        return annotation_state.model_dump()
    except AnnotationStateError as e:
        return {"status": "error", "message": str(e)}

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
        return {"status": "error", "message": str(e)}

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

        return None
    except AnnotationStateError as e:
        return {"status": "error", "message": str(e)}

@app.post('/api/update-image-quality')
def update_image_quality(update: ImageQualityUpdate):
    """Update the quality status of an image with proper locking."""
    # First, try to acquire a lock for this specific image
    if not acquire_image_lock(update.image_path):
        return {"status": "error", "message": "Image is currently being edited by another user"}

    try:
        # Then, try to acquire a lock for the entire annotation state
        if not acquire_annotation_state_lock():
            return {"status": "error", "message": "Annotation state is currently being updated by another user"}

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
                return {"status": "error", "message": f"Image {update.image_path} not found"}

            # Save updated state
            save_annotation_state(annotation_state)

            return {"status": "success"}
        finally:
            # Always release the annotation state lock
            release_annotation_state_lock()
    finally:
        # Always release the image lock
        release_image_lock(update.image_path)

def acquire_annotation_state_lock() -> bool:
    """Try to acquire a lock for the annotation state. Returns True if successful."""
    # Use Redis SETNX to atomically set the lock if it doesn't exist
    return r.set(ANNOTATION_STATE_LOCK_KEY, 'locked', ex=LOCK_TIMEOUT, nx=True)

def release_annotation_state_lock() -> None:
    """Release the lock for the annotation state."""
    r.delete(ANNOTATION_STATE_LOCK_KEY)

def acquire_image_lock(image_path: str) -> bool:
    """Try to acquire a lock for an image. Returns True if successful."""
    lock_key = f'{IMAGE_LOCK_PREFIX}{image_path}'
    # Use Redis SETNX to atomically set the lock if it doesn't exist
    return r.set(lock_key, 'locked', ex=LOCK_TIMEOUT, nx=True)

def release_image_lock(image_path: str) -> None:
    """Release the lock for an image."""
    lock_key = f'{IMAGE_LOCK_PREFIX}{image_path}'
    r.delete(lock_key)

def acquire_image_queue_lock() -> bool:
    """Try to acquire a lock for the image queue. Returns True if successful."""
    return r.set(IMAGE_QUEUE_LOCK_KEY, 'locked', ex=LOCK_TIMEOUT, nx=True)

def release_image_queue_lock() -> None:
    """Release the lock for the image queue."""
    r.delete(IMAGE_QUEUE_LOCK_KEY)