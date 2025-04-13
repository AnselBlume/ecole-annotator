from fastapi import HTTPException, APIRouter, Query, Response
from fastapi.responses import StreamingResponse, JSONResponse
from PIL.Image import Image as PILImage
import io
import logging
from render_mask import get_combined_mask_image, image_from_masks
import base64
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

def image_to_base64(image, format='PNG'):
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

@router.get('/render-mask')
def render_combined_mask(
    image_path: str = Query(...),
    parts: str = Query(...)
):
    '''
    Dynamically generates a mask image for the selected parts and returns it.

    Args:
        image_path: path to the base image
        parts: comma-separated list of part names

    Returns:
        A streaming JPEG image response
    '''
    try:
        part_list = parts.split(',')
        logging.info(f'Rendering mask for {image_path} with parts {part_list}')
        mask_image: PILImage = get_combined_mask_image(image_path, part_list)

        # Convert to byte stream
        img_byte_arr = io.BytesIO()
        # Use PNG for better quality with masks
        mask_image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        return StreamingResponse(img_byte_arr, media_type='image/png')

    except Exception as e:
        logging.error(f'Failed to generate mask for {image_path} parts {parts}: {e}')
        raise HTTPException(status_code=500, detail=f'Could not generate mask: {str(e)}')

@router.get('/render-preview')
def render_mask_preview(
    image_path: str = Query(...),
    rle_data: str = Query(None),
    overlay: bool = Query(False)
):
    '''
    Dynamically renders a mask preview from RLE data.
    This is used for real-time visualization during annotation.

    Args:
        image_path: path to the base image
        rle_data: RLE data for the mask (JSON string)
        overlay: Whether to overlay the mask on the original image

    Returns:
        A streaming PNG image response
    '''
    try:
        from pycocotools import mask as mask_utils
        import numpy as np
        from PIL import Image, ImageDraw
        from root_utils import open_image
        import json
        from render_mask import image_from_masks
        import traceback

        # Log the incoming data for debugging
        logger.info(f"Rendering preview mask for {image_path}, overlay={overlay}")
        if rle_data:
            # Log only the first 100 chars of RLE data to avoid excessive logging
            rle_preview = rle_data[:100] + "..." if len(rle_data) > 100 else rle_data
            logger.info(f"RLE data preview: {rle_preview}")
        else:
            logger.info("No RLE data provided")
            return Response(
                content=json.dumps({"error": "No RLE data provided"}),
                media_type="application/json",
                status_code=400
            )

        # Open the base image
        try:
            base_image = open_image(image_path)
            width, height = base_image.size
            logger.info(f"Successfully opened base image with dimensions {width}x{height}")
        except Exception as e:
            logger.error(f"Failed to open base image {image_path}: {e}")
            # Return a placeholder error image
            error_img = Image.new('RGB', (400, 300), color=(255, 200, 200))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error loading image: {str(e)[:50]}...", fill=(0, 0, 0))
            img_byte_arr = io.BytesIO()
            error_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            return StreamingResponse(img_byte_arr, media_type='image/png')

        # Create empty mask as default
        mask = np.zeros((height, width), dtype=np.uint8)

        # Process RLE data if provided
        if rle_data:
            try:
                # Parse RLE data from JSON string
                logger.info("Parsing RLE data from JSON string")
                rle_dict = json.loads(rle_data)
                logger.info(f"RLE data keys: {list(rle_dict.keys()) if isinstance(rle_dict, dict) else 'not a dict'}")

                # Validate that we have the required fields
                if not isinstance(rle_dict, dict):
                    raise ValueError("RLE data must be a dictionary")

                if 'counts' not in rle_dict:
                    raise ValueError("Missing 'counts' field in RLE data")

                if 'size' not in rle_dict:
                    raise ValueError("Missing 'size' field in RLE data")

                # Make a copy of the dict to avoid modifying the original
                rle_copy = dict(rle_dict)
                counts = rle_copy['counts']

                # Convert string counts to bytes if needed
                if isinstance(counts, str):
                    rle_copy['counts'] = counts.encode('utf-8')
                    logger.info("Converted RLE counts from string to bytes")
                elif not isinstance(counts, bytes):
                    raise ValueError(f"RLE counts must be string or bytes, got {type(counts)}")

                # Ensure size format is valid
                if not isinstance(rle_copy['size'], list) or len(rle_copy['size']) != 2:
                    raise ValueError(f"RLE size must be a list with 2 elements, got {rle_copy['size']}")

                # Optionally adjust size to match image dimensions
                if rle_copy['size'][0] != height or rle_copy['size'][1] != width:
                    logger.warning(f"Adjusting RLE size to match image: {height}x{width}")
                    rle_copy['size'] = [height, width]

                # Decode the RLE
                try:
                    mask = mask_utils.decode(rle_copy)
                    mask_sum = np.sum(mask)
                    logger.info(f"Successfully decoded RLE to mask with shape {mask.shape}, sum: {mask_sum}")
                except Exception as e:
                    logger.error(f"Failed to decode RLE: {e}")
                    logger.error(traceback.format_exc())
                    raise ValueError(f"Failed to decode RLE: {e}")
            except Exception as e:
                logger.error(f"Failed to process RLE data: {e}")
                logger.error(traceback.format_exc())
                # Create an error image
                error_img = Image.new('RGB', (400, 300), color=(255, 200, 200))
                draw = ImageDraw.Draw(error_img)
                draw.text((20, 150), f"RLE error: {str(e)[:50]}...", fill=(0, 0, 0))
                img_byte_arr = io.BytesIO()
                error_img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                return StreamingResponse(img_byte_arr, media_type='image/png')

        # Stack the mask to create the format expected by image_from_masks
        mask_stack = np.expand_dims(mask, axis=0)
        logger.info(f"Mask stack shape: {mask_stack.shape}, max value: {np.max(mask_stack)}, sum: {np.sum(mask_stack)}")

        # Use image_from_masks to generate the mask image
        try:
            if overlay:
                # Overlay on the original image with transparency
                logger.info("Creating overlay with image_from_masks")
                result_image = image_from_masks(
                    masks=mask_stack,
                    combine_as_binary_mask=True,
                    combine_color='red',
                    superimpose_on_image=base_image,
                    superimpose_alpha=0.7
                )
                logger.info("Successfully created overlay image")
            else:
                # Just return the mask with a visible color
                logger.info("Creating mask-only image with image_from_masks")
                result_image = image_from_masks(
                    masks=mask_stack,
                    combine_as_binary_mask=True,
                    combine_color='red'
                )
                logger.info("Created mask-only image")

        except Exception as e:
            logger.error(f"Error in image_from_masks: {e}")
            logger.error(traceback.format_exc())
            # Create a basic error visualization
            error_img = Image.new('RGB', (400, 300), color=(255, 220, 220))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error: {str(e)[:100]}", fill=(0, 0, 0))
            result_image = error_img

        # Convert to byte stream
        img_byte_arr = io.BytesIO()

        # Determine type of result_image and convert to PIL if needed
        if isinstance(result_image, Image.Image):
            # Ensure the image is in RGB mode for consistent output
            if result_image.mode != 'RGB':
                result_image = result_image.convert('RGB')
            # Save with optimized settings
            result_image.save(img_byte_arr, format='PNG', compress_level=3)
            logger.info("Saved PIL Image to byte stream")
        else:
            try:
                # Convert numpy array or tensor to PIL image
                pil_result = None

                if hasattr(result_image, 'numpy') and callable(getattr(result_image, 'numpy')):
                    # Handle PyTorch tensor
                    result_array = result_image.numpy()
                    if result_array.ndim == 3 and result_array.shape[0] == 3:
                        # Channel-first format (C, H, W)
                        pil_result = Image.fromarray((result_array.transpose(1, 2, 0) * 255).astype(np.uint8))
                    else:
                        # Other tensor formats
                        pil_result = Image.fromarray((result_array * 255).astype(np.uint8))
                elif isinstance(result_image, np.ndarray):
                    # Handle numpy array
                    if result_image.ndim == 3:
                        if result_image.shape[0] == 3:
                            # If it's a 3-channel image with channels first (C, H, W)
                            pil_result = Image.fromarray((result_image.transpose(1, 2, 0) * 255).astype(np.uint8))
                        else:
                            # Assume channel-last format (H, W, C)
                            pil_result = Image.fromarray((result_image * 255).astype(np.uint8))
                    else:
                        # For grayscale
                        pil_result = Image.fromarray((result_image * 255).astype(np.uint8))

                if pil_result is None:
                    raise ValueError(f"Unable to convert result_image of type {type(result_image)} to PIL Image")

                # Ensure the image is in RGB mode
                if pil_result.mode != 'RGB':
                    pil_result = pil_result.convert('RGB')

                pil_result.save(img_byte_arr, format='PNG', compress_level=3)
                logger.info("Converted and saved tensor/array to byte stream")
            except Exception as conv_error:
                logger.error(f"Error converting result to PIL image: {conv_error}")
                logger.error(traceback.format_exc())

                # Create a simple error image as fallback
                error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
                draw = ImageDraw.Draw(error_img)
                draw.text((20, 150), f"Error creating mask: {str(conv_error)[:50]}...", fill=(0, 0, 0))
                error_img.save(img_byte_arr, format='PNG')

        img_byte_arr.seek(0)
        logger.info("Successfully rendered preview image, returning as PNG")

        # Use PNG format for better quality and transparency support
        return StreamingResponse(img_byte_arr, media_type='image/png')

    except Exception as e:
        logger.error(f'Failed to generate mask preview for {image_path}: {e}')
        import traceback
        logger.error(traceback.format_exc())

        # Return a placeholder error image
        try:
            error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error: {str(e)[:50]}...", fill=(0, 0, 0))
            img_byte_arr = io.BytesIO()
            error_img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            return StreamingResponse(img_byte_arr, media_type='image/png')
        except:
            raise HTTPException(status_code=500, detail=f'Could not generate mask preview: {str(e)}')

@router.get('/debug-render-test')
def debug_render_test(
    image_path: str = Query(...),
):
    '''
    Debug endpoint to test mask rendering with a simple red shape.

    Args:
        image_path: path to the base image

    Returns:
        A streaming JPEG image response with a simple red rectangle overlay
    '''
    try:
        import numpy as np
        from PIL import Image, ImageDraw
        from root_utils import open_image

        logger.info(f"Running debug render test for {image_path}")

        # Open the base image
        try:
            base_image = open_image(image_path)
            width, height = base_image.size
            logger.info(f"Successfully opened base image with dimensions {width}x{height}")
        except Exception as e:
            logger.error(f"Failed to open base image {image_path}: {e}")
            # Return a placeholder error image
            error_img = Image.new('RGB', (400, 300), color=(255, 200, 200))
            img_byte_arr = io.BytesIO()
            error_img.save(img_byte_arr, format='JPEG')
            img_byte_arr.seek(0)
            return StreamingResponse(img_byte_arr, media_type='image/jpeg')

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

        # Add timestamp to image (to avoid caching)
        draw = ImageDraw.Draw(result_image)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((10, 10), f"Debug test: {timestamp}", fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=2)

        # Convert to byte stream
        img_byte_arr = io.BytesIO()
        result_image.save(img_byte_arr, format='JPEG', quality=100)
        img_byte_arr.seek(0)

        logger.info("Successfully rendered debug test image")
        return StreamingResponse(img_byte_arr, media_type='image/jpeg')

    except Exception as e:
        logger.error(f'Failed to generate debug test image for {image_path}: {e}')
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f'Debug test failed: {str(e)}')

@router.get('/render-mask-base64')
def render_mask_base64(
    image_path: str = Query(...),
    parts: str = Query(...)
):
    '''
    Dynamically generates a mask image for the selected parts and returns it as base64.

    Args:
        image_path: path to the base image
        parts: comma-separated list of part names

    Returns:
        JSON with base64-encoded image
    '''
    try:
        part_list = parts.split(',')
        logging.info(f'Rendering base64 mask for {image_path} with parts {part_list}')
        mask_image: PILImage = get_combined_mask_image(image_path, part_list)

        # Convert to base64
        base64_image = image_to_base64(mask_image)

        return {
            "success": True,
            "base64_image": f"data:image/png;base64,{base64_image}"
        }

    except Exception as e:
        logging.error(f'Failed to generate base64 mask for {image_path} parts {parts}: {e}')
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Could not generate mask: {str(e)}"}
        )

@router.post('/render-preview-base64')
async def render_preview_base64(request_data: dict):
    '''
    Dynamically renders a mask preview from RLE data and returns it as base64.

    Args:
        request_data: A dictionary containing:
            - image_path: path to the base image
            - rle_data: RLE data for the mask
            - overlay: Whether to overlay the mask on the original image (default: True)

    Returns:
        JSON with base64-encoded mask image
    '''
    try:
        from pycocotools import mask as mask_utils
        import numpy as np
        from PIL import Image, ImageDraw
        from root_utils import open_image
        import json
        import traceback

        image_path = request_data.get("image_path")
        rle_data = request_data.get("rle_data")
        overlay = request_data.get("overlay", True)

        if not image_path:
            logger.error("No image_path provided in render_preview_base64")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No image_path provided"}
            )

        # Log the incoming data for debugging
        logger.info(f"Rendering base64 preview mask for {image_path}, overlay={overlay}")

        if not rle_data:
            logger.warning("No RLE data provided for base64 preview")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No RLE data provided"}
            )

        # Debug the RLE data format
        logger.info(f"RLE data type: {type(rle_data)}")

        # Handle string or dict RLE data
        if isinstance(rle_data, str):
            # Try to parse if it's a JSON string
            try:
                logger.info(f"Parsing RLE string: {rle_data[:50]}...")
                rle_dict = json.loads(rle_data)
                logger.info(f"Successfully parsed RLE JSON string into dict with keys: {list(rle_dict.keys())}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse RLE string as JSON: {e}")
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Invalid RLE data format: {str(e)}"}
                )
        else:
            rle_dict = rle_data
            if isinstance(rle_dict, dict):
                logger.info(f"Using RLE dict with keys: {list(rle_dict.keys())}")
            else:
                logger.error(f"RLE data is not a dict: {type(rle_dict)}")
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "RLE data must be a dictionary or JSON string"}
                )

        # Open the base image
        try:
            base_image = open_image(image_path)
            width, height = base_image.size
            logger.info(f"Successfully opened base image with dimensions {width}x{height}")
        except Exception as e:
            logger.error(f"Failed to open base image {image_path}: {e}")
            # Return error image as base64
            error_img = Image.new('RGB', (400, 300), color=(255, 200, 200))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error loading image: {str(e)[:50]}...", fill=(0, 0, 0))
            base64_img = image_to_base64(error_img)
            return {
                "success": False,
                "error": f"Failed to open image: {str(e)}",
                "base64_image": f"data:image/png;base64,{base64_img}"
            }

        # Create empty mask as default
        mask = np.zeros((height, width), dtype=np.uint8)

        # Process RLE data
        try:
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
            if size[0] != height or size[1] != width:
                logger.warning(f"RLE size {size} doesn't match image {height}x{width}. Adjusting.")
                rle_copy['size'] = [height, width]

            # Decode the RLE
            logger.info(f"Decoding RLE with size: {rle_copy['size']}")
            try:
                mask = mask_utils.decode(rle_copy)
                mask_sum = np.sum(mask)
                logger.info(f"Successfully decoded RLE to mask with shape {mask.shape}, sum: {mask_sum}")
            except Exception as e:
                logger.error(f"Failed to decode RLE: {e}")
                logger.error(traceback.format_exc())
                raise ValueError(f"Failed to decode RLE: {e}")
        except Exception as e:
            logger.error(f"Failed to process RLE data: {e}")
            logger.error(traceback.format_exc())

            # Return error image instead of continuing with empty mask
            error_img = Image.new('RGB', (400, 300), color=(255, 200, 200))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"RLE processing error: {str(e)[:50]}...", fill=(0, 0, 0))
            base64_img = image_to_base64(error_img)
            return {
                "success": False,
                "error": f"Failed to process RLE data: {str(e)}",
                "base64_image": f"data:image/png;base64,{base64_img}"
            }

        # Stack the mask to create the format expected by image_from_masks
        mask_stack = np.expand_dims(mask, axis=0)

        # Use image_from_masks to generate the mask image
        try:
            from render_mask import image_from_masks

            if overlay:
                # Overlay on the original image with transparency
                logger.info("Creating overlay with image_from_masks")
                result_image = image_from_masks(
                    masks=mask_stack,
                    combine_as_binary_mask=True,
                    combine_color='red',
                    superimpose_on_image=base_image,
                    superimpose_alpha=0.7
                )
                logger.info("Successfully created overlay image")
            else:
                # Just return the mask with a visible color
                logger.info("Creating mask-only image with image_from_masks")
                result_image = image_from_masks(
                    masks=mask_stack,
                    combine_as_binary_mask=True,
                    combine_color='red'
                )
                logger.info("Successfully created mask-only image")

            # Convert result to PIL Image if needed
            if not isinstance(result_image, Image.Image):
                logger.info(f"Converting result of type {type(result_image)} to PIL Image")
                if hasattr(result_image, 'numpy') and callable(getattr(result_image, 'numpy')):
                    # Handle PyTorch tensor
                    result_image = Image.fromarray(
                        (result_image.numpy() * 255).astype(np.uint8).transpose(1, 2, 0)
                    )
                elif isinstance(result_image, np.ndarray):
                    # Handle numpy array
                    if result_image.ndim == 3:
                        if result_image.shape[0] == 3:
                            # Channel-first format (C, H, W)
                            result_image = Image.fromarray(
                                (result_image.transpose(1, 2, 0) * 255).astype(np.uint8)
                            )
                        else:
                            # Assume channel-last format (H, W, C)
                            result_image = Image.fromarray(
                                (result_image * 255).astype(np.uint8)
                            )
                    else:
                        # Grayscale
                        result_image = Image.fromarray(
                            (result_image * 255).astype(np.uint8)
                        )

            # Ensure result_image is RGB mode for consistent output
            if result_image.mode != 'RGB':
                logger.info(f"Converting image from mode {result_image.mode} to RGB")
                result_image = result_image.convert('RGB')

            # Convert to base64 with explicit format and compression parameters
            logger.info("Converting result image to base64")
            img_byte_arr = io.BytesIO()
            result_image.save(img_byte_arr, format='PNG', compress_level=3)
            img_byte_arr.seek(0)
            base64_img = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            logger.info(f"Generated base64 image of length {len(base64_img)}")

            return {
                "success": True,
                "base64_image": f"data:image/png;base64,{base64_img}"
            }

        except Exception as e:
            logger.error(f"Error generating mask image: {e}")
            logger.error(traceback.format_exc())

            # Return error image
            error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error: {str(e)[:50]}...", fill=(0, 0, 0))
            base64_img = image_to_base64(error_img)

            return {
                "success": False,
                "error": f"Error generating mask image: {str(e)}",
                "base64_image": f"data:image/png;base64,{base64_img}"
            }

    except Exception as e:
        logger.error(f"Unexpected error in render_preview_base64: {e}")
        logger.error(traceback.format_exc())

        # Last resort error handling
        try:
            error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Unexpected error: {str(e)[:50]}...", fill=(0, 0, 0))
            base64_img = image_to_base64(error_img)

            return {
                "success": False,
                "error": str(e),
                "base64_image": f"data:image/png;base64,{base64_img}"
            }
        except:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to generate preview: {str(e)}"}
            )