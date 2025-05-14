import orjson
import os
import sys
import argparse
import numpy as np
from pycocotools.mask import decode
from typing import Dict, List
from tqdm import tqdm
import coloredlogs
import logging

coloredlogs.install(level='INFO')
logger = logging.getLogger(__name__)

sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '../backend')))
from root_utils import open_image
from render_mask import image_from_masks
from dataset.utils import get_part_suffix, get_object_prefix

INPUT_JSON = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
OUTPUT_DIR = '/shared/nas2/blume5/sp25/annotator/data/output_visualizations_by_part'

def visualize_parts_by_name(annotations: Dict, part_search: str, output_base: str):
    # Dictionary to store mapping of output visualizations to source images
    image_mapping = {}

    # Counter for unique image naming
    counter = 0

    for image_path, data in tqdm(annotations['checked'].items()):
        found_part = False

        # Create base output directory
        os.makedirs(output_base, exist_ok=True)

        for part_name, part_data in data['parts'].items():
            # Check if this part contains the search string
            part_suffix = get_part_suffix(part_name)
            if part_search.lower() not in part_suffix.lower():
                continue

            found_part = True
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

            # Load the image
            image = open_image(image_path)

            # Get object type for directory organization
            object_type = get_object_prefix(part_name)

            # Create directory structure: object_type/part_suffix/
            part_dir = os.path.join(output_base, object_type, part_suffix)
            os.makedirs(part_dir, exist_ok=True)

            # Create the visualization
            masks_stack = np.stack(masks, axis=0)  # (num_masks, H, W)
            visual = image_from_masks(
                masks_stack,
                superimpose_on_image=image,
                superimpose_alpha=0.8
            )

            # Create a unique filename for this visualization
            image_id = os.path.splitext(os.path.basename(image_path))[0]
            output_filename = f"{image_id}_{counter}.jpg"
            counter += 1

            output_path = os.path.join(part_dir, output_filename)
            visual.save(output_path)

            # Store mapping information
            relative_path = os.path.relpath(output_path, output_base)
            image_mapping[relative_path] = {
                "source_image": image_path,
                "part_name": part_name,
                "part_suffix": part_suffix,
                "object_type": object_type
            }

            logger.info(f"Saved: {output_path}")

        if not found_part:
            logger.debug(f"No parts containing '{part_search}' found in {image_path}")

    # Save the mapping information
    mapping_file = os.path.join(output_base, f"{part_search}_mapping.json")
    with open(mapping_file, 'wb') as f:
        f.write(orjson.dumps(image_mapping, option=orjson.OPT_INDENT_2))

    logger.info(f"Saved mapping information to {mapping_file}")
    return len(image_mapping)

def parse_args(args: list[str] = None):
    parser = argparse.ArgumentParser(description='Visualize annotated parts by part name/suffix')
    parser.add_argument('part_search', help='Search string to find in part names (e.g. "head", "leg")')
    parser.add_argument('--input', '-i', default=INPUT_JSON, help='Path to input annotations JSON')
    parser.add_argument('--output', '-o', default=OUTPUT_DIR, help='Path to output directory')
    return parser.parse_args(args)

if __name__ == '__main__':
    args = parse_args()

    with open(args.input, 'r') as f:
        annotations = orjson.loads(f.read())

    # Customize output directory with part search string
    output_dir = os.path.join(args.output, args.part_search)
    os.makedirs(output_dir, exist_ok=True)

    count = visualize_parts_by_name(annotations, args.part_search, output_dir)
    logger.info(f"Visualized {count} instances of parts containing '{args.part_search}'")