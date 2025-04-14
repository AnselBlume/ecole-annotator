import orjson
import os
import sys
import json
import numpy as np
from PIL import Image
from pycocotools.mask import decode
from typing import Dict

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '../backend')))
from root_utils import open_image
from render_mask import image_from_masks  # Adjust import if needed
from dataset.utils import get_part_suffix

INPUT_JSON = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
OUTPUT_DIR = 'output_visualizations'

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

def visualize_checked_parts(annotations: Dict, output_base: str):
    for image_path, data in annotations['checked'].items():
        image_id = os.path.splitext(os.path.basename(image_path))[0]
        image = open_image(image_path)

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

            # Save
            part_dir = os.path.join(output_base, image_id)
            ensure_dir(part_dir)
            part_suffix = get_part_suffix(part_name)
            output_path = os.path.join(part_dir, f"{part_suffix}.jpg")
            visual.save(output_path)
            print(f"Saved: {output_path}")

if __name__ == '__main__':
    with open(INPUT_JSON, 'r') as f:
        annotations = orjson.loads(f.read())

    ensure_dir(OUTPUT_DIR)
    visualize_checked_parts(annotations, OUTPUT_DIR)