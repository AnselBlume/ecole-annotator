import numpy as np
import torch
from torch import Tensor
from PIL.Image import Image as PILImage
import logging
import torchvision.transforms.functional as TF
from torchvision.transforms.functional import InterpolationMode
from pycocotools import mask as mask_utils
from root_utils import open_image

logger = logging.getLogger(__name__)

DEFAULT_MAX_DIMENSION = 2048
DEFAULT_INTERPOLATION_MODE = InterpolationMode.BICUBIC

def needs_resize(image_path: str, max_dimension: int = DEFAULT_MAX_DIMENSION) -> tuple[bool, PILImage]:
    '''
    Check if an image needs to be resized based on its dimensions

    Args:
        image_path: path to the image
        max_dimension: maximum dimension of the image
    '''
    try:
        # Load the image
        image = open_image(image_path)
        width, height = image.size
        return width > max_dimension or height > max_dimension, image
    except Exception as e:
        logger.error(f"Error checking image size for {image_path}: {e}")
        return False, None

def resize_image(image: PILImage, max_dimension: int = DEFAULT_MAX_DIMENSION) -> PILImage:
    '''
    Resize an image if it exceeds the maximum dimension

    Args:
        image: PIL image
        max_dimension: maximum dimension of the image
    '''
    return _resize(image, max_dimension)

def resize_rle(rle: dict, max_dimension: int = DEFAULT_MAX_DIMENSION) -> dict:
    mask = mask_utils.decode(rle)
    logger.info(f"Resizing mask of size {mask.shape}")

    mask_tensor = torch.from_numpy(mask[None, :, :])  # Add batch/channel dim
    resized_tensor = _resize(mask_tensor, max_dimension, interpolation=InterpolationMode.NEAREST)
    resized_mask = resized_tensor.round().bool().numpy()[0]  # Remove channel dim

    mask = np.asfortranarray(resized_mask.astype(np.uint8))  # Ensure proper format
    encoded_rle = mask_utils.encode(mask)

    if isinstance(encoded_rle['counts'], bytes):
        encoded_rle['counts'] = encoded_rle['counts'].decode('utf-8')

    logger.info(f"Resized mask of size {encoded_rle['size']}")
    return encoded_rle

def _resize(
    image: PILImage | Tensor,
    max_dimension: int,
    interpolation: InterpolationMode = DEFAULT_INTERPOLATION_MODE
) -> PILImage | Tensor:

    '''
    Resizes by the longer edge
    '''
    if isinstance(image, PILImage):
        w, h = image.size
    else:
        h, w = image.shape[-2:]

    if w > h:
        new_w = max_dimension
        new_h = int(h * max_dimension / w)
    else:
        new_h = max_dimension
        new_w = int(w * max_dimension / h)

    return TF.resize(image, (new_h, new_w), interpolation=interpolation)