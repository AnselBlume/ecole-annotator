from move_image_to_unchecked import move_image_to_unchecked
from utils import backup_annotations, load_annotations, save_annotations, get_object_prefix
from tqdm import tqdm
import logging
import coloredlogs

logger = logging.getLogger(__name__)

def move_class_to_unchecked(annotations: dict, class_name: str) -> dict:
    img_paths = []
    for k in ['checked', 'unchecked']:
        logger.info(f'Processing {k} images')

        for path, img_dict in tqdm(annotations[k].items()):
            for part in img_dict['parts']:
                if get_object_prefix(part) == class_name:
                    img_paths.append(path)
                    break

    logger.info(f'Moving {len(img_paths)} images to unchecked')
    for path in tqdm(img_paths):
        move_image_to_unchecked(annotations, path)

    return annotations

if __name__ == '__main__':
    coloredlogs.install(level='INFO')

    annotations_path = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    class_name = 'geography--plateau'

    backup_annotations(annotations_path)

    d = load_annotations(annotations_path)

    d = move_class_to_unchecked(d, class_name)

    save_annotations(d, annotations_path)