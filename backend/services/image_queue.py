from model import AnnotationState, ImageAnnotation
from services.redis_client import r, acquire_lock
import json
from typing import Any, Optional
from services.annotator import image_path_to_label, get_object_prefix
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# Redis keys
IMAGE_QUEUE_KEY = 'image_queue'
IMAGE_QUEUE_LOCK_KEY = 'image_queue_lock'

# Load image metadata into Redis queue (one-time initialization)
def initialize_queue(annotation_state: AnnotationState, sort_by_concept: bool = True, n_to_interleave: int = 1):
    if sort_by_concept:
        logger.info('Sorting queue by concept')
        image_queue = _sort_queue_by_concept(annotation_state, n_to_interleave)
    else:
        image_queue = list(annotation_state.unchecked.values())

    image_queue = [json.dumps(img.model_dump()) for img in image_queue]

    if image_queue:
        r.delete(IMAGE_QUEUE_KEY)  # Clear old data first
        r.rpush(IMAGE_QUEUE_KEY, *image_queue)

def acquire_image_queue_lock() -> Optional[Any]:
    '''Try to acquire a lock for the image queue with retry logic.

    Returns:
        The lock object if acquired, None otherwise

    Raises:
        LockAcquisitionError: If the lock cannot be acquired after retries
    '''
    return acquire_lock(IMAGE_QUEUE_LOCK_KEY)

def _sort_queue_by_concept(annotation_state: AnnotationState, n_to_interleave: int) -> list[ImageAnnotation]:
    '''
    Interleaves the unchecked annotations by concept, where concepts with existing annotations are annotated last.
    Annotations are sorted by the number of existing parts to try annotating high-value images first.

    Args:
        annotation_state: The annotation state to sort
        n_to_interleave: The number of annotations of each label before switching to the next label

    Returns:
        A list of interleaved annotations
    '''
    def get_image_label(img_annot: ImageAnnotation) -> str:
        try:
            return image_path_to_label(img_annot.image_path)
        except ValueError:
            extracted_label = get_object_prefix(next(iter(img_annot.parts.values())).name)
            logger.debug(f'Failed to get label for image {img_annot.image_path} from path; extracted from part name: {extracted_label}')
            return extracted_label

    # Labels with existing annotations should be annotated last
    labels_with_existing_annots = set()
    for img_annot in annotation_state.checked.values():
        labels_with_existing_annots.add(get_image_label(img_annot))

    image_annots = list(annotation_state.unchecked.values())
    label_to_annots = defaultdict(list)
    for img in image_annots:
        label_to_annots[get_image_label(img)].append(img)

    logger.info(f'Number of labels with existing annotations: {len(labels_with_existing_annots)}')
    logger.info(f'Number of labels without existing annotations: {len(set(label_to_annots) - labels_with_existing_annots)}')

    # Sort each label's annotations by the number of existing parts to try annotating high-value images first
    for label, annots in label_to_annots.items():
        annots.sort(key=lambda x: len(x.parts), reverse=True)

    # Interleave the sorted annotations
    label_without_annots_to_annots = {l : a for l, a in label_to_annots.items() if l not in labels_with_existing_annots}
    interleaved = _interleave_annots(label_without_annots_to_annots, n_to_interleave)

    label_with_annots_to_annots = {l : a for l, a in label_to_annots.items() if l in labels_with_existing_annots}
    interleaved.extend(_interleave_annots(label_with_annots_to_annots, n_to_interleave))

    return interleaved

def _interleave_annots(annots_by_label: dict[str, list[ImageAnnotation]], n_to_interleave: int) -> list[ImageAnnotation]:
    '''
    Interleave the annotations from the given dictionary of annotations by label.
    Continues until all annotations from all labels have been interleaved.

    Args:
        annots_by_label: A dictionary mapping labels to lists of annotations
        n_to_interleave: The number of annotations of each label before switching to the next label

    Returns:
        A list of interleaved annotations
    '''
    interleaved = []

    while len(annots_by_label) > 0: # There are still labels to interleave
        labels_to_remove = []

        for label, annots in annots_by_label.items():
            if len(annots) == 0: # No more annotations for this label
                labels_to_remove.append(label)
                continue

            # Pop the next n_to_interleave annotations for this label
            n_to_pop = min(n_to_interleave, len(annots))
            for _ in range(n_to_pop):
                interleaved.append(annots.pop(0))

        for label in labels_to_remove:
            del annots_by_label[label]

    return interleaved