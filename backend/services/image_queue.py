from model import AnnotationState, ImageAnnotation
from services.redis_client import r, acquire_lock
import heapq
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

def _sort_queue_by_concept(
    annotation_state: AnnotationState,
    n_to_interleave: int
) -> list[ImageAnnotation]:
    """
    Order unchecked annotations so that, while the user is annotating, the
    cumulative number of *checked* images for every label stays as equal as
    possible.

    Args:
        annotation_state:  current annotation state
        n_to_interleave:   how many consecutive images of the same label to emit
                           each time that label is chosen (usually 1)

    Returns:
        A list of ImageAnnotation objects in the order they should be shown.
    """
    # --- helper to determine a label for any image --------------------------
    def get_image_label(img_annot: ImageAnnotation) -> str:
        try:
            return image_path_to_label(img_annot.image_path)
        except ValueError:
            return get_object_prefix(next(iter(img_annot.parts.values())).name)

    # --- build {label: [unchecked images]} ----------------------------------
    unchecked_by_label: dict[str, list[ImageAnnotation]] = defaultdict(list)
    for img in annotation_state.unchecked.values():
        unchecked_by_label[get_image_label(img)].append(img)

    # sort each label’s images (high‑value first, as before)
    for annots in unchecked_by_label.values():
        annots.sort(key=lambda x: len(x.parts), reverse=True)

    # --- count already‑checked ------------------------------------------------
    checked_count: dict[str, int] = defaultdict(int)
    for img in annotation_state.checked.values():
        checked_count[get_image_label(img)] += 1

    # --- produce balanced queue ---------------------------------------------
    return _interleave_to_balance_checked_counts(
        unchecked_by_label,
        checked_count,
        n_to_interleave
    )

def _interleave_to_balance_checked_counts(
    unchecked_by_label: dict[str, list[ImageAnnotation]],
    checked_count: dict[str, int],
    n_to_interleave: int
) -> list[ImageAnnotation]:
    """
    Always pop the label with the *lowest* current total (checked + already
    queued) so that totals stay as even as possible.

    Args:
        unchecked_by_label: {label: remaining unchecked images}
        checked_count:      {label: how many have already been checked}
        n_to_interleave:    images to emit per pop

    Returns:
        Ordered list of ImageAnnotation objects
    """
    # running totals = checked already + how many we have queued so far
    running_total = checked_count.copy()
    queued_count: dict[str, int] = defaultdict(int)

    # min‑heap keyed by (current_total, label)
    heap: list[tuple[int, str]] = [
        (running_total.get(lbl, 0), lbl) for lbl in unchecked_by_label
    ]
    heapq.heapify(heap)

    if heap:
        count, label = heap[0]
        logger.info(f'Label with minimum number of annotations: {label}: ({count})')
    else:
        logger.info('No labels found in unchecked_by_label.')

    ordered: list[ImageAnnotation] = []

    while heap:
        current_total, lbl = heapq.heappop(heap)
        images = unchecked_by_label[lbl]

        # take up to n_to_interleave images
        take = min(n_to_interleave, len(images))
        ordered.extend(images[:take])
        del images[:take]

        queued_count[lbl] += take
        running_total[lbl] = checked_count.get(lbl, 0) + queued_count[lbl]

        # if that label still has images left, push it back with new total
        if images:
            heapq.heappush(heap, (running_total[lbl], lbl))

    return ordered