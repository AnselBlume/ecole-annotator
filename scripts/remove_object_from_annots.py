'''
NOTE: Remember to also make a new version of the dataset with rhl, but COPY THE graph.yaml files over, not RHL!
Then, delete the mask folders for the parts you removed, and delete the entries from the copiedgraph.yaml files.
'''
import orjson
from tqdm import tqdm
from collections import defaultdict
from pprint import pformat
import sys
import os
from utils import backup_annotations, load_annotations, save_annotations
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), '../backend')))
from dataset.utils import get_object_prefix

def remove_object_from_dict(paths_dict: dict, objects_to_remove: set[str]):
    n_removed = defaultdict(int)

    for path, img_dict in tqdm(list(paths_dict.items())):
        try:
            object_name = get_object_prefix(next(iter(img_dict['parts'])))
        except StopIteration:
            print(f'No parts found for {path}')
            continue

        if object_name in objects_to_remove:
            del paths_dict[path]
            n_removed[object_name] += 1

    return n_removed

if __name__ == "__main__":
    annots_file = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'

    objects_to_remove = {
        'boats--aircraft'
    }

    backup_annotations(annots_file)
    annots = load_annotations(annots_file)

    for key in ['checked', 'unchecked']:
        paths_dict = annots[key]
        n_removed = remove_object_from_dict(paths_dict, objects_to_remove)
        print(f'Removed from {key}: {pformat(n_removed)}')

    save_annotations(annots, annots_file)