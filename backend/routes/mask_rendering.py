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
    """Convert PIL Image to base64 string"""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=format)
    img_byte_arr.seek(0)
    img_bytes = img_byte_arr.getvalue()
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
        A streaming JPEG image response
    '''
    try:
        from pycocotools import mask as mask_utils
        import numpy as np
        from PIL import Image
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
            draw = Image.ImageDraw.Draw(error_img)
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

                # Ensure we have a proper dictionary with the right keys
                if isinstance(rle_dict, dict) and 'counts' in rle_dict and 'size' in rle_dict:
                    # Make a copy of the dict to avoid modifying the original
                    rle_copy = dict(rle_dict)
                    counts = rle_copy['counts']

                    # Convert string counts to bytes if needed
                    if isinstance(counts, str):
                        rle_copy['counts'] = counts.encode('utf-8')
                        logger.info("Converted RLE counts from string to bytes")

                    # Ensure size matches the image dimensions
                    if not rle_copy['size'] or rle_copy['size'][0] != height or rle_copy['size'][1] != width:
                        logger.warning(f"Adjusting RLE size to match image: {height}x{width}")
                        rle_copy['size'] = [height, width]

                    # Decode the RLE
                    try:
                        mask = mask_utils.decode(rle_copy)
                        mask_sum = np.sum(mask)
                        logger.info(f"Successfully decoded RLE to mask with shape {mask.shape}, sum: {mask_sum}")

                        if mask_sum == 0:
                            logger.warning("Decoded mask is empty (all zeros), adding test rectangle")
                            # Add a test rectangle for visualization
                            h, w = mask.shape
                            center_h, center_w = h // 2, w // 2
                            test_size = min(50, h//4, w//4)
                            mask[center_h-test_size//2:center_h+test_size//2, center_w-test_size//2:center_w+test_size//2] = 1
                    except Exception as e:
                        logger.error(f"Failed to decode RLE: {e}")
                        logger.error(traceback.format_exc())
                else:
                    logger.warning(f"Invalid RLE format or missing required keys")
            except Exception as e:
                logger.error(f"Failed to parse RLE data: {e}")
                logger.error(traceback.format_exc())

        # Stack the mask to create the format expected by image_from_masks
        # Convert binary mask to a stacked format (1, height, width)
        mask_stack = np.expand_dims(mask, axis=0)

        # Check if mask has any content
        if np.sum(mask) == 0:
            logger.warning("Mask contains no positive pixels, setting a test pixel for debugging")
            # For debugging, set a small rectangle in the center
            h, w = mask.shape
            center_h, center_w = h // 2, w // 2
            size = 50  # Size of test rectangle
            mask[center_h-size//2:center_h+size//2, center_w-size//2:center_w+size//2] = 1
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
            error_img = Image.new('RGB', (width, height), color=(255, 220, 220))
            draw = Image.ImageDraw.Draw(error_img)
            draw.text((width//2-100, height//2), f"Error: {str(e)[:100]}", fill=(0, 0, 0))
            result_image = error_img

        # Convert to byte stream
        img_byte_arr = io.BytesIO()

        # If result_image is a PIL Image, save directly
        if isinstance(result_image, Image.Image):
            result_image.save(img_byte_arr, format='PNG', quality=100)
            logger.info("Saved PIL Image to byte stream")
        # If result_image is a PyTorch tensor or numpy array, convert to PIL first
        else:
            try:
                from PIL import Image
                from torchvision.transforms.functional import to_pil_image
                import torch

                if isinstance(result_image, torch.Tensor):
                    logger.info(f"Converting torch tensor to PIL image, tensor shape: {result_image.shape}")
                    pil_result = to_pil_image(result_image)
                else:  # numpy array
                    logger.info(f"Converting numpy array to PIL image, array shape: {result_image.shape}")
                    if result_image.ndim == 3 and result_image.shape[0] == 3:
                        # If it's a 3-channel image with channels first (C, H, W)
                        pil_result = Image.fromarray(result_image.transpose(1, 2, 0))
                    elif result_image.ndim == 3:
                        # If it's a 3-channel image with channels last (H, W, C)
                        pil_result = Image.fromarray(result_image)
                    else:
                        # For grayscale or binary images
                        pil_result = Image.fromarray(result_image)

                pil_result.save(img_byte_arr, format='PNG', quality=100)
                logger.info("Converted and saved tensor/array to byte stream")
            except Exception as conv_error:
                logger.error(f"Error converting result to PIL image: {conv_error}")
                logger.error(traceback.format_exc())

                # Create a simple error image as fallback
                error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
                draw = Image.ImageDraw.Draw(error_img)
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
            draw = Image.ImageDraw.Draw(error_img)
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
        logger.info(f"RLE data keys: {list(rle_data.keys()) if isinstance(rle_data, dict) else 'not a dict'}")
        logger.info(f"RLE data content: {rle_data}")

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
            logger.info(f"Using RLE data as-is: {list(rle_dict.keys()) if isinstance(rle_dict, dict) else 'not a dict'}")

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
            # Ensure we have a proper dictionary
            if not isinstance(rle_dict, dict):
                logger.error(f"RLE data is not a dictionary: {type(rle_dict)}")
                raise ValueError("RLE data must be a dictionary")

            if 'counts' not in rle_dict:
                logger.error(f"RLE data missing 'counts' field. Available keys: {list(rle_dict.keys())}")
                raise ValueError("RLE data must contain 'counts' field")

            # Make a copy of the dict to avoid modifying the original
            rle_copy = dict(rle_dict)

            # Debug the counts
            counts = rle_copy['counts']
            if isinstance(counts, str):
                logger.info(f"RLE counts is a string: {counts[:30]}...")
                rle_copy['counts'] = counts.encode('utf-8')
                logger.info("Converted RLE counts from string to bytes")
            elif isinstance(counts, bytes):
                logger.info(f"RLE counts is already bytes, length: {len(counts)}")
            else:
                logger.warning(f"RLE counts is neither string nor bytes: {type(counts)}")

            # Ensure size matches the image dimensions
            if 'size' not in rle_copy or not rle_copy['size']:
                rle_copy['size'] = [height, width]
                logger.info(f"Setting RLE size to image dimensions: {height}x{width}")
            elif rle_copy['size'][0] != height or rle_copy['size'][1] != width:
                logger.warning(f"RLE size {rle_copy['size']} doesn't match image {height}x{width}. Adjusting.")
                rle_copy['size'] = [height, width]

            # Decode the RLE
            logger.info(f"Decoding RLE with size: {rle_copy['size']}")
            try:
                mask = mask_utils.decode(rle_copy)
                mask_sum = np.sum(mask)
                logger.info(f"Successfully decoded RLE to mask with shape {mask.shape}, sum: {mask_sum}")

                if mask_sum == 0:
                    logger.warning("Decoded mask is empty (all zeros)")
                    # For better visibility, add a small test rectangle
                    h, w = mask.shape
                    center_h, center_w = h // 2, w // 2
                    test_size = 50
                    mask[center_h-test_size//2:center_h+test_size//2, center_w-test_size//2:center_w+test_size//2] = 1
                    logger.info("Added test rectangle to empty mask")
            except Exception as e:
                logger.error(f"Failed to decode RLE: {e}")
                logger.error(traceback.format_exc())
                # Still continue with an empty mask
        except Exception as e:
            logger.error(f"Failed to process RLE data: {e}")
            logger.error(traceback.format_exc())
            # Continue with the empty mask

        # Stack the mask to create the format expected by image_from_masks
        mask_stack = np.expand_dims(mask, axis=0)

        # Check if mask has any content
        if np.sum(mask) == 0:
            logger.warning("Final mask contains no positive pixels")

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
                logger.info("Successfully created mask-only image")

            logger.info(f"Result image type: {type(result_image)}")
            if hasattr(result_image, 'shape'):
                logger.info(f"Result image shape: {result_image.shape}")
            elif hasattr(result_image, 'size'):
                logger.info(f"Result image size: {result_image.size}")
        except Exception as e:
            logger.error(f"Error in image_from_masks: {e}")
            logger.error(traceback.format_exc())
            # Create a fallback image
            error_img = Image.new('RGB', (width, height), color=(255, 200, 200))
            draw = ImageDraw.Draw(error_img)
            draw.text((width//2-100, height//2), f"Error rendering mask: {str(e)[:50]}...", fill=(0, 0, 0))
            result_image = error_img

        # Convert result to PIL Image if needed
        try:
            if not isinstance(result_image, Image.Image):
                from torchvision.transforms.functional import to_pil_image
                import torch

                if isinstance(result_image, torch.Tensor):
                    logger.info(f"Converting torch tensor to PIL image")
                    result_image = to_pil_image(result_image)
                else:  # numpy array
                    logger.info(f"Converting numpy array to PIL image")
                    if result_image.ndim == 3 and result_image.shape[0] == 3:
                        # Channel-first format (C, H, W)
                        result_image = Image.fromarray(result_image.transpose(1, 2, 0))
                    else:
                        result_image = Image.fromarray(result_image)
        except Exception as e:
            logger.error(f"Error converting result to PIL image: {e}")
            logger.error(traceback.format_exc())
            # Create a fallback image
            error_img = Image.new('RGB', (width, height), color=(255, 200, 200))
            draw = ImageDraw.Draw(error_img)
            draw.text((width//2-100, height//2), f"Error converting image: {str(e)[:50]}...", fill=(0, 0, 0))
            result_image = error_img

        # Convert to base64
        try:
            base64_img = image_to_base64(result_image)
            logger.info("Successfully created base64 preview image")

            return {
                "success": True,
                "base64_image": f"data:image/png;base64,{base64_img}"
            }
        except Exception as e:
            logger.error(f"Error converting image to base64: {e}")
            logger.error(traceback.format_exc())

            # Last resort error handling
            try:
                error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
                draw = ImageDraw.Draw(error_img)
                draw.text((20, 150), f"Error creating base64: {str(e)[:50]}...", fill=(0, 0, 0))
                base64_img = image_to_base64(error_img)

                return {
                    "success": False,
                    "error": str(e),
                    "base64_image": f"data:image/png;base64,{base64_img}"
                }
            except:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": f"Could not generate preview: {str(e)}"}
                )

    except Exception as e:
        logger.error(f'Failed to generate base64 preview for {request_data.get("image_path")}: {e}')
        logger.error(traceback.format_exc())

        # Return error image
        try:
            error_img = Image.new('RGB', (400, 300), color=(255, 180, 180))
            draw = ImageDraw.Draw(error_img)
            draw.text((20, 150), f"Error: {str(e)[:50]}...", fill=(0, 0, 0))
            base64_img = image_to_base64(error_img)

            return {
                "success": False,
                "error": str(e),
                "base64_image": f"data:image/png;base64,{base64_img}"
            }
        except:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Could not generate preview: {str(e)}"}
            )