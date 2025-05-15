import orjson
import os
import sys
import numpy as np
from pycocotools.mask import decode
from typing import Dict
from tqdm import tqdm
import coloredlogs
import logging

coloredlogs.install(level='INFO')
logger = logging.getLogger(__name__)

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '../backend')))
from root_utils import open_image
from render_mask import image_from_masks  # Adjust import if needed
from dataset.utils import get_part_suffix, get_object_prefix

INPUT_JSON = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
OUTPUT_DIR = '/shared/nas2/blume5/sp25/annotator/data/output_visualizations'

def visualize_checked_parts(annotations: Dict, output_base: str):
    for image_path, data in tqdm(annotations['checked'].items()):
        image_id = os.path.splitext(os.path.basename(image_path))[0]
        image = open_image(image_path)

        # Create directory structure: output_base/object_type/image_id
        object_type = get_object_prefix(next(iter(data['parts'])))
        image_dir = os.path.join(output_base, object_type, image_id)
        os.makedirs(image_dir, exist_ok=True)

        for part_name, part_data in data['parts'].items():
            masks = []
            for rle_data in part_data['rles']:
                rle = {
                    'size': rle_data['size'],
                    'counts': rle_data['counts'].encode('utf-8')
                }
                mask = decode(rle)
                masks.append(mask)

            if not masks:
                continue

            masks_stack = np.stack(masks, axis=0)  # (num_masks, H, W)
            visual = image_from_masks(
                masks_stack,
                superimpose_on_image=image,
                superimpose_alpha=0.8
            )

            part_suffix = get_part_suffix(part_name).replace(os.path.sep, '_') # Replace slashes with underscores
            output_path = os.path.join(image_dir, f"{part_suffix}.jpg")
            visual.save(output_path)
            logger.debug(f"Saved: {output_path}")

if __name__ == '__main__':
    with open(INPUT_JSON, 'r') as f:
        annotations = orjson.loads(f.read())

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    visualize_checked_parts(annotations, OUTPUT_DIR)