from fastapi import HTTPException, APIRouter, Query, Response
import logging
import traceback
from datetime import datetime

from render_mask import get_combined_mask_image
from utils.image_utils import (
    load_image_from_path,
    create_debug_overlay,
    image_to_base64
)
from utils.mask_utils import (
    process_rle_data,
    decode_rle_to_mask,
    create_empty_mask,
    create_mask_image,
    create_mask_from_polygon,
    encode_mask_to_rle
)
from utils.api_utils import (
    error_image_response,
    handle_request_error,
    image_response,
    error_response,
    success_response
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get('/render-mask')
def render_combined_mask(
    image_path: str = Query(...),
    parts: str = Query(...),
    mask_color: str = Query('aqua')
):
    '''
    Dynamically generates a mask image for the selected parts and returns it.

    Args:
        image_path: path to the base image
        parts: comma-separated list of part names
        mask_color: Color to use for the mask (default: aqua)

    Returns:
        A streaming JPEG image response
    '''
    try:
        part_list = parts.split(',')
        logging.info(f'Rendering mask for {image_path} with parts {part_list}, color: {mask_color}')
        mask_image = get_combined_mask_image(image_path, part_list, mask_color)

        return image_response(mask_image)

    except Exception as e:
        logging.error(f'Failed to generate mask for {image_path} parts {parts}: {e}')
        return error_image_response(f'Could not generate mask: {str(e)}')

@router.get('/render-preview')
def render_mask_preview(
    image_path: str = Query(...),
    rle_data: str = Query(None),
    overlay: bool = Query(False),
    mask_color: str = Query('aqua')
):
    '''
    Dynamically renders a mask preview from RLE data.
    This is used for real-time visualization during annotation.

    Args:
        image_path: path to the base image
        rle_data: RLE data for the mask (JSON string)
        overlay: Whether to overlay the mask on the original image
        mask_color: Color to use for the mask (default: aqua)

    Returns:
        A streaming JPEG image response
    '''
    try:
        # Log the incoming data for debugging
        logger.info(f"Rendering preview mask for {image_path}, overlay={overlay}, color={mask_color}")
        if not rle_data:
            logger.info("No RLE data provided")
            return Response(
                content={"error": "No RLE data provided"},
                media_type="application/json",
                status_code=400
            )

        # Log RLE data preview (truncated)
        rle_preview = rle_data[:100] + "..." if len(rle_data) > 100 else rle_data
        logger.info(f"RLE data preview: {rle_preview}")

        # Load the base image
        try:
            base_image, width, height = load_image_from_path(image_path)
        except ValueError as e:
            return error_image_response(str(e))

        # Create empty mask as default
        mask = create_empty_mask(width, height)

        # Process RLE data if provided
        if rle_data:
            try:
                # Process RLE data
                rle_dict = process_rle_data(rle_data, width, height)

                # Decode the RLE
                mask = decode_rle_to_mask(rle_dict)
            except ValueError as e:
                return error_image_response(f"RLE error: {str(e)}")

        # Create mask image
        try:
            result_image = create_mask_image(mask, base_image, overlay, color=mask_color)
        except ValueError as e:
            return error_image_response(f"Error creating mask: {str(e)}")

        # Return the image
        return image_response(result_image, format='JPEG')

    except Exception as e:
        logger.error(f'Failed to generate mask preview for {image_path}: {e}')
        logger.error(traceback.format_exc())
        return error_image_response(str(e))

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
        logger.info(f"Running debug render test for {image_path}")

        # Load the base image
        try:
            base_image, width, height = load_image_from_path(image_path)
        except ValueError as e:
            return error_image_response(str(e), format='JPEG')

        # Create a debug overlay with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_image = create_debug_overlay(base_image, f"Debug test: {timestamp}")

        return image_response(result_image, format='JPEG')

    except Exception as e:
        logger.error(f'Failed to generate debug test image for {image_path}: {e}')
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f'Debug test failed: {str(e)}')

@router.post('/render-preview-base64')
async def render_preview_base64(request_data: dict):
    '''
    Dynamically renders a mask preview from RLE data and returns it as base64.

    Args:
        request_data: A dictionary containing:
            - image_path: path to the base image
            - rle_data: RLE data for the mask
            - overlay: Whether to overlay the mask on the original image (default: True)
            - mask_color: Color to use for the mask (default: aqua)

    Returns:
        JSON with base64-encoded mask image
    '''
    try:
        image_path = request_data.get("image_path")
        rle_data = request_data.get("rle_data")
        overlay = request_data.get("overlay", True)
        mask_color = request_data.get("mask_color", "aqua")

        if not image_path:
            logger.error("No image_path provided in render_preview_base64")
            return error_response("No image_path provided")

        # Log the incoming request data
        logger.info(f"Rendering base64 preview mask for {image_path}, overlay={overlay}, color={mask_color}")
        logger.info(f"RLE data type: {type(rle_data)}")

        if not rle_data:
            logger.warning("No RLE data provided for base64 preview")
            return error_response("No RLE data provided")

        # Load the base image
        try:
            base_image, width, height = load_image_from_path(image_path)
        except ValueError as e:
            return handle_request_error(e, "Failed to open image")

        # Process RLE data and generate mask
        try:
            # Process RLE data
            rle_dict = process_rle_data(rle_data, width, height)

            # Decode to mask
            mask = decode_rle_to_mask(rle_dict)

            # Create mask image
            result_image = create_mask_image(mask, base_image, overlay, color=mask_color)

            # Return base64 image response
            return {
                "success": True,
                "base64_image": f"data:image/jpeg;base64,{image_to_base64(result_image)}"
            }
        except ValueError as e:
            return handle_request_error(e, "Failed to process RLE data")

    except Exception as e:
        return handle_request_error(e, "Unexpected error in render_preview_base64")

@router.post('/generate-from-polygon')
async def generate_mask_from_polygon(request_data: dict):
    # XXX This does not used anywhere since ModularAnnotationMode calls generate-polygon-mask to get an RLE
    '''
    Generates a mask from a polygon and returns RLE data.

    Args:
        request_data: A dictionary containing:
            - image_path: path to the base image
            - points: List of [x, y] coordinates forming the polygon
            - mask_color: Color of the mask (default: "aqua")

    Returns:
        JSON with success status and RLE data for the mask
    '''
    try:
        image_path = request_data.get("image_path")
        points = request_data.get("points", [])
        mask_color = request_data.get("mask_color", "aqua")

        if not image_path:
            logger.error("No image_path provided in generate_mask_from_polygon")
            return error_response("No image_path provided")

        if not points or len(points) < 3:
            logger.error(f"Not enough points provided in generate_mask_from_polygon: {len(points) if points else 0}")
            return error_response("At least 3 points required to form a polygon")

        logger.info(f"Generating mask from polygon with {len(points)} points for {image_path}, color: {mask_color}")

        # Load the base image to get dimensions
        try:
            _, width, height = load_image_from_path(image_path)
        except ValueError as e:
            return error_response(f"Failed to open image: {str(e)}", status_code=500)

        # Create a binary mask from the polygon
        mask = create_mask_from_polygon(points, width, height)

        # Encode as RLE
        rle_for_json = encode_mask_to_rle(mask)

        return success_response({"rle": rle_for_json})

    except Exception as e:
        logger.error(f"Error generating mask from polygon: {e}")
        logger.error(traceback.format_exc())
        return error_response(f"Failed to generate mask: {str(e)}", status_code=500)

@router.get('/debug-image-load')
def debug_image_load_endpoint(
    image_path: str = Query(...),
):
    '''
    Debug endpoint to test image loading and return information about the image.

    Args:
        image_path: path to the image

    Returns:
        JSON with image information or error details
    '''
    try:
        # Run the debug function
        result = debug_image_load(image_path)

        # Return detailed information
        return {
            "success": True,
            "image_path": image_path,
            "file_info": result["file_info"],
            "image_info": result.get("image_info", {"success": False, "error": "Image loading not attempted"})
        }
    except Exception as e:
        logger.error(f"Failed to debug image {image_path}: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "image_path": image_path
        }