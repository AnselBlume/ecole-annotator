from fastapi import HTTPException, status, APIRouter
from model import ImageAnnotation, ImageQualityUpdate
from services.annotator import (
    get_annotation_state,
    AnnotationStateError,
    acquire_annotation_state_lock,
    acquire_image_lock,
    mark_image_as_annotated,
    save_annotation_state
)
from services.redis_client import release_lock, LockAcquisitionError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post('/save-annotation')
def save_annotation(annotation: ImageAnnotation):
    '''Save an annotation with proper locking.'''
    # First, try to acquire a lock for this specific image
    try:
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