import logging
import time
import numpy as np
import torch
from typing import Dict, Any, List, Optional
from fastapi import Request
from root_utils import open_image

logger = logging.getLogger(__name__)

# SAM2 predictor singleton
sam2_predictor = None
SAM_MODEL_NAME = "facebook/sam2.1-hiera-base-plus"

# User-specific image embedding cache for SAM2
# Format: { 'user_id': { 'image_path': {'embeddings': data, 'timestamp': time, 'size': (h,w), 'masks': {'part_name': {'mask': mask_data, 'logits': logits_data}} } } }
# The 'masks' field caches the per-part most recent mask and logits for improved prediction
image_embedding_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
CACHE_CLEANUP_INTERVAL = 3600  # seconds (1 hour)
CACHE_ENTRY_TTL = 1800  # seconds (30 minutes)
last_cache_cleanup = time.time()

def get_user_id(request: Request) -> str:
    '''Get a consistent identifier for the current user session via cookie.

    Raises if the cookie is missing.'''
    sid = request.cookies.get("annotator_session")
    if not sid:
        # client didn’t send a session cookie—fail fast to debug
        raise RuntimeError("Missing annotator_session cookie")
    return sid

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

def get_sam2_predictor():
    """
    Initialize SAM2 predictor as a singleton to avoid costly reinitialization.
    """
    global sam2_predictor
    if sam2_predictor is None:
        try:
            from sam2.sam2_image_predictor import SAM2ImagePredictor
            logger.info("Initializing SAM2 predictor...")
            sam2_predictor = SAM2ImagePredictor.from_pretrained(
                SAM_MODEL_NAME,
                device="cuda" if torch.cuda.is_available() else "cpu"
            )
            logger.info("SAM2 predictor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SAM2 predictor: {e}")
            raise RuntimeError(f"Failed to initialize SAM2 predictor: {e}")
    return sam2_predictor

def ensure_clean_image_cache(user_id: str, image_path: str):
    """
    Ensure that when a user starts working on an image, they have a clean cache.
    This prevents one user's previous masks from affecting another user.
    """
    # First check if the user exists in the cache
    if user_id not in image_embedding_cache:
        image_embedding_cache[user_id] = {}
        logger.info(f"Created new cache entry for user: {user_id}")
        return

    # Check if this user has this image in their cache
    if image_path not in image_embedding_cache[user_id]:
        # User doesn't have this image cached yet, which is fine
        return

    # If the user already has this image cached, we're good - they're continuing their own work
    logger.info(f"User {user_id} already has a cache for image {image_path}")

def process_point_prompt(image_path: str, user_id: str, positive_points: List, negative_points: List,
                         part_name: Optional[str] = None, use_cached_logits: bool = True):
    """
    Process point prompts to generate a mask using SAM2
    """
    # Run cache cleanup on each request
    cleanup_old_cache_entries()

    # Get the predictor (initializes once)
    predictor = get_sam2_predictor()

    # Make sure this user has their own clean cache for this image
    ensure_clean_image_cache(user_id, image_path)

    # Initialize user's cache if not exists
    if user_id not in image_embedding_cache:
        image_embedding_cache[user_id] = {}

    user_cache = image_embedding_cache[user_id]

    # Set the image if not in cache
    if image_path not in user_cache:
        # Set image
        logger.info(f"For numpy array image, we assume (HxWxC) format")
        image = np.array(open_image(image_path))
        original_size = image.shape[:2]  # Store original size (height, width)
        logger.info(f"Image shape: {original_size}")

        # Set image in predictor and save embeddings in cache
        logger.info(f"Computing image embeddings for the provided image...")
        predictor.set_image(image)

        # Store in cache with timestamp
        user_cache[image_path] = {
            'original_size': original_size,
            'timestamp': time.time(),
            'masks': {}  # Initialize masks dictionary for this image
        }

        logger.debug(f"Image embeddings computed for user {user_id}, image: {image_path}")
    else:
        # Update timestamp on cache hit
        user_cache[image_path]['timestamp'] = time.time()
        original_size = user_cache[image_path]['original_size']
        logger.info(f"Reusing existing image embeddings for user {user_id}, image: {image_path}")

        # Make sure we have a masks dictionary
        if 'masks' not in user_cache[image_path]:
            user_cache[image_path]['masks'] = {}

    # Convert points to format expected by SAM
    input_points = []
    input_labels = []

    for point in positive_points:
        input_points.append([point.x, point.y])
        input_labels.append(1)  # 1 for positive

    for point in negative_points:
        input_points.append([point.x, point.y])
        input_labels.append(0)  # 0 for negative

    # Convert to numpy arrays
    input_points = np.array(input_points)
    input_labels = np.array(input_labels)

    logger.info(f"Running SAM2 prediction with {len(input_points)} points")

    # Try to use cached logits for this part if available
    cached_logits = None
    if use_cached_logits and part_name and part_name in user_cache[image_path].get('masks', {}):
        part_cache = user_cache[image_path]['masks'][part_name]
        if 'logits' in part_cache:
            cached_logits = part_cache['logits']
            logger.info(f"Found cached logits for part: {part_name}")

    # Run prediction with cached logits if available
    if cached_logits is not None:
        logger.info("Using cached logits for prediction")
        masks, scores, logits = predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            mask_input=cached_logits[None, :, :],  # Add batch dimension
            multimask_output=True
        )
    else:
        # Standard prediction without mask_input
        logger.info("Running standard prediction without mask_input")
        masks, scores, logits = predictor.predict(
            point_coords=input_points,
            point_labels=input_labels,
            multimask_output=True
        )

    # Get best mask based on score
    mask_idx = np.argmax(scores)
    best_score = scores[mask_idx]
    best_mask = masks[mask_idx]
    best_logits = logits[mask_idx]

    logger.info(f"Prediction complete. Best mask index: {mask_idx}, score: {best_score:.4f}")

    # Save this mask and logits to the cache if we have a part name
    if part_name:
        user_cache[image_path]['masks'][part_name] = {
            'mask': best_mask,
            'logits': best_logits
        }
        logger.info(f"Cached mask and logits for part: {part_name}")

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

    return best_mask, best_score, best_logits

def process_polygon_prompt(image_path: str, user_id: str, polygon_points: List):
    """
    Process polygon points to generate a mask
    """
    # Run cache cleanup
    cleanup_old_cache_entries()

    # Make sure this user has their own clean cache for this image
    ensure_clean_image_cache(user_id, image_path)

    # Initialize user's cache if not exists
    if user_id not in image_embedding_cache:
        image_embedding_cache[user_id] = {}

    user_cache = image_embedding_cache[user_id]

    # Only open the image if it's not in the user's cache
    if image_path not in user_cache:
        # Open image to get dimensions
        image = np.array(open_image(image_path))
        height, width = image.shape[:2]

        # Store in cache with timestamp
        user_cache[image_path] = {
            'original_size': (height, width),
            'timestamp': time.time(),
            'masks': {}  # Initialize masks dictionary
        }

        logger.info(f"Image size computed for user {user_id}, image: {image_path}")
    else:
        # Update timestamp on cache hit
        user_cache[image_path]['timestamp'] = time.time()
        height, width = user_cache[image_path]['original_size']
        logger.info(f"Reusing existing image size for user {user_id}, image: {image_path}")

        # Ensure we have a masks dictionary
        if 'masks' not in user_cache[image_path]:
            user_cache[image_path]['masks'] = {}

    # Create empty mask for the polygon
    import cv2
    mask = np.zeros((height, width), dtype=np.uint8)

    # Convert points to format expected by cv2
    points_list = []
    for point in polygon_points:
        points_list.append([point.x, point.y])

    # Draw filled polygon
    points = np.array(points_list, dtype=np.int32)
    cv2.fillPoly(mask, [points], 1)

    # Ensure the mask matches the original image dimensions
    original_size = user_cache[image_path]['original_size']
    if original_size and (mask.shape[0] != original_size[0] or mask.shape[1] != original_size[1]):
        logger.warning(f"Mask size mismatch: {mask.shape} vs original {original_size}")
        # Resize mask if needed
        from PIL import Image
        pil_mask = Image.fromarray(mask)
        pil_mask = pil_mask.resize((original_size[1], original_size[0]), Image.NEAREST)
        mask = np.array(pil_mask) > 0

    return mask

def clear_user_cache_for_image(image_path: str):
    """
    Clear cached masks for an image across all users when saving annotations
    """
    for user_id in image_embedding_cache:
        if image_path in image_embedding_cache[user_id]:
            if 'masks' in image_embedding_cache[user_id][image_path]:
                logger.info(f"Clearing cached masks for image {image_path} for user {user_id}")
                image_embedding_cache[user_id][image_path]['masks'] = {}