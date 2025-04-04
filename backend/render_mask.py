from fastapi import FastAPI, Query, Response, APIRouter
from fastapi.responses import StreamingResponse
from typing import List
import os
import json
import io
from PIL import Image
from utils import open_image
import torch
import numpy as np
from torchvision.utils import draw_segmentation_masks
from pycocotools import mask as mask_utils
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

DATA_DIR = './data'

# Load metadata into memory at startup
with open(os.path.join(DATA_DIR, 'images.json')) as f:
    METADATA = json.load(f)
logger.info(f'Loaded {len(METADATA)} image entries into memory.')

# Utility to decode masks and build a mask tensor
def get_mask_tensor(image_size, masks_rle):
    height, width = image_size[1], image_size[0]
    all_masks = []
    for rle in masks_rle:
        binary = mask_utils.decode(rle)  # shape (H, W, 1) or (H, W)
        if len(binary.shape) == 3:
            binary = binary[:, :, 0]
        all_masks.append(torch.tensor(binary, dtype=torch.bool))

    if not all_masks:
        return torch.zeros((0, height, width), dtype=torch.bool)
    return torch.stack(all_masks)

@router.get('/render-mask')
def render_mask(image_path: str = Query(...), parts: str = Query(...)):
    # Find the image entry
    image_entry = next((item for item in METADATA if item['imagePath'] == image_path), None)
    if not image_entry:
        return Response(status_code=404, content='Image metadata not found')

    selected_labels = parts.split(',')
    selected_masks = []
    for part in image_entry['parts']:
        if part['label'] in selected_labels:
            selected_masks.extend(part['masks'])

    # Load base image
    image = open_image(image_path)
    image_tensor = torch.from_numpy(np.array(image)).permute(2, 0, 1)  # (C, H, W)

    # Decode masks
    mask_tensor = get_mask_tensor(image.size, selected_masks)
    if mask_tensor.shape[0] > 0:
        overlaid = draw_segmentation_masks(image_tensor, mask_tensor, alpha=0.8)
    else:
        overlaid = image_tensor

    # Convert back to image
    out_img = Image.fromarray(overlaid.permute(1, 2, 0).byte().numpy())
    buf = io.BytesIO()
    out_img.save(buf, format='JPEG')
    buf.seek(0)

    return StreamingResponse(buf, media_type='image/jpeg')
