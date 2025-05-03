import argparse
import os
from utils import load_annotations, save_annotations, backup_annotations
from tqdm import tqdm
from collections import defaultdict
from pprint import pformat

def rename_part(annotations: dict, old_part_name: str, new_part_name: str):
    """
    Rename a part in the annotations dictionary.

    Args:
        annotations: The annotations dictionary
        old_part_name: The old name of the part (full name including class prefix)
        new_part_name: The new name of the part (full name including class prefix)

    Returns:
        A dictionary with stats about the renaming operation
    """
    n_renamed = defaultdict(int)

    # Process both checked and unchecked images
    for status in ['checked', 'unchecked']:
        paths_dict = annotations[status]
        for path, img_dict in tqdm(paths_dict.items(), desc=f"Processing {status}"):
            if old_part_name in img_dict['parts']:
                # Get the part data
                part_data = img_dict['parts'][old_part_name]

                # Add the part with the new name
                img_dict['parts'][new_part_name] = part_data

                # Remove the old part
                del img_dict['parts'][old_part_name]

                n_renamed[status] += 1

    return dict(n_renamed)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Rename a part in the annotations')
    parser.add_argument('--old_part', type=str, required=True,
                        help='The old part name (e.g., "boats--airboat--part:stern plate")')
    parser.add_argument('--new_part', type=str, required=True,
                        help='The new part name (e.g., "boats--airboat--part:back plate")')
    parser.add_argument('--annotations_path', type=str,
                        default='/shared/nas2/blume5/sp25/annotator/data/annotations.json',
                        help='Path to the annotations file')
    parser.add_argument('--out_path', type=str,
                        default=None,
                        help='Path to save the new annotations. If not provided, will modify in place.')

    args = parser.parse_args()

    # Create backup before making changes
    backup_path = backup_annotations(args.annotations_path)
    print(f"Created backup at {backup_path}")

    # Load annotations
    annotations = load_annotations(args.annotations_path)

    # Rename parts
    renamed_stats = rename_part(annotations, args.old_part, args.new_part)
    print(f"Renamed part '{args.old_part}' to '{args.new_part}':")
    print(pformat(renamed_stats))

    # Save the annotations
    out_path = args.out_path or args.annotations_path
    save_annotations(annotations, out_path)
    print(f"Saved annotations to {out_path}")
