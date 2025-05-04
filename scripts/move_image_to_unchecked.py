from utils import backup_annotations, load_annotations, save_annotations

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
    img_path = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/24-11-18/annotations/all_annotations/UCLA/Da/Geography/city/images/images (2).jpeg'

    backup_annotations(annotations_path)

    d = load_annotations(annotations_path)

    d = move_image_to_unchecked(d, img_path)

    save_annotations(d, annotations_path)