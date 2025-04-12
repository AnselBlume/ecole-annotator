from typing import List
from PIL.Image import Image as PILImage
from services.annotator import get_annotation_state, acquire_annotation_state_lock
from model import ImageAnnotation
from services.redis_client import release_lock, LockAcquisitionError
from fastapi import HTTPException
import logging
from pycocotools.mask import decode
import numpy as np
import torch
import matplotlib.pyplot as plt
from torchvision.transforms.functional import pil_to_tensor, to_pil_image
from torchvision.utils import draw_segmentation_masks
from root_utils import open_image

logger = logging.getLogger(__name__)

def get_combined_mask_image(image_path: str, part_names: List[str]) -> PILImage:
    '''
    Generate a combined mask image for the given parts of a specific image.

    Args:
        image_path: Path to the original image
        part_names: Parts to include in the mask

    Returns:
        PIL Image object of the combined mask
    '''
    # Example: fetch from Redis or JSON file
    try:
        annotation_state_lock = acquire_annotation_state_lock()
        if not annotation_state_lock:
            raise HTTPException(status_code=500, detail='Could not acquire annotation state lock')
        annotation_state = get_annotation_state()
    except LockAcquisitionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_lock(annotation_state_lock)

    # Find the matching annotation
    annotation: ImageAnnotation = annotation_state.unchecked.get(image_path) or annotation_state.checked.get(image_path)

    if not annotation:
        raise HTTPException(status_code=404, detail=f'Image annotation not found for {image_path}')

    part_masks = []
    for part_name, part_annotation in annotation.parts.items():
        masks = decode(part_annotation.rles) # (height, width, num_masks)
        logger.info(f'masks has shape {masks.shape}. Expected shape (height, width, num_masks)')
        combined_mask = np.any(masks, axis=2) # (height, width)
        part_masks.append(combined_mask)

    part_masks = np.stack(part_masks, axis=0) # (num_masks, height, width)
    image = open_image(image_path)

    return image_from_masks(part_masks, superimpose_on_image=image)

def get_colors(num_colors, cmap_name='rainbow', as_tuples=False):
    '''
    Returns a mapping from index to color (RGB).

    Args:
        num_colors (int): The number of colors to generate

    Returns:
        torch.Tensor: Mapping from index to color of shape (num_colors, 3).
    '''
    cmap = plt.get_cmap(cmap_name)

    colors = np.stack([
        (255 * np.array(cmap(i))).astype(int)[:3]
        for i in np.linspace(0, 1, num_colors)
    ])

    if as_tuples:
        colors = [tuple(c) for c in colors]

    return colors

def image_from_masks(
    masks: torch.Tensor | np.ndarray,
    combine_as_binary_mask: bool = False,
    combine_color = 'aqua',
    superimpose_on_image: torch.Tensor | PILImage = None,
    superimpose_alpha: float = .8,
    cmap: str = 'rainbow'
):
    '''
    Creates an image from a set of masks.

    Args:
        masks (torch.Tensor): (num_masks, height, width)
        combine_as_binary_mask (bool): Show all segmentations with the same color, showing where any mask is present. Defaults to False.
        superimpose_on_image (torch.Tensor): The image to use as the background, if provided: (C, height, width). Defaults to None.
        cmap (str, optional): Colormap name to use when coloring the masks. Defaults to 'rainbow'.

    Returns:
        torch.Tensor: Image of shape (C, height, width) with the plotted masks.
    '''
    is_numpy = isinstance(masks, np.ndarray)
    if is_numpy:
        masks = torch.from_numpy(masks)

    # Masks should be a tensor of shape (num_masks, height, width)
    if combine_as_binary_mask:
        masks = masks.sum(dim=0, keepdim=True).to(torch.bool)

    # If there is only one mask, ensure we get a visible color
    colors = get_colors(masks.shape[0], cmap_name=cmap, as_tuples=True) if masks.shape[0] > 1 else combine_color

    if superimpose_on_image is not None:
        if isinstance(superimpose_on_image, PILImage):
            superimpose_on_image = pil_to_tensor(superimpose_on_image)
            return_as_pil = True

        else:
            return_as_pil = False

        alpha = superimpose_alpha
        background = superimpose_on_image
    else:
        alpha = 1
        background = torch.zeros(3, masks.shape[1], masks.shape[2], dtype=torch.uint8)
        return_as_pil = False

    masks = draw_segmentation_masks(background, masks, colors=colors, alpha=alpha)

    # Output format
    if return_as_pil:
        masks = to_pil_image(masks)

    elif is_numpy:
        masks = masks.numpy()

    return masks