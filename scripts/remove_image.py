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
    search_strs = [
        '58ff99b931544ffb3d699f65f487c73107ee36ca2819a8ca2bc12a63c55e0a1c.jpg',
    ]

    backup_annotations(annotations_path)

    d = load_annotations(annotations_path)

    for search_str in search_strs:
        print(f'Searching for {search_str}')
        paths = find_paths_containing_str(d, search_str)
        print(f'There are {len(paths)} paths containing the image path: \n {pformat(paths)}')

        for path in paths:
            response = input(f'Remove {path} ? (y/n): ')
            if response.lower() == 'y':
                remove_path(d, path)

    save_annotations(d, annotations_path)