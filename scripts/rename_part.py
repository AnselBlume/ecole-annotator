import jsonargparse
from utils import load_annotations, save_annotations, backup_annotations
from tqdm import tqdm
from collections import defaultdict
from pprint import pformat
from typing import Literal
import os
import logging
import coloredlogs
import sys
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '../backend')))
from dataset.utils import get_part_suffix, get_object_prefix, join_object_and_part

logger = logging.getLogger(__name__)

MatchStrategy = Literal['contains', 'exact', 'part_suffix_exact', 'part_suffix_contains']
RenamingStrategy = Literal[
    'full_replace',
    'part_suffix_replace',
    'substring_replace',
    'part_suffix_substring_replace',
    'append',
    'prepend'
]

def is_match(query: str, target: str, strategy: MatchStrategy):
    '''
    Check if the query matches the target using the given strategy.

    Strategies:
        - exact: The query must match the target exactly (fully-qualified name).
        - part_suffix_exact: The query must match the target's part suffix exactly.
        - part_suffix_contains: The target's part suffix must contain the query.
        - contains: The target must contain the query.
    '''
    query = query.lower()
    target = target.lower()

    # In order of most to least restrictive
    if strategy == 'exact':
        return query == target
    elif strategy == 'part_suffix_exact':
        return query == get_part_suffix(target)
    elif strategy == 'part_suffix_contains':
        return query in get_part_suffix(target)
    elif strategy == 'contains':
        return query in target
    else:
        raise ValueError(f"Invalid strategy: {strategy}")

def map_to_new_name(query: str, old_part_name: str, new_part_name: str, strategy: RenamingStrategy):
    '''
    Map the old part name to the new part name using the given strategy.
    If the strategy is 'exact', the new part name is returned as is.
    If the strategy is 'part_suffix_exact', the new part name is used as the suffix with the old object prefix.
    If the strategy is 'part_suffix_contains', the new part name is used as the suffix with the old object prefix.
    If the strategy is 'contains', the new part name is used as the suffix with the old object prefix.
    '''
    if strategy == 'full_replace':
        return new_part_name
    elif strategy == 'part_suffix_replace':
        return join_object_and_part(get_object_prefix(old_part_name), new_part_name)
    elif strategy == 'substring_replace':
        return old_part_name.replace(query, new_part_name)
    elif strategy == 'part_suffix_substring_replace':
        return join_object_and_part(get_object_prefix(old_part_name), old_part_name.replace(query, new_part_name))
    elif strategy == 'append':
        return f'{old_part_name}{new_part_name}'
    elif strategy == 'prepend':
        return f'{new_part_name}{old_part_name}'
    else:
        raise ValueError(f"Invalid strategy: {strategy}")

def rename_part(annotations: dict, query: str, new_part_name: str, strategy: MatchStrategy = 'exact', renaming_strategy: RenamingStrategy = 'full_replace'):
    """
    Rename a part in the annotations dictionary.

    Args:
        annotations: The annotations dictionary
        old_part_name: The old name of the part (full name including class prefix)
        new_part_name: The new name of the part (full name including class prefix)

    Returns:
        A dictionary with stats about the renaming operation
    """
    n_renamed_by_status = defaultdict(int)
    n_renamed_by_part = defaultdict(int)

    # Process both checked and unchecked images
    for status in ['checked', 'unchecked']:
        paths_dict = annotations[status]
        for path, img_dict in tqdm(paths_dict.items(), desc=f"Processing {status}"):
            for part_name, part_data in list(img_dict['parts'].items()):
                if is_match(query, part_name, strategy):
                    renamed_part_name = map_to_new_name(query, part_name, new_part_name, renaming_strategy)

                    if part_name not in n_renamed_by_part:
                        logger.debug(f"Renaming {part_name} ---> {renamed_part_name}")

                    part_data['name'] = renamed_part_name

                    # Add the part with the new name
                    img_dict['parts'][renamed_part_name] = part_data

                    # Remove the old part
                    del img_dict['parts'][part_name]

                    n_renamed_by_status[status] += 1
                    n_renamed_by_part[part_name] += 1

    return dict(n_renamed_by_status), dict(n_renamed_by_part)

if __name__ == "__main__":
    coloredlogs.install(level='DEBUG')

    parser = jsonargparse.ArgumentParser(description='Rename a part in the annotations')
    parser.add_argument('--query', type=str, required=True,
                        help='The old part name (e.g., "boats--airboat--part:stern plate", or "stern plate", if using a part suffix strategy)')
    parser.add_argument('--new_part_name', type=str, required=True,
                        help='The new part name (e.g., "boats--airboat--part:back plate"), or "back plate", if using a part suffix strategy)')
    parser.add_argument('--annotations_path', type=str,
                        default='/shared/nas2/blume5/sp25/annotator/data/annotations.json',
                        help='Path to the annotations file')
    parser.add_argument('--out_path', type=str,
                        default=None,
                        help='Path to save the new annotations. If not provided, will modify in place.')

    parser.add_argument('--match_strategy', type=MatchStrategy,
                        default='exact',
                        help='The strategy to use for matching parts (contains, exact)')
    parser.add_argument('--renaming_strategy', type=RenamingStrategy,
                        default='full_replace',
                        help='The strategy to use for renaming parts')

    args = parser.parse_args()

    # Create backup before making changes
    backup_path = backup_annotations(args.annotations_path)
    logger.info(f"Created backup at {backup_path}")

    # Load annotations
    annotations = load_annotations(args.annotations_path)

    # Rename parts
    renamed_stats, renamed_stats_by_part = rename_part(annotations, args.query, args.new_part_name, args.match_strategy, args.renaming_strategy)
    logger.info(f"Renamed parts using query '{args.query}' to '{args.new_part_name}':")
    logger.info(pformat(renamed_stats))
    logger.info(pformat(renamed_stats_by_part))

    # Save the annotations
    out_path = args.out_path or args.annotations_path
    save_annotations(annotations, out_path)
    logger.info(f"Saved annotations to {out_path}")
