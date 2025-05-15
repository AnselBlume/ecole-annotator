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
    n_imgs_removed = defaultdict(int)
    n_parts_removed = defaultdict(int)

    for path, img_dict in tqdm(list(paths_dict.items())):
        removed_part = False
        for part in list(img_dict['parts']):
            object_name = get_object_prefix(part)

            if object_name in objects_to_remove:
                print(f'Removing {object_name} from {path} with part {part}')
                del img_dict['parts'][part]
                n_parts_removed[object_name] += 1
                removed_part = True

        if removed_part and len(img_dict['parts']) == 0: # Don't just delete dicts without parts
            print(f'Removing {path} because it has no parts')
            del paths_dict[path]
            n_imgs_removed[object_name] += 1

    return n_imgs_removed, n_parts_removed

if __name__ == "__main__":
    annots_file = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'

    objects_to_remove = {
        'helicopter--fuel system'
    }

    backup_annotations(annots_file)
    annots = load_annotations(annots_file)

    for key in ['checked', 'unchecked']:
        paths_dict = annots[key]
        n_imgs_removed, n_parts_removed = remove_object_from_dict(paths_dict, objects_to_remove)
        print(f'Removed from {key}: {pformat(n_imgs_removed)}')
        print(f'Removed from {key}: {pformat(n_parts_removed)}')

    if 'excluded_objects' not in annots:
        annots['excluded_objects'] = []

    annots['excluded_objects'].extend(objects_to_remove)

    save_annotations(annots, annots_file)