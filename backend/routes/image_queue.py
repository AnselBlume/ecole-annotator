import os
import json
import base64
import hashlib
from tqdm import tqdm
from fastapi import HTTPException, status, APIRouter
from services.image_queue import acquire_image_queue_lock, initialize_queue, IMAGE_QUEUE_KEY
from services.annotator import (
    get_annotation_state,
    AnnotationStateError,
    is_image_annotated,
    acquire_annotation_state_lock,
    acquire_image_lock,
    save_annotation_state,
    image_path_to_part_labels
)
from utils.image_utils import needs_resize, resize_image, resize_rle
from services.redis_client import r, release_lock, LockAcquisitionError
from services.annotator import DATA_DIR
from model import ImageAnnotation
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
            image_data: ImageAnnotation = json.loads(image_json)
            try:
                image_lock = acquire_image_lock(image_data['image_path'])
                if not image_lock:
                    # If we can't acquire the lock, skip this image and try the next one
                    logger.warning(f'Could not acquire lock for image {image_data["image_path"]}, skipping')
                    continue

                try:
                    if is_image_annotated(image_data['image_path']):
                        continue

                    # Get object class from image path to find all possible parts
                    try:
                        all_possible_parts = image_path_to_part_labels(image_data['image_path'])
                        logger.info(f'All possible parts for image {image_data["image_path"]}: {all_possible_parts}')

                        # Add missing parts with empty RLEs
                        from model import PartAnnotation
                        for part_name in all_possible_parts:
                            if part_name not in image_data['parts']:
                                # Add placeholder for part with no existing annotations
                                image_data['parts'][part_name] = {
                                    'name': part_name,
                                    'rles': [],
                                    'was_checked': False,
                                    'is_poor_quality': False,
                                    'is_correct': None,
                                    'is_complete': True,
                                    'has_existing_annotations': False  # Flag to indicate this is a new part with no existing annotations
                                }
                            else:
                                # Mark existing parts
                                image_data['parts'][part_name]['has_existing_annotations'] = True
                    except Exception as e:
                        logger.warning(f"Error adding all possible parts: {e}")
                        # Continue even if we can't add all parts

                    image_data = _handle_resize(image_data) # This overwrites the 'parts' and 'image_path' fields

                    return image_data
                finally:
                    release_lock(image_lock)
            except LockAcquisitionError:
                # If we can't acquire the lock, skip this image and try the next one
                logger.warning(f'Could not acquire lock for image {image_data["image_path"]}, skipping')
                continue
    return {}

def _handle_resize(image_data: ImageAnnotation):
    # Note that this is really a dict of type ImageAnnotation
    nr, image = needs_resize(image_data['image_path'])
    if not nr:
        return image_data

    # Resize image and masks
    logger.info(f"Resizing image of size {image.size}")
    resized_image = resize_image(image)
    logger.info(f"Resized image has size {resized_image.size}")
    os.makedirs(os.path.join(DATA_DIR, 'resized_images'), exist_ok=True)

    # Generate new path. B64 encode original path as suffix to basename to avoid possible collisions
    basename = os.path.splitext(os.path.basename(image_data['image_path']))[0]
    orig_path_hash = short_md5(image_data['image_path'])
    new_path = os.path.join(
        DATA_DIR,
        'resized_images',
        f'{basename}_{orig_path_hash}.jpg'
    )
    resized_image.save(new_path)
    old_path = image_data['image_path']
    image_data['image_path'] = new_path

    # Resize masks
    total_rles = sum(len(part.get('rles', [])) for part in image_data['parts'].values())
    logger.info(f"Starting to resize {total_rles} masks")

    rle_count = 0
    prog_bar = tqdm(range(total_rles), desc="Resizing masks")
    for part_name, part in image_data['parts'].items():

        for i, rle in enumerate(part['rles']):
            rle_count += 1
            try:
                rle_dict = resize_rle(rle)
                rle['size'] = rle_dict['size']
                rle['counts'] = rle_dict['counts']
                rle['mask_path'] = None
                prog_bar.update(1)
            except Exception as e:
                logger.error(f"Error resizing mask for part {part_name}, index {i}: {e}")

    logger.info(f'Completed resizing all {rle_count} masks')

    # Save updated image data to Redis
    logger.info(f'Saving image data to Redis')
    try:
        annotation_state_lock = acquire_annotation_state_lock()
        if not annotation_state_lock:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail='Could not obtain annotation state lock. Please try again later.'
            )

        annotation_state = get_annotation_state()
        annotation_state.unchecked.pop(old_path)
        annotation_state.unchecked[new_path] = image_data

        save_annotation_state(annotation_state, to_file=False)

    finally:
        release_lock(annotation_state_lock)

    return image_data

def short_md5(path: str) -> str:
    # Generate MD5 hash (raw bytes)
    md5_bytes = hashlib.md5(path.encode('utf-8')).digest()

    # Base64 encode it, remove padding (=), and make it URL-safe
    short_hash = base64.urlsafe_b64encode(md5_bytes).decode('utf-8').rstrip('=')

    return short_hash