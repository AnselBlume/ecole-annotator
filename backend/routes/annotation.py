from fastapi import HTTPException, status, APIRouter, Request, Query
from model import ImageAnnotation, ImageQualityUpdate, PointPrompt, PolygonPrompt
from services.annotator import (
    get_annotation_state,
    AnnotationStateError,
    acquire_annotation_state_lock,
    acquire_image_lock,
    mark_image_as_annotated,
    save_annotation_state,
    image_path_to_label
)
from services.redis_client import release_lock, LockAcquisitionError, r
from services.sam_predictor import (
    get_user_id,
    process_point_prompt,
    process_polygon_prompt,
    clear_user_cache_for_image
)
from utils.mask_utils import create_rle_from_mask
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post('/save-annotation')
def save_annotation(annotation: ImageAnnotation, request: Request):
    '''Save an annotation with proper locking.'''
    # First, try to acquire a lock for this specific image
    try:
        # Get the user ID from the session cookie
        user_id = get_user_id(request)

        image_lock = acquire_image_lock(annotation.image_path)
        if not image_lock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Image annotation is currently being saved by another user'
            )

        try:
            # Then, try to acquire a lock for the entire annotation state
            state_lock = acquire_annotation_state_lock()
            if not state_lock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Annotation state is currently being updated by another user'
                )

            try:
                annotation_state = get_annotation_state()

                # Check if this is a new annotation (not previously in checked)
                is_new_annotation = annotation.image_path not in annotation_state.checked

                if annotation.image_path in annotation_state.unchecked:
                    del annotation_state.unchecked[annotation.image_path]

                annotation_state.checked[annotation.image_path] = annotation

                save_annotation_state(annotation_state)
                mark_image_as_annotated(annotation.image_path)

                # Increment user's annotation count if it's a new annotation
                if is_new_annotation:
                    user_count_key = f"user_annotation_count:{user_id}"
                    r.incr(user_count_key)
                    logger.info(f"Incremented annotation count for user {user_id}")

                # Clear any cached masks for this image across all users
                clear_user_cache_for_image(annotation.image_path)

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

@router.get('/annotation-state')
def get_annotation_state_endpoint():
    '''Get the current annotation state.'''
    try:
        annotation_state = get_annotation_state()
        return annotation_state.model_dump()
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get('/annotation-stats')
def get_annotation_stats():
    '''Get statistics about the annotation progress.'''
    try:
        annotation_state = get_annotation_state()
        checked_count = len(annotation_state.checked)
        unchecked_count = len(annotation_state.unchecked)
        total_count = checked_count + unchecked_count

        return {
            'total_images': total_count,
            'checked_images': checked_count,
            'unchecked_images': unchecked_count,
            'progress_percentage': round((checked_count / total_count) * 100) if total_count > 0 else 0
        }
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get('/user-annotation-count')
def get_user_annotation_count(request: Request):
    '''Get the number of images annotated by the current user based on session cookie.'''
    try:
        user_id = get_user_id(request)

        # Get the key for storing user's annotation count
        user_count_key = f"user_annotation_count:{user_id}"

        # Get the count from Redis, default to 0 if not exists
        user_count = int(r.get(user_count_key) or 0)

        return {
            'user_count': user_count
        }
    except Exception as e:
        logger.error(f"Error getting user annotation count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user annotation count: {str(e)}"
        )

@router.get('/object-label')
def get_object_label(image_path: str = Query(..., description="The path to the image")):
    '''Get the object label for an image.'''
    try:
        return {
            'object_label': image_path_to_label(image_path)
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get('/object-parts')
def get_object_parts(object_label: str = None):
    '''Get all possible parts for an object label or all object-part mappings.'''
    try:
        import json
        from services.annotator import r, OBJECT_LABEL_TO_PARTS_KEY

        object_label_to_parts = json.loads(r.get(OBJECT_LABEL_TO_PARTS_KEY) or '{}')

        if object_label:
            return {
                'parts': object_label_to_parts.get(object_label, [])
            }
        else:
            return {
                'object_label_to_parts': object_label_to_parts
            }
    except Exception as e:
        logger.error(f"Error getting object parts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get object parts: {str(e)}"
        )

@router.get('/image-annotation/{image_path:path}')
def get_image_annotation(image_path: str):
    '''Get a specific image annotation by its path.'''
    try:
        annotation_state = get_annotation_state()

        # Check in both checked and unchecked dictionaries
        if image_path in annotation_state.checked:
            return annotation_state.checked[image_path].model_dump()
        elif image_path in annotation_state.unchecked:
            return annotation_state.unchecked[image_path].model_dump()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Image annotation not found: {image_path}'
        )
    except AnnotationStateError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post('/update-image-quality')
def update_image_quality(update: ImageQualityUpdate):
    '''Update the quality status of an image with proper locking.'''
    # First, try to acquire a lock for this specific image
    try:
        image_lock = acquire_image_lock(update.image_path)
        if not image_lock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Image is currently being edited by another user'
            )

        try:
            # Then, try to acquire a lock for the entire annotation state
            state_lock = acquire_annotation_state_lock()
            if not state_lock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Annotation state is currently being updated by another user'
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
                        detail=f'Image not found: {update.image_path}'
                    )

                # Save updated state
                save_annotation_state(annotation_state)

                return {'status': 'success'}
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

@router.post('/update-part-annotation')
def update_part_annotation(image_path: str, part_name: str, annotation_data: dict):
    """
    Update a specific part annotation with new RLEs generated from SAM2 or polygon annotation.
    """
    try:
        # Acquire locks
        image_lock = acquire_image_lock(image_path)
        if not image_lock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Image is currently being edited by another user'
            )

        try:
            state_lock = acquire_annotation_state_lock()
            if not state_lock:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Annotation state is currently being updated by another user'
                )

            try:
                annotation_state = get_annotation_state()

                # Find image in checked or unchecked
                image_found = False
                for state_dict in [annotation_state.checked, annotation_state.unchecked]:
                    if image_path in state_dict:
                        image_annotation = state_dict[image_path]

                        # Update or add part
                        if part_name in image_annotation.parts:
                            # Update existing part
                            if 'rles' in annotation_data:
                                image_annotation.parts[part_name].rles = annotation_data['rles']

                            # Update other attributes if provided
                            for attr in ['is_poor_quality', 'is_correct', 'is_complete']:
                                if attr in annotation_data:
                                    setattr(image_annotation.parts[part_name], attr, annotation_data[attr])

                            image_annotation.parts[part_name].was_checked = True
                        else:
                            # Create new part
                            from model import PartAnnotation
                            new_part = PartAnnotation(
                                name=part_name,
                                rles=annotation_data.get('rles', []),
                                was_checked=True,
                                is_correct=annotation_data.get('is_correct', True),
                                is_poor_quality=annotation_data.get('is_poor_quality', False),
                                is_complete=annotation_data.get('is_complete', True)
                            )
                            image_annotation.parts[part_name] = new_part

                        image_found = True
                        break

                if not image_found:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f'Image not found: {image_path}'
                    )

                # Save updated state
                save_annotation_state(annotation_state)

                return {'status': 'success'}
            finally:
                release_lock(state_lock)
        finally:
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

@router.post('/generate-mask-from-points')
async def generate_mask_from_points(prompt: PointPrompt, request: Request):
    """
    Generate a mask using SAM2 from positive and negative point prompts.
    Returns RLE encoded mask.
    """
    try:
        # Log incoming request for debugging
        logger.debug(f"Generate mask from points for image: {prompt.image_path}")
        logger.debug(f"Positive points: {[(p.x, p.y) for p in prompt.positive_points]}")
        logger.debug(f"Negative points: {[(p.x, p.y) for p in prompt.negative_points]}")
        logger.debug(f"Using mask color: {prompt.mask_color}")

        # Get user-specific identifier
        user_id = get_user_id(request)
        logger.debug(f"Processing request for user: {user_id}")

        # Process the point prompt to get a mask
        best_mask, best_score, _ = process_point_prompt(
            prompt.image_path,
            user_id,
            prompt.positive_points,
            prompt.negative_points,
            prompt.part_name
        )

        # Convert mask to RLE format
        rle_dict = create_rle_from_mask(best_mask, prompt.image_path)
        logger.info(f"Generated valid RLE dict with keys: {list(rle_dict.keys())}")

        return {
            "rle": rle_dict,
            "score": float(best_score),
            "mask_color": prompt.mask_color
        }

    except Exception as e:
        logger.error(f"Error generating mask from points: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate mask: {str(e)}"
        )

@router.post('/generate-mask-from-polygon')
async def generate_mask_from_polygon(prompt: PolygonPrompt, request: Request):
    """
    Generate a mask from polygon points.
    Returns RLE encoded mask.
    """
    try:
        # Log incoming request for debugging
        logger.debug(f"Generate mask from polygon for image: {prompt.image_path}")
        logger.debug(f"Polygon points: {[(p.x, p.y) for p in prompt.polygon_points]}")
        logger.debug(f"Using mask color: {prompt.mask_color}")

        # Get user-specific identifier
        user_id = get_user_id(request)
        logger.debug(f"Processing polygon request for user: {user_id}")

        # Process the polygon to get a mask
        mask = process_polygon_prompt(prompt.image_path, user_id, prompt.polygon_points)

        # Convert mask to RLE format
        rle_dict = create_rle_from_mask(mask, prompt.image_path)
        logger.debug(f"Generated valid RLE dict with keys: {list(rle_dict.keys())}")

        return {
            "rle": rle_dict,
            "mask_color": prompt.mask_color
        }

    except Exception as e:
        logger.error(f"Error generating mask from polygon: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate mask: {str(e)}"
        )

@router.post('/preview-mask-from-points')
async def preview_mask_from_points(prompt: PointPrompt, request: Request):
    """
    Generate a preview mask using SAM2 from positive and negative point prompts.
    Similar to generate_mask_from_points but doesn't save the result.
    """
    try:
        # Log incoming points data for debugging
        positive_count = len(prompt.positive_points) if prompt.positive_points else 0
        negative_count = len(prompt.negative_points) if prompt.negative_points else 0
        logger.info(f"Preview mask requested with {positive_count} positive points and {negative_count} negative points")

        # Get user-specific identifier
        user_id = get_user_id(request)

        # Process the point prompt to get a mask
        best_mask, best_score, _ = process_point_prompt(
            prompt.image_path,
            user_id,
            prompt.positive_points,
            prompt.negative_points,
            prompt.part_name
        )

        # Convert mask to RLE format
        rle_dict = create_rle_from_mask(best_mask, prompt.image_path)
        logger.info(f"RLE dict created with keys: {list(rle_dict.keys())}")

        return {
            "rle": rle_dict,
            "score": float(best_score)
        }

    except Exception as e:
        logger.error(f"Error generating preview mask from points: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate preview mask: {str(e)}"
        )

@router.post('/preview-mask-from-polygon')
async def preview_mask_from_polygon(prompt: PolygonPrompt, request: Request):
    """
    Generate a preview mask from polygon points.
    Similar to generate_mask_from_polygon but doesn't save the result.
    """
    try:
        # Get user-specific identifier
        user_id = get_user_id(request)
        logger.info(f"Processing polygon preview for user: {user_id}")

        # Process the polygon to get a mask
        mask = process_polygon_prompt(prompt.image_path, user_id, prompt.polygon_points)

        # Convert mask to RLE format
        rle_dict = create_rle_from_mask(mask, prompt.image_path)

        # Log success
        logger.info(f"Successfully generated polygon mask preview")

        return {
            "rle": rle_dict
        }

    except Exception as e:
        logger.error(f"Error generating mask from polygon: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate mask: {str(e)}"
        )