from utils import backup_annotations, load_annotations, save_annotations
from pprint import pformat

def find_paths_containing_str(annotations: dict, search_str: str):
    paths = []
    for key in ['checked', 'unchecked']:
        for path in annotations[key]:
            if search_str in path:
                paths.append(path)
    return paths

def move_image_to_unchecked(annotations: dict, img_path: str, clear_unchecked: bool = False) -> dict:
    # Find the annotation
    try:
        img_dict = annotations['checked'].pop(img_path)
    except KeyError:
        img_dict = annotations['unchecked'].pop(img_path)

    for part, part_dict in img_dict['parts'].items():
        part_dict['was_checked'] = False

    if clear_unchecked:
        annotations['unchecked'].clear()

    annotations['unchecked'] = { # Add image to the front of the unchecked dict
        img_path: img_dict,
        **annotations['unchecked'],
    }

    return annotations

if __name__ == '__main__':
    annotations_path = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'

    backup_annotations(annotations_path)
    d = load_annotations(annotations_path)

    running = True
    while running:
        # Choose search mode
        mode = input("\nChoose mode - (1) Search by substring, (2) Direct path entry, (q) Quit: ").lower()

        if mode == 'q':
            running = False
            continue

        if mode == '1':
            # Search mode
            searching = True
            while searching:
                search_str = input("\nEnter search string (or 'back' to return to main menu): ")
                if search_str.lower() == 'back':
                    searching = False
                    continue

                print(f'Searching for {search_str}')
                paths = find_paths_containing_str(d, search_str)
                print(f'There are {len(paths)} paths containing the search string: \n {pformat(paths)}')

                for path in paths:
                    response = input(f'Move {path} to unchecked? (y/n): ')
                    if response.lower() == 'y':
                        d = move_image_to_unchecked(d, path)
                        print(f'Moved to unchecked: {path}')

                save_annotations(d, annotations_path)
                print("Changes saved.")

        elif mode == '2':
            # Direct mode
            direct_entry = True
            while direct_entry:
                img_path = input("\nEnter exact image path (or 'back' to return to main menu): ")
                if img_path.lower() == 'back':
                    direct_entry = False
                    continue

                try:
                    d = move_image_to_unchecked(d, img_path)
                    print(f'Moved to unchecked: {img_path}')
                    save_annotations(d, annotations_path)
                    print("Changes saved.")
                except KeyError:
                    print(f"Error: Path '{img_path}' not found in annotations.")

        else:
            print("Invalid option. Please choose 1, 2, or q.")

    print("Script finished.")