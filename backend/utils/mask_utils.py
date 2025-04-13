import numpy as np
import logging
import json
import traceback
from typing import Dict, Union, List, Optional
from PIL import Image
from pycocotools import mask as mask_utils

from utils.image_utils import convert_to_pil_image
from render_mask import image_from_masks

logger = logging.getLogger(__name__)

def process_rle_data(rle_data: Union[str, Dict], image_width: int, image_height: int) -> Dict:
    """Process and validate RLE data, ensuring it's properly formatted"""
    # Handle string or dict RLE data
    if isinstance(rle_data, str):
        try:
            rle_dict = json.loads(rle_data)
            logger.info(f"Successfully parsed RLE JSON string into dict")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse RLE string as JSON: {e}")
            raise ValueError(f"Invalid RLE data format: {str(e)}")
    else:
        rle_dict = rle_data

    # Validate the RLE dictionary
    if not isinstance(rle_dict, dict):
        logger.error(f"RLE data is not a dict: {type(rle_dict)}")
        raise ValueError("RLE data must be a dictionary or JSON string")

    # Validate required fields
    if 'counts' not in rle_dict:
        logger.error(f"RLE data missing 'counts' field. Available keys: {list(rle_dict.keys())}")
        raise ValueError("RLE data must contain 'counts' field")

    if 'size' not in rle_dict:
        logger.error(f"RLE data missing 'size' field. Available keys: {list(rle_dict.keys())}")
        raise ValueError("RLE data must contain 'size' field")

    # Make a copy of the dict to avoid modifying the original
    rle_copy = dict(rle_dict)

    # Handle the counts field
    counts = rle_copy['counts']
    if isinstance(counts, str):
        logger.info(f"Converting string RLE counts (length: {len(counts)}) to bytes")
        rle_copy['counts'] = counts.encode('utf-8')
    elif not isinstance(counts, bytes):
        logger.error(f"RLE counts has invalid type: {type(counts)}")
        raise ValueError(f"RLE counts must be string or bytes, not {type(counts)}")

    # Ensure size matches the image dimensions
    size = rle_copy['size']
    if not isinstance(size, list) or len(size) != 2:
        logger.error(f"Invalid size format: {size}")
        raise ValueError(f"RLE size must be a list with 2 elements, not {size}")

    # Optionally adjust size to match image dimensions
    if size[0] != image_height or size[1] != image_width:
        logger.warning(f"RLE size {size} doesn't match image {image_height}x{image_width}. Adjusting.")
        rle_copy['size'] = [image_height, image_width]

    return rle_copy

def decode_rle_to_mask(rle: Dict) -> np.ndarray:
    """Decode RLE data to binary mask"""
    try:
        mask = mask_utils.decode(rle)
        mask_sum = np.sum(mask)
        logger.info(f"Successfully decoded RLE to mask with shape {mask.shape}, sum: {mask_sum}")
        return mask
    except Exception as e:
        logger.error(f"Failed to decode RLE: {e}")
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to decode RLE: {e}")

def encode_mask_to_rle(mask: np.ndarray) -> Dict:
    """Encode binary mask to RLE format"""
    try:
        # Ensure the mask is a valid binary mask
        mask = mask.astype(np.uint8)

        # Use pycocotools to encode the mask
        rle = mask_utils.encode(np.asfortranarray(mask))

        # Convert to Python-friendly format (convert bytes to string)
        rle_for_json = {
            'counts': rle['counts'].decode('utf-8') if isinstance(rle['counts'], bytes) else rle['counts'],
            'size': rle['size'].tolist() if hasattr(rle['size'], 'tolist') else rle['size']
        }

        return rle_for_json
    except Exception as e:
        logger.error(f"Failed to encode mask to RLE: {e}")
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to encode mask to RLE: {e}")

def create_empty_mask(width: int, height: int) -> np.ndarray:
    """Create an empty binary mask with given dimensions"""
    return np.zeros((height, width), dtype=np.uint8)

def create_mask_from_polygon(polygon_points: List[List[int]], width: int, height: int) -> np.ndarray:
    """Create a binary mask from polygon points"""
    # Create an empty mask
    mask_img = Image.new('L', (width, height), 0)

    # Convert points to tuple format for PIL drawing
    points = [(p[0], p[1]) for p in polygon_points]

    # Draw the polygon
    from PIL import ImageDraw
    draw = ImageDraw.Draw(mask_img)
    draw.polygon(points, fill=1)

    # Convert to numpy array
    mask = np.array(mask_img)

    return mask

def create_mask_image(
    mask_array: np.ndarray,
    base_image: Optional[Image.Image] = None,
    overlay: bool = True,
    color: str = 'red',
    alpha: float = 0.7
) -> Image.Image:
    """Create a mask image from a binary mask array, with optional overlay on base image"""
    # Stack mask to expected format for image_from_masks
    mask_stack = np.expand_dims(mask_array, axis=0)

    try:
        if overlay and base_image is not None:
            # Overlay mask on the original image with transparency
            logger.info("Creating overlay with image_from_masks")
            result_image = image_from_masks(
                masks=mask_stack,
                combine_as_binary_mask=True,
                combine_color=color,
                superimpose_on_image=base_image,
                superimpose_alpha=alpha
            )
        else:
            # Just return the mask with a visible color
            logger.info("Creating mask-only image")
            result_image = image_from_masks(
                masks=mask_stack,
                combine_as_binary_mask=True,
                combine_color=color
            )

        # Ensure result is a PIL Image
        if not isinstance(result_image, Image.Image):
            logger.info(f"Converting result of type {type(result_image)} to PIL Image")
            result_image = convert_to_pil_image(result_image)

        # Ensure image is RGB mode for consistent output
        if result_image.mode != 'RGB':
            logger.info(f"Converting image from mode {result_image.mode} to RGB")
            result_image = result_image.convert('RGB')

        return result_image
    except Exception as e:
        logger.error(f"Error in create_mask_image: {e}")
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to create mask image: {str(e)}")

def combine_masks(masks: List[np.ndarray]) -> np.ndarray:
    """Combine multiple binary masks into a single mask"""
    if not masks:
        raise ValueError("No masks provided to combine")

    # Check dimensions
    shape = masks[0].shape
    for i, mask in enumerate(masks):
        if mask.shape != shape:
            raise ValueError(f"Mask {i} has different shape {mask.shape} than first mask {shape}")

    # Combine masks (logical OR)
    combined = np.zeros(shape, dtype=np.uint8)
    for mask in masks:
        combined = np.logical_or(combined, mask).astype(np.uint8)

    return combined