from PIL import Image, ImageDraw
import io
import logging
import base64
import numpy as np
from typing import Tuple, Optional, Union, Dict, Any

logger = logging.getLogger(__name__)

def image_to_base64(image: Image.Image, format='PNG') -> str:
    """Convert PIL Image to base64 string with optimized compression"""
    img_byte_arr = io.BytesIO()

    # Use PNG for binary masks as it's much better at compressing them
    # Set compress_level to 3 (0-9 scale) for a balance of speed and size
    if format.upper() == 'PNG':
        image.save(img_byte_arr, format=format, compress_level=3)
    elif format.upper() == 'JPEG':
        # For JPEG, use quality=85 for good compression without visible artifacts
        image.save(img_byte_arr, format=format, quality=85, optimize=True)
    else:
        # Default save with format-specific parameters
        image.save(img_byte_arr, format=format)

    img_byte_arr.seek(0)
    img_bytes = img_byte_arr.getvalue()

    # Log the size of the encoded image
    logger.debug(f"Base64 encoding image, byte size: {len(img_bytes)}")

    return base64.b64encode(img_bytes).decode('utf-8')

def pil_image_to_byte_stream(image: Image.Image, format='PNG', quality=None) -> io.BytesIO:
    """Convert PIL image to byte stream for streaming response"""
    img_byte_arr = io.BytesIO()

    if format.upper() == 'PNG':
        image.save(img_byte_arr, format=format, compress_level=3)
    elif format.upper() == 'JPEG':
        # For JPEG, use quality=85 for good compression without visible artifacts
        image.save(img_byte_arr, format=format, quality=quality or 85, optimize=True)
    else:
        # Default save with format-specific parameters
        image.save(img_byte_arr, format=format)

    img_byte_arr.seek(0)
    return img_byte_arr

def create_error_image(message: str, width=400, height=300) -> Image.Image:
    """Create a simple error image with the given message"""
    error_img = Image.new('RGB', (width, height), color=(255, 200, 200))
    draw = ImageDraw.Draw(error_img)
    draw.text((20, 150), f"Error: {message[:50]}...", fill=(0, 0, 0))
    return error_img

def convert_to_pil_image(image_data) -> Image.Image:
    """Convert various image data formats to PIL Image"""
    if isinstance(image_data, Image.Image):
        return image_data

    if hasattr(image_data, 'numpy') and callable(getattr(image_data, 'numpy')):
        # Handle PyTorch tensor
        result_array = image_data.numpy()
        if result_array.ndim == 3 and result_array.shape[0] == 3:
            # Channel-first format (C, H, W)
            return Image.fromarray((result_array.transpose(1, 2, 0) * 255).astype(np.uint8))
        else:
            # Other tensor formats
            return Image.fromarray((result_array * 255).astype(np.uint8))
    elif isinstance(image_data, np.ndarray):
        # Handle numpy array
        if image_data.ndim == 3:
            if image_data.shape[0] == 3:
                # Channel-first format (C, H, W)
                return Image.fromarray((image_data.transpose(1, 2, 0) * 255).astype(np.uint8))
            else:
                # Assume channel-last format (H, W, C)
                return Image.fromarray((image_data * 255).astype(np.uint8))
        else:
            # For grayscale
            return Image.fromarray((image_data * 255).astype(np.uint8))
    else:
        raise ValueError(f"Cannot convert type {type(image_data)} to PIL Image")

def load_image_from_path(image_path: str, allow_large_images: bool = True) -> Tuple[Image.Image, int, int]:
    """Load an image and return it with dimensions

    Args:
        image_path: Path to the image file
        allow_large_images: If True, disable PIL's size limit for large images

    Returns:
        Tuple of (image, width, height)
    """
    try:
        # Check if file exists and is readable
        import os
        if not os.path.isfile(image_path):
            logger.error(f"Image file not found: {image_path}")
            raise ValueError(f"Image file not found: {image_path}")

        if not os.access(image_path, os.R_OK):
            logger.error(f"Image file not readable: {image_path}")
            raise ValueError(f"Image file not readable: {image_path}")

        # Log file size
        file_size_bytes = os.path.getsize(image_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        logger.info(f"Image file size: {file_size_mb:.2f} MB")

        # For very large images, disable PIL's size limit
        if allow_large_images:
            # Save the original value to restore it later
            original_max_pixels = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = None

        # Set up to handle truncated images
        from PIL import ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True

        # Try to open the image
        from root_utils import open_image
        try:
            # First try the custom open_image from root_utils
            base_image = open_image(image_path)
        except Exception as e:
            logger.warning(f"Custom open_image failed: {e}, trying PIL directly")
            # Fall back to direct PIL open
            base_image = Image.open(image_path)

        # Ensure the image is loaded fully
        base_image.load()

        # Get dimensions
        width, height = base_image.size
        logger.info(f"Successfully opened image with dimensions {width}x{height} (format: {base_image.format}, mode: {base_image.mode})")

        # For very large images, consider resize
        max_dimension = 4000  # Arbitrary limit based on common browser/memory constraints
        if width > max_dimension or height > max_dimension:
            logger.warning(f"Image is very large ({width}x{height}), this may cause display issues")

        # Restore the original max pixels setting if we changed it
        if allow_large_images and original_max_pixels is not None:
            Image.MAX_IMAGE_PIXELS = original_max_pixels

        return base_image, width, height
    except Exception as e:
        logger.error(f"Failed to open image {image_path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise ValueError(f"Failed to open image: {str(e)}")

def create_debug_overlay(base_image: Image.Image, text: Optional[str] = None) -> Image.Image:
    """Create a debug overlay with a red rectangle and optional text"""
    width, height = base_image.size

    # Create a test overlay with a solid red rectangle
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw a rectangle in the center (1/3 of the image size)
    rect_width = width // 3
    rect_height = height // 3
    rect_x = (width - rect_width) // 2
    rect_y = (height - rect_height) // 2
    draw.rectangle(
        [(rect_x, rect_y), (rect_x + rect_width, rect_y + rect_height)],
        fill=(255, 0, 0, 180)  # Semi-transparent red
    )

    # Convert base image to RGBA if it's not already
    if base_image.mode != 'RGBA':
        base_image = base_image.convert('RGBA')

    # Overlay the test shape
    result_image = Image.alpha_composite(base_image, overlay)

    # Convert back to RGB for JPEG compatibility
    result_image = result_image.convert('RGB')

    # Add text if provided
    if text:
        draw = ImageDraw.Draw(result_image)
        draw.text((10, 10), text, fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=2)

    return result_image