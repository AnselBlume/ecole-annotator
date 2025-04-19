from move_image_to_unchecked import move_image_to_unchecked
from utils import backup_annotations, load_annotations, save_annotations

if __name__ == '__main__':
    annotations_path = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    debug_img_path = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/24-11-18/annotations/all_annotations/UCLA/Zi-Yi/Boats/banana_boat/images/e21adf03bffd563d814c1fde730105a96517212568a72bc539727291bec4eefb.jpg'

    backup_annotations(annotations_path)

    d = load_annotations(annotations_path)

    d = move_image_to_unchecked(d, debug_img_path, clear_unchecked=True)

    save_annotations(d, annotations_path)