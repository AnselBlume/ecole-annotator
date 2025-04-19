import orjson
from tqdm import tqdm
from collections import defaultdict
from pprint import pformat

def move_parts_to_unchecked(annotations: dict, parts_to_move: set[str]):
    n_moved = defaultdict(int)

    paths_to_move = []
    for path, img_dict in tqdm(annotations['checked'].items()):
        for part_name in list(img_dict['parts']):
            if part_name in parts_to_move:
                # Move image from checked to unchecked
                paths_to_move.append(path)
                n_moved[part_name] += 1
                break

    for path in paths_to_move:
        annotations['unchecked'][path] = annotations['checked'][path]
        del annotations['checked'][path]

    return n_moved

if __name__ == "__main__":
    annots_file = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    out_path = '/shared/nas2/blume5/sp25/annotator/data/annotations-part-moved.json'
    parts_to_move = {
        'boats--amphibious--part:track system'
    }

    with open(annots_file, "rb") as f:
        annots = orjson.loads(f.read())

    n_moved = move_parts_to_unchecked(annots, parts_to_move)
    print(f'Moved: {pformat(n_moved)}')

    with open(out_path, "wb") as f:
        f.write(orjson.dumps(annots, option=orjson.OPT_INDENT_2))