from fastapi import HTTPException, status, APIRouter, File, UploadFile, Depends
from model import ImageAnnotation, ImageQualityUpdate, PointPrompt, PolygonPrompt
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
from typing import List, Dict, Any, Optional
import numpy as np
import torch
from root_utils import open_image
import time
from fastapi import Request

logger = logging.getLogger(__name__)

router = APIRouter()

# SAM2 predictor singleton
sam2_predictor = None
SAM_MODEL_NAME = "facebook/sam2.1-hiera-base-plus"

# User-specific image embedding cache
# Format: { 'user_id': { 'image_path': {'embeddings': data, 'timestamp': time, 'size': (h,w)} } }
# This will be cleaned up periodically to avoid memory leaks
image_embedding_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
CACHE_CLEANUP_INTERVAL = 3600  # seconds (1 hour)
CACHE_ENTRY_TTL = 1800  # seconds (30 minutes)
last_cache_cleanup = time.time()

def cleanup_old_cache_entries():
    """Remove stale cache entries to prevent memory leaks"""
    global last_cache_cleanup
    current_time = time.time()

    # Only run cleanup periodically
    if current_time - last_cache_cleanup < CACHE_CLEANUP_INTERVAL:
        return

    logger.info("Cleaning up stale SAM embedding cache entries")
    users_to_remove = []

    for user_id, user_cache in image_embedding_cache.items():
        paths_to_remove = []

        for image_path, cache_data in user_cache.items():
            if current_time - cache_data['timestamp'] > CACHE_ENTRY_TTL:
                paths_to_remove.append(image_path)

        for path in paths_to_remove:
            del user_cache[path]

        if not user_cache:
            users_to_remove.append(user_id)

    for user_id in users_to_remove:
        del image_embedding_cache[user_id]

    last_cache_cleanup = current_time
    logger.info(f"Cache cleanup complete. {len(image_embedding_cache)} users remain in cache")

def get_user_id(request: Request) -> str:
    """Get a consistent identifier for the current user session"""
    # Use client's IP address + user agent as a simple user identifier
    # In a production app, you would use proper session/user authentication
    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    return f"{client_host}:{user_agent}"

def get_sam2_predictor():
    """
    Initialize SAM2 predictor as a singleton to avoid costly reinitialization.
    """
    global sam2_predictor
    if sam2_predictor is None:
        try:
            from sam2.sam2_image_predictor import SAM2ImagePredictor
            logger.info("Initializing SAM2 predictor...")
            # We use tiny model for speed, but you can use other sizes like 'small', 'base_plus', or 'large'
            sam2_predictor = SAM2ImagePredictor.from_pretrained(
                SAM_MODEL_NAME,
                device="cuda" if torch.cuda.is_available() else "cpu"
            )
            logger.info("SAM2 predictor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SAM2 predictor: {e}")
            raise RuntimeError(f"Failed to initialize SAM2 predictor: {e}")
    return sam2_predictor

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

# Helper function to safely convert RLE annotation to dict
def rle_to_dict(rle_annotation):
    """
    Convert an RLE annotation to a dictionary, handling different Pydantic versions
    and object types.
    """
    try:
        # Get basic attributes using different methods depending on the object type
        if hasattr(rle_annotation, "model_dump"):
            # For newer Pydantic versions (v2+)
            result = rle_annotation.model_dump()
        elif hasattr(rle_annotation, "dict"):
            # For older Pydantic versions (v1)
            result = rle_annotation.dict()
        elif hasattr(rle_annotation, "__dict__"):
            # Fallback for objects with __dict__ attribute
            result = vars(rle_annotation)
        else:
            # Manual conversion
            result = {}

        # Always directly access the attributes to ensure we get the values
        # These are the critical fields we need for RLE data
        if hasattr(rle_annotation, "counts"):
            result["counts"] = rle_annotation.counts
        if hasattr(rle_annotation, "size"):
            result["size"] = rle_annotation.size
        if hasattr(rle_annotation, "image_path"):
            result["image_path"] = rle_annotation.image_path
        if hasattr(rle_annotation, "is_root_concept"):
            result["is_root_concept"] = rle_annotation.is_root_concept

        # Verify we have the critical fields with valid values
        if "counts" not in result or result["counts"] is None:
            logger.error(f"Missing 'counts' in RLE data: {result}")
            raise ValueError("Missing 'counts' field in RLE data")

        if "size" not in result or result["size"] is None:
            logger.error(f"Missing 'size' in RLE data: {result}")
            raise ValueError("Missing 'size' field in RLE data")

        # Ensure size is a list with 2 elements
        if not isinstance(result["size"], list) or len(result["size"]) != 2:
            logger.error(f"Invalid 'size' format in RLE data: {result['size']}")
            raise ValueError(f"Invalid 'size' format in RLE data: {result['size']}")

        # Log success
        logger.debug(f"Successfully converted RLE data: {result}")
        return result

    except Exception as e:
        logger.error(f"Error in rle_to_dict: {e}")
        # Don't return a fallback dict with None values
        # Instead, re-raise the exception so we can handle it properly
        raise

@router.post('/generate-mask-from-points')
async def generate_mask_from_points(prompt: PointPrompt):
    """
    Generate a mask using SAM2 from positive and negative point prompts.
    Returns RLE encoded mask.
    """
    try:
        from dataset.annotation import RLEAnnotation
        from pycocotools import mask as mask_utils
        import traceback

        # Log incoming request for debugging
        logger.info(f"Generate mask from points for image: {prompt.image_path}")
        logger.info(f"Positive points: {[(p.x, p.y) for p in prompt.positive_points]}")
        logger.info(f"Negative points: {[(p.x, p.y) for p in prompt.negative_points]}")

        # Get the predictor (initializes once)
        predictor = get_sam2_predictor()

        # Set image
        image = np.array(open_image(prompt.image_path))
        logger.info(f"Image loaded with shape: {image.shape}")
        predictor.set_image(image)

        # Convert points to format expected by SAM
        input_points = []
        input_labels = []

        for point in prompt.positive_points:
            input_points.append([point.x, point.y])
            input_labels.append(1)  # 1 for positive

        for point in prompt.negative_points:
            input_points.append([point.x, point.y])
            input_labels.append(0)  # 0 for negative

        # Convert to numpy arrays
        input_points = np.array(input_points)
        input_labels = np.array(input_labels)

        logger.info(f"Running prediction with {len(input_points)} points")

        # Run prediction
        masks, scores, _ = predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            multimask_output=True
        )

        # Log prediction results
        logger.info(f"Got {len(masks)} masks with scores: {scores}")

        # Get best mask based on score
        mask_idx = np.argmax(scores)
        best_mask = masks[mask_idx]
        logger.info(f"Selected mask {mask_idx} with score {scores[mask_idx]}")
        logger.info(f"Mask shape: {best_mask.shape}, type: {best_mask.dtype}")
        logger.info(f"Mask sum: {np.sum(best_mask)} (number of positive pixels)")

        # Convert to RLE
        fortran_mask = np.asfortranarray(best_mask.astype(np.uint8))
        rle = mask_utils.encode(fortran_mask)

        # Log RLE data
        logger.info(f"RLE generated with size: {rle['size']}")
        counts_preview = rle['counts']
        if isinstance(counts_preview, bytes):
            counts_preview = counts_preview.decode('utf-8')
        logger.info(f"RLE counts preview: {counts_preview[:30]}...")

        # Create RLE annotation
        rle_annotation = RLEAnnotation(
            counts=rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
            size=rle['size'],
            image_path=prompt.image_path,
            is_root_concept=False
        )

        # Use helper function to convert to dict
        try:
            rle_dict = rle_to_dict(rle_annotation)
            logger.info(f"Generated valid RLE dict with keys: {list(rle_dict.keys())}")

            # Double-check the critical fields
            if 'counts' not in rle_dict or rle_dict['counts'] is None:
                logger.error("Critical error: 'counts' is missing in final RLE dict")
                # Fix it directly
                rle_dict['counts'] = counts_preview

            if 'size' not in rle_dict or rle_dict['size'] is None:
                logger.error("Critical error: 'size' is missing in final RLE dict")
                # Fix it directly
                rle_dict['size'] = rle['size']

            # Final verification
            logger.info(f"Final RLE dict: {rle_dict}")

            return {
                "rle": rle_dict,
                "score": float(scores[mask_idx])
            }
        except Exception as rle_error:
            logger.error(f"Error creating RLE dict: {rle_error}")
            logger.error(traceback.format_exc())

            # Create a direct dictionary instead of using the helper
            direct_rle = {
                "counts": rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
                "size": rle['size'],
                "image_path": prompt.image_path,
                "is_root_concept": False
            }

            logger.info(f"Created direct RLE dict: {direct_rle}")

            return {
                "rle": direct_rle,
                "score": float(scores[mask_idx])
            }

    except Exception as e:
        logger.error(f"Error generating mask from points: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate mask: {str(e)}"
        )

@router.post('/generate-mask-from-polygon')
async def generate_mask_from_polygon(prompt: PolygonPrompt):
    """
    Generate a mask from polygon points.
    Returns RLE encoded mask.
    """
    try:
        from dataset.annotation import RLEAnnotation
        import cv2
        from pycocotools import mask as mask_utils
        import traceback

        # Log incoming request for debugging
        logger.info(f"Generate mask from polygon for image: {prompt.image_path}")
        logger.info(f"Polygon points: {[(p.x, p.y) for p in prompt.polygon_points]}")

        # Open image to get dimensions
        image = np.array(open_image(prompt.image_path))
        logger.info(f"Image loaded with shape: {image.shape}")
        height, width = image.shape[:2]

        # Create empty mask
        mask = np.zeros((height, width), dtype=np.uint8)

        # Convert points to format expected by cv2
        polygon_points = []
        for point in prompt.polygon_points:
            polygon_points.append([point.x, point.y])

        # Draw filled polygon
        points = np.array(polygon_points, dtype=np.int32)
        cv2.fillPoly(mask, [points], 1)

        # Log mask details
        logger.info(f"Created polygon mask with shape: {mask.shape}")
        logger.info(f"Mask sum: {np.sum(mask)} (number of positive pixels)")

        # Convert to RLE
        fortran_mask = np.asfortranarray(mask)
        rle = mask_utils.encode(fortran_mask)

        # Log RLE data
        logger.info(f"RLE generated with size: {rle['size']}")
        counts_preview = rle['counts']
        if isinstance(counts_preview, bytes):
            counts_preview = counts_preview.decode('utf-8')
        logger.info(f"RLE counts preview: {counts_preview[:30]}...")

        # Create RLE annotation
        rle_annotation = RLEAnnotation(
            counts=rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
            size=rle['size'],
            image_path=prompt.image_path,
            is_root_concept=False
        )

        # Use helper function to convert to dict
        try:
            rle_dict = rle_to_dict(rle_annotation)
            logger.info(f"Generated valid RLE dict with keys: {list(rle_dict.keys())}")

            # Double-check the critical fields
            if 'counts' not in rle_dict or rle_dict['counts'] is None:
                logger.error("Critical error: 'counts' is missing in final RLE dict")
                # Fix it directly
                rle_dict['counts'] = counts_preview

            if 'size' not in rle_dict or rle_dict['size'] is None:
                logger.error("Critical error: 'size' is missing in final RLE dict")
                # Fix it directly
                rle_dict['size'] = rle['size']

            # Final verification
            logger.info(f"Final RLE dict: {rle_dict}")

            return {
                "rle": rle_dict
            }
        except Exception as rle_error:
            logger.error(f"Error creating RLE dict: {rle_error}")
            logger.error(traceback.format_exc())

            # Create a direct dictionary instead of using the helper
            direct_rle = {
                "counts": rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
                "size": rle['size'],
                "image_path": prompt.image_path,
                "is_root_concept": False
            }

            logger.info(f"Created direct RLE dict: {direct_rle}")

            return {
                "rle": direct_rle
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
        # Run cache cleanup on each request
        cleanup_old_cache_entries()

        from dataset.annotation import RLEAnnotation
        from pycocotools import mask as mask_utils

        # Log incoming points data for debugging
        positive_count = len(prompt.positive_points) if prompt.positive_points else 0
        negative_count = len(prompt.negative_points) if prompt.negative_points else 0
        logger.info(f"Preview mask requested with {positive_count} positive points and {negative_count} negative points")

        if positive_count > 0:
            # Log a few points for debugging
            for i, pt in enumerate(prompt.positive_points[:2]):
                logger.info(f"Positive point {i}: x={pt.x}, y={pt.y}")

        # Get the predictor (initializes once)
        predictor = get_sam2_predictor()

        # Get user-specific identifier
        user_id = get_user_id(request)

        # Initialize user's cache if not exists
        if user_id not in image_embedding_cache:
            image_embedding_cache[user_id] = {}

        user_cache = image_embedding_cache[user_id]

        # Only set the image if it's not in the user's cache
        if prompt.image_path not in user_cache:
            # Set image
            logger.info(f"For numpy array image, we assume (HxWxC) format")
            image = np.array(open_image(prompt.image_path))
            original_size = image.shape[:2]  # Store original size (height, width)
            logger.info(f"Image shape: {original_size}")

            # Set image in predictor and save embeddings in cache
            logger.info(f"Computing image embeddings for the provided image...")
            predictor.set_image(image)
            logger.info(f"Image embeddings computed.")

            # Store in cache with timestamp
            user_cache[prompt.image_path] = {
                'original_size': original_size,
                'timestamp': time.time()
            }

            logger.info(f"Image embeddings computed for user {user_id}, image: {prompt.image_path}")
        else:
            # Update timestamp on cache hit
            user_cache[prompt.image_path]['timestamp'] = time.time()
            original_size = user_cache[prompt.image_path]['original_size']
            logger.info(f"Reusing existing image embeddings for user {user_id}, image: {prompt.image_path}")

        # Convert points to format expected by SAM
        input_points = []
        input_labels = []

        for point in prompt.positive_points:
            input_points.append([point.x, point.y])
            input_labels.append(1)  # 1 for positive

        for point in prompt.negative_points:
            input_points.append([point.x, point.y])
            input_labels.append(0)  # 0 for negative

        # Convert to numpy arrays
        input_points = np.array(input_points)
        input_labels = np.array(input_labels)

        logger.info(f"Running SAM2 prediction with {len(input_points)} points")

        # Run prediction
        masks, scores, _ = predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            multimask_output=True
        )

        # Get best mask based on score
        mask_idx = np.argmax(scores)
        best_score = scores[mask_idx]
        best_mask = masks[mask_idx]

        logger.info(f"Prediction complete. Best mask index: {mask_idx}, score: {best_score:.4f}, mask shape: {best_mask.shape}")

        # Ensure the mask matches the original image size
        if original_size and best_mask.shape != original_size:
            logger.warning(f"Mask size mismatch: {best_mask.shape} vs original {original_size}")
            # Resize mask if needed (should be handled by SAM2 already but just in case)
            from PIL import Image
            pil_mask = Image.fromarray(best_mask.astype(np.uint8) * 255)
            pil_mask = pil_mask.resize((original_size[1], original_size[0]), Image.NEAREST)
            best_mask = np.array(pil_mask) > 0

        # Check if mask contains any positive pixels
        mask_sum = np.sum(best_mask)
        logger.info(f"Mask sum (number of positive pixels): {mask_sum}")

        if mask_sum == 0:
            logger.warning("Mask is empty (all zeros)")

        # Convert to RLE
        fortran_mask = np.asfortranarray(best_mask.astype(np.uint8))
        rle = mask_utils.encode(fortran_mask)

        # Create RLE annotation
        rle_annotation = RLEAnnotation(
            counts=rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
            size=rle['size'],
            image_path=prompt.image_path,
            is_root_concept=False
        )

        # Log the RLE data for debugging
        logger.info(f"Generated RLE annotation with size: {rle['size']}")

        counts_preview = rle['counts']
        if isinstance(counts_preview, bytes):
            counts_preview = counts_preview.decode('utf-8')
        logger.info(f"RLE counts preview: {counts_preview[:30]}...")

        # Use helper function to convert to dict
        rle_dict = rle_to_dict(rle_annotation)
        logger.info(f"RLE dict created with keys: {list(rle_dict.keys())}")

        # Ensure all required fields are present and have values
        if 'counts' not in rle_dict or rle_dict['counts'] is None:
            rle_dict['counts'] = counts_preview
            logger.warning(f"RLE counts was missing or None, setting from original: {counts_preview[:30]}...")

        if 'size' not in rle_dict or rle_dict['size'] is None:
            rle_dict['size'] = rle['size']
            logger.warning(f"RLE size was missing or None, setting from original: {rle['size']}")

        # Double-check the final RLE dict
        logger.info(f"Final RLE dict: {rle_dict}")

        return {
            "rle": rle_dict,
            "score": float(scores[mask_idx])
        }

    except Exception as e:
        logger.error(f"Error generating preview mask from points: {e}")
        import traceback
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
        # Run cache cleanup on each request
        cleanup_old_cache_entries()

        from dataset.annotation import RLEAnnotation
        import cv2
        from pycocotools import mask as mask_utils

        # Get user-specific identifier
        user_id = get_user_id(request)

        # Initialize user's cache if not exists
        if user_id not in image_embedding_cache:
            image_embedding_cache[user_id] = {}

        user_cache = image_embedding_cache[user_id]

        # Only open the image if it's not in the user's cache
        if prompt.image_path not in user_cache:
            # Open image to get dimensions
            image = np.array(open_image(prompt.image_path))
            height, width = image.shape[:2]

            # Store in cache with timestamp
            user_cache[prompt.image_path] = {
                'original_size': (height, width),
                'timestamp': time.time()
            }

            logger.info(f"Image size computed for user {user_id}, image: {prompt.image_path}")
        else:
            # Update timestamp on cache hit
            user_cache[prompt.image_path]['timestamp'] = time.time()
            height, width = user_cache[prompt.image_path]['original_size']
            logger.info(f"Reusing existing image size for user {user_id}, image: {prompt.image_path}")

        # Create empty mask
        mask = np.zeros((height, width), dtype=np.uint8)

        # Convert points to format expected by cv2
        polygon_points = []
        for point in prompt.polygon_points:
            polygon_points.append([point.x, point.y])

        # Draw filled polygon
        points = np.array(polygon_points, dtype=np.int32)
        cv2.fillPoly(mask, [points], 1)

        # Ensure the mask matches the original image dimensions
        original_size = user_cache[prompt.image_path]['original_size']
        if original_size and (mask.shape[0] != original_size[0] or mask.shape[1] != original_size[1]):
            logger.warning(f"Mask size mismatch: {mask.shape} vs original {original_size}")
            # Resize mask if needed
            from PIL import Image
            pil_mask = Image.fromarray(mask)
            pil_mask = pil_mask.resize((original_size[1], original_size[0]), Image.NEAREST)
            mask = np.array(pil_mask) > 0

        # Convert to RLE (Run-Length Encoding)
        fortran_mask = np.asfortranarray(mask.astype(np.uint8))
        rle = mask_utils.encode(fortran_mask)

        # Create RLE annotation
        rle_annotation = RLEAnnotation(
            counts=rle['counts'].decode() if isinstance(rle['counts'], bytes) else rle['counts'],
            size=rle['size'],
            image_path=prompt.image_path,
            is_root_concept=False
        )

        # Use helper function to convert to dict
        rle_dict = rle_to_dict(rle_annotation)

        # Log success
        logger.info(f"Successfully generated polygon mask with dimensions {mask.shape}")

        return {
            "rle": rle_dict
        }

    except Exception as e:
        logger.error(f"Error generating mask from polygon: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate mask: {str(e)}"
        )