from utils import backup_annotations, load_annotations, save_annotations
from pprint import pformat

def find_paths_containing_str(annotations: dict, search_str: str):
    paths = []
    for key in ['checked', 'unchecked']:
        for path in annotations[key]:
            if search_str in path:
                paths.append(path)
    return paths

def remove_path(annotations: dict, remove_img_path: str):
    # Try to remove from checked first
    if path in annotations['checked']:
        annotations['checked'].pop(path)
        print(f'Removed from checked: {path}')
    # If not in checked, try unchecked
    elif path in annotations['unchecked']:
        annotations['unchecked'].pop(path)
        print(f'Removed from unchecked: {path}')
    else:
        print(f'Warning: Path not found in either checked or unchecked: {path}')

if __name__ == '__main__':
    annotations_path = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    search_str = '3fadf803a31669d15c063bcce22e3793cf63fe5ca52ded1e66e6d3ebffd372e8.jpg'

    backup_annotations(annotations_path)

    d = load_annotations(annotations_path)

    paths = find_paths_containing_str(d, search_str)
    print(f'There are {len(paths)} paths containing the image path: \n {pformat(paths)}')

    for path in paths:
        response = input(f'Remove {path}? (y/n): ')
        if response.lower() == 'y':
            remove_path(d, path)

    save_annotations(d, annotations_path)