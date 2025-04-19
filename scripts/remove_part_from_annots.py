'''
NOTE: Remember to also make a new version of the dataset with rhl, but COPY THE graph.yaml files over, not RHL!
Then, delete the mask folders for the parts you removed, and delete the entries from the copiedgraph.yaml files.
'''
import orjson
from tqdm import tqdm
from collections import defaultdict
from pprint import pformat

def remove_part_from_dict(paths_dict: dict, parts_to_remove: set[str]):
    n_removed = defaultdict(int)

    for path, img_dict in tqdm(paths_dict.items()):
        for part_name in list(img_dict['parts']):
            if part_name in parts_to_remove:
                del img_dict['parts'][part_name]
                n_removed[part_name] += 1

    return n_removed

if __name__ == "__main__":
    annots_file = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    out_path = '/shared/nas2/blume5/sp25/annotator/data/annotations-part-removed.json'
    parts_to_remove = {
        'boats--airboat--part:stern plate'
    }

    with open(annots_file, "rb") as f:
        annots = orjson.loads(f.read())

    for key in ['checked', 'unchecked']:
        paths_dict = annots[key]
        n_removed = remove_part_from_dict(paths_dict, parts_to_remove)
        print(f'Removed from {key}: {pformat(n_removed)}')

    with open(out_path, "wb") as f:
        f.write(orjson.dumps(annots, option=orjson.OPT_INDENT_2))