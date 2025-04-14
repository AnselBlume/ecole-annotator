import orjson
from model import AnnotationState
from dataset.annotation import collect_annotations, DatasetMetadata
import os
import json
import fcntl
from typing import Any, Optional
from services.redis_client import r, acquire_lock
import logging
from model import PartAnnotation, ImageAnnotation
from dataset.utils import is_part_name

logger = logging.getLogger(__name__)

# Paths
PARTONOMY_DIR = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/partonomy'
DATA_DIR = '/shared/nas2/blume5/sp25/annotator/data'
ANNOTATION_FILE = os.path.join(DATA_DIR, 'annotations.json')

# Redis keys
ANNOTATION_STATE_KEY = 'annotation_state'
IMAGE_ANNOTATED_PREFIX = 'annotated:'
ANNOTATION_STATE_LOCK_KEY = 'annotation_state_lock'
IMAGE_LOCK_PREFIX = 'lock:'

_img_path_to_label = None
_object_label_to_parts = None

class AnnotationStateError(Exception):
    '''Exception raised when there's an issue with the annotation state.'''
    pass

def get_annotation_state() -> AnnotationState:
    '''Get the current annotation state from Redis.

    Raises:
        AnnotationStateError: If the annotation state is missing or invalid.
    '''
    annotation_state_json = r.get(ANNOTATION_STATE_KEY)
    if not annotation_state_json:
        raise AnnotationStateError('Annotation state is missing. The system may not be properly initialized.')

    try:
        return AnnotationState.model_validate_json(annotation_state_json)
    except Exception as e:
        raise AnnotationStateError(f'Failed to parse annotation state: {e}')

def save_annotation_state(annotation_state: AnnotationState, to_file: bool = True) -> None:
    '''Save the annotation state to Redis and the file with proper locking.'''
    # Save to Redis first (atomic operation)
    r.set(ANNOTATION_STATE_KEY, annotation_state.model_dump_json())

    if to_file: # Save to file with file locking
        with open(ANNOTATION_FILE, 'wb') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Acquire exclusive lock
            try:
                f.write(orjson.dumps(annotation_state.model_dump(), option=orjson.OPT_INDENT_2))
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

def load_annotation_state():
    # Load annotations
    annotations: DatasetMetadata = collect_annotations(
        os.path.join(PARTONOMY_DIR, 'images'),
        os.path.join(PARTONOMY_DIR, 'masks'),
        validate_rle_dicts=False
    )

    img_paths_to_rle_dicts = annotations.img_paths_to_rle_dicts
    part_labels = set(annotations.part_labels)

    # Need mapping from image label to obejct label to display on annotator interface
    global _img_path_to_label, _object_label_to_parts
    _img_path_to_label = { # Mapping from image path to object label
        path : label
        for label, paths in annotations.img_paths_by_label.items()
        for path in paths
        if not is_part_name(label)
    }
    # Use the object_label_to_part_labels mapping from annotations instead of building our own
    _object_label_to_parts = {obj_label: sorted(part_labels) for obj_label, part_labels in annotations.object_label_to_part_labels.items()}

    # Load existing annotations
    if os.path.exists(ANNOTATION_FILE):
        with open(ANNOTATION_FILE) as f:
            try:
                annotation_state_data = json.load(f)
                annotation_state = AnnotationState.model_validate(annotation_state_data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f'Error loading existing annotations: {e}. Starting fresh.')
                annotation_state = AnnotationState(checked={}, unchecked={})
    else: # No existing annotations
        checked = {}
        unchecked = {}
        for img_path, label_to_rle_dicts in img_paths_to_rle_dicts.items():
            for label, rle_dicts in label_to_rle_dicts.items():
                if label in part_labels: # Only validate part annotations, not objects
                    annot: ImageAnnotation = unchecked.setdefault(img_path, ImageAnnotation(image_path=img_path, parts={}))
                    annot.parts[label] = PartAnnotation(name=label, rles=rle_dicts)

        annotation_state = AnnotationState(checked=checked, unchecked=unchecked)

    return annotation_state

def acquire_annotation_state_lock() -> Optional[Any]:
    '''Try to acquire a lock for the annotation state with retry logic.

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    return acquire_lock(ANNOTATION_STATE_LOCK_KEY)

def acquire_image_lock(image_path: str) -> Optional[Any]:
    '''Try to acquire a lock for an image with retry logic.

    Args:
        image_path: The path of the image to lock

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    lock_name = f'{IMAGE_LOCK_PREFIX}{image_path}'
    return acquire_lock(lock_name)

def mark_image_as_annotated(image_path: str) -> None:
    '''Mark an image as annotated in Redis.'''
    r.set(f'{IMAGE_ANNOTATED_PREFIX}{image_path}', 1)

def is_image_annotated(image_path: str) -> bool:
    '''Check if an image is already annotated.'''
    return r.exists(f'{IMAGE_ANNOTATED_PREFIX}{image_path}')

def image_path_to_part_labels(image_path: str) -> list[str]:
    logger.info(f'Image path in path to label? {image_path in _img_path_to_label}')
    logger.info(f'Image path to label: {_img_path_to_label[image_path]}')

    return _object_label_to_parts[_img_path_to_label[image_path]]