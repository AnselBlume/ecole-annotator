from fastapi import HTTPException, APIRouter, Query
from fastapi.responses import StreamingResponse
from PIL.Image import Image as PILImage
import io
import logging
from render_mask import get_combined_mask_image

router = APIRouter()

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
        A streaming PNG image response
    '''
    try:
        part_list = parts.split(',')
        mask_image: PILImage = get_combined_mask_image(image_path, part_list)

        # Convert to byte stream
        img_byte_arr = io.BytesIO()
        mask_image.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)

        return StreamingResponse(img_byte_arr, media_type='image/jpeg')

    except Exception as e:
        logging.error(f'Failed to generate mask for {image_path} parts {parts}: {e}')
        raise HTTPException(status_code=500, detail='Could not generate mask')