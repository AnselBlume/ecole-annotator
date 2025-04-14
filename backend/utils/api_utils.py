import logging
import traceback
from typing import Dict, Any
from fastapi.responses import StreamingResponse, JSONResponse
from PIL import Image

from utils.image_utils import create_error_image, pil_image_to_byte_stream, image_to_base64

logger = logging.getLogger(__name__)

def error_image_response(message: str, format='JPEG') -> StreamingResponse:
    """Create a streaming response with an error image"""
    error_img = create_error_image(message)
    img_byte_arr = pil_image_to_byte_stream(error_img, format)
    return StreamingResponse(img_byte_arr, media_type=f'image/{format.lower()}')

def handle_request_error(e: Exception, error_message: str) -> Dict:
    """Common error handler for API requests"""
    logger.error(f"{error_message}: {e}")
    logger.error(traceback.format_exc())

    # Create error image and convert to base64
    error_img = create_error_image(str(e))
    base64_img = image_to_base64(error_img)

    return {
        "success": False,
        "error": f"{error_message}: {str(e)}",
        "base64_image": f"data:image/jpeg;base64,{base64_img}"
    }

def success_response(data: Dict[str, Any] = None) -> Dict:
    """Create a standard success response"""
    response = {"success": True}
    if data:
        response.update(data)
    return response

def error_response(message: str, status_code: int = 400) -> JSONResponse:
    """Create a standard error response"""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": message
        }
    )

def image_response(image: Image.Image, format: str = 'JPEG') -> StreamingResponse:
    """Create a streaming response with the given image"""
    img_byte_arr = pil_image_to_byte_stream(image, format)
    return StreamingResponse(img_byte_arr, media_type=f'image/{format.lower()}')

def base64_image_response(image: Image.Image, include_data_uri: bool = True) -> Dict:
    """Create a response with a base64-encoded image"""
    base64_img = image_to_base64(image)
    if include_data_uri:
        return {
            "success": True,
            "base64_image": f"data:image/jpeg;base64,{base64_img}"
        }
    return {
        "success": True,
        "base64_image": base64_img
    }

def validate_required_params(params: Dict[str, Any], required_fields: list) -> tuple:
    """Validate that required parameters are present

    Returns:
        tuple: (is_valid, error_message)
    """
    missing = [field for field in required_fields if field not in params or params[field] is None]
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"
    return True, ""