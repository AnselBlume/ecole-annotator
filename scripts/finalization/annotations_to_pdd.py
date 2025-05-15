'''
Run this file as a module from the root annotator directory via
    python -m scripts.finalization.annotations_to_pdd
'''
from __future__ import annotations
import os
import spacy
from pprint import pformat
import sys
import orjson
import yaml
from collections import defaultdict
from dataclasses import dataclass, field
from tqdm import tqdm
from typing import Any, Literal
import sys
sys.path.append('/shared/nas2/blume5/sp25/annotator/backend') # To allow its imports to work
from backend.dataset.utils import (
    get_object_prefix,
    get_category_name,
    get_object_name,
    get_part_suffix,
)
from backend.model import ImageAnnotation
import logging

logger = logging.getLogger(__name__)

# Copied from /shared/nas2/blume5/fa24/concept_downloading/annotation_processing/src/annotation_stats.py
DISABLE_TQDM = not sys.stdout.isatty()

nlp = spacy.load('en_core_web_sm')

@dataclass
class Concept:
    super_category: str
    fine_category: str
    part: str = None

def get_unique_objects(concepts: list[Concept]) -> tuple[list[Concept], dict[str, list[Concept]]]:
    unique_objects: list[Concept] = []
    duplicated_objects: dict[str, list[Concept]] = defaultdict(list)

    unique_names = set()
    for concept in tqdm(concepts, desc='Normalizing object names', disable=DISABLE_TQDM):
        assert concept.part is None
        concept_name = normalize_string(f'{concept.super_category} {concept.fine_category}')

        if concept_name in unique_names:
            duplicated_objects[concept_name].append(concept)
        else:
            unique_objects.append(concept)
            unique_names.add(concept_name)
            # Add the first instance in case it is later a duplicate
            duplicated_objects[concept_name].append(concept)

    # Remove instances that are not actually duplicates
    duplicated_objects = {
        concept_name: concept_list
        for concept_name, concept_list in duplicated_objects.items()
        if len(concept_list) > 1
    }

    return unique_objects, duplicated_objects

def get_unique_parts(concepts: list[Concept]) -> tuple[list[Concept], dict[str, list[Concept]]]:
    unique_parts: list[Concept] = []
    duplicated_parts: dict[str, list[Concept]] = defaultdict(list)

    unique_names = set()
    for concept in tqdm(concepts, desc='Normalizing part names', disable=DISABLE_TQDM):
        assert concept.part
        concept_name = normalize_string(concept.part)

        if concept_name in unique_names:
            duplicated_parts[concept_name].append(concept)
        else:
            unique_parts.append(concept)
            unique_names.add(concept_name)
            # Add the first instance in case it is later a duplicate
            duplicated_parts[concept_name].append(concept)

    # Remove instances that are not actually duplicates
    duplicated_parts = {
        concept_name: concept_list
        for concept_name, concept_list in duplicated_parts.items()
        if len(concept_list) > 1
    }

    return unique_parts, duplicated_parts

def normalize_string(s: str):
    s = s.strip().lower()
    doc = nlp(s)
    lemmatized = ' '.join([token.lemma_ for token in doc])

    return lemmatized

# Copied from partonomy_private
@dataclass
class ConceptGraph:
    instance_graph: dict[str, list[str]] = None
    part_graph: dict[str, list[str]] = None

@dataclass
class PartDatasetInstance:
    image_path: str = ''
    image_label: str = ''
    segmentations: dict[str, list[Any]] = field(default_factory=dict) # Mapping from labels to list of segmentations

    @property
    def segmentation_labels(self) -> list[str]:
        # For backwards compatibility
        return sorted(self.segmentations)

    def to_dict(self) -> dict[str, Any]:
        return {
            'image_path': self.image_path,
            'image_label': self.image_label,
            'segmentations': self.segmentations,
            'segmentation_labels': self.segmentation_labels,
        }

    def __hash__(self):
        return hash((self.image_path, self.image_label))

    @staticmethod
    def from_dict(d: dict[str, Any]) -> PartDatasetInstance:
        return PartDatasetInstance(
            image_path=d['image_path'],
            image_label=d['image_label'],
            segmentations=d['segmentations']
        )

@dataclass
class PartDatasetDescriptor:
    dataset_name: str = ''
    instances: list[PartDatasetInstance] = field(default_factory=list)
    part_graph: dict[str, list[str]] = field(default_factory=dict) # Adjacency list of objects --> their parts (possibly empty list)
    instance_graph: dict[str, list[str]] = field(default_factory=dict) # Adjacency list of objects --> their subobjects (possibly empty list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'dataset_name': self.dataset_name,
            'instances': [inst.to_dict() for inst in self.instances],
            'part_graph': self.part_graph,
            'instance_graph': self.instance_graph,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> PartDatasetDescriptor:
        return PartDatasetDescriptor(
            dataset_name=d['dataset_name'],
            instances=[PartDatasetInstance.from_dict(inst) for inst in d['instances']],
            part_graph=d['part_graph'],
            instance_graph=d['instance_graph'],
        )

def image_annot_to_label(annotation: ImageAnnotation) -> str:
    return get_object_prefix(next(iter(annotation.parts)))

def annotation_to_instance(annotation: ImageAnnotation) -> PartDatasetInstance:
    image_label = image_annot_to_label(annotation)

    segmentations = {
        part_name: part_annot.rles
        for part_name, part_annot in annotation.parts.items()
    }

    return PartDatasetInstance(
        image_path=annotation.image_path,
        image_label=image_label,
        segmentations=segmentations,
    )

def build_instance_graph(annotations: list[ImageAnnotation]) -> dict[str, list[str]]:
    instance_graph = defaultdict(set)

    for ann in annotations:
        image_label = image_annot_to_label(ann)
        category = get_category_name(image_label)
        instance_graph[category].add(image_label)

    instance_graph = {
        k : sorted(instance_graph[k])
        for k in sorted(instance_graph)
    }

    return instance_graph

def build_component_graph(annotations: list[ImageAnnotation]) -> dict[str, list[str]]:
    component_graph = defaultdict(set)

    for ann in annotations:
        image_label = image_annot_to_label(ann)
        component_graph[image_label].update(set(ann.parts))

    component_graph = {
        k : sorted(component_graph[k])
        for k in sorted(component_graph)
    }

    return component_graph

def build_pdd(annotations: list[ImageAnnotation]) -> tuple[PartDatasetDescriptor, dict[str, list[str]], dict[str, list[str]]]:
    instances = [annotation_to_instance(ann) for ann in annotations]
    instance_graph = build_instance_graph(annotations)
    component_graph = build_component_graph(annotations)

    pdd = PartDatasetDescriptor(
        dataset_name='partonomy_core-val',
        instances=instances,
        instance_graph=instance_graph,
        part_graph=component_graph,
    )

    return pdd, instance_graph, component_graph

def get_concepts(annotations: list[ImageAnnotation]) -> tuple[list[Concept], list[Concept]]:
    """Generate object and part concepts from the dataset.

    Args:
        masks_dir: Directory containing the mask files

    Returns:
        Tuple of (object_concepts, part_concepts) where each is a list of Concept objects
    """
    object_concepts = []
    part_concepts = []
    all_concept_names = set()

    for ann in annotations:
        image_label = image_annot_to_label(ann)
        category = get_category_name(image_label)
        object_prefix = get_object_prefix(image_label)
        object_name = get_object_name(image_label)

        if object_prefix not in all_concept_names:
            object_concepts.append(Concept(
                super_category=category,
                fine_category=object_name
            ))
            all_concept_names.add(object_prefix)

        for part_name in ann.parts:
            if part_name not in all_concept_names:
                part_concepts.append(Concept(
                    super_category=category,
                    fine_category=object_name,
                    part=get_part_suffix(part_name)
                ))
                all_concept_names.add(part_name)

    return object_concepts, part_concepts

def compute_stats(annotations: list[ImageAnnotation]) -> dict[str, Any]:
    object_concepts, part_concepts = get_concepts(annotations)

    logger.info(f'Number of annotations: {len(annotations)}')
    logger.info(f'Number of images: {len(set(ann.image_path for ann in annotations))}')

    # Count absolute number of object, part names
    logger.info(f'Number of object names: {len(object_concepts)}')
    logger.info(f'Number of part names: {len(part_concepts)}')

    # Normalize object, part names and recount
    unique_objects, duplicated_objects = get_unique_objects(object_concepts)
    unique_parts, duplicated_parts = get_unique_parts(part_concepts)

    logger.info(f'Number of normalized object names: {len(unique_objects)}')
    logger.info(f'Number of normalized part names: {len(unique_parts)}')

    logger.debug(f'Duplicated object names:\n{pformat(duplicated_objects)}')
    logger.debug(f'Duplicated part names:\n{pformat(duplicated_parts)}')

    # Compute number of parts with annotations
    n_annotations_per_part = defaultdict(int)
    n_images_per_part = defaultdict(int)
    for ann in annotations:
        for part_name, part_annot in ann.parts.items():
            assert part_annot.rles, f'Part {part_name} of {ann.image_path} has no annotations'
            n_annotations_per_part[part_name] += len(part_annot.rles)
            n_images_per_part[part_name] += 1

    logger.info(f'Number of total masks: {sum(n_annotations_per_part.values())}')
    logger.info(f'Minimum masks per part: {min(n_annotations_per_part.values())}')
    logger.info(f'Maximum masks per part: {max(n_annotations_per_part.values())}')

    logger.info(f'Number of unioned part annotations: {sum(n_images_per_part.values())}')
    logger.info(f'Minimum images per part: {min(n_images_per_part.values())}')
    logger.info(f'Maximum images per part: {max(n_images_per_part.values())}')

    # Count the number of masks in the PartDatasetDescriptor
    # The below code is correct, but it was written for loading the PDD from JSON
    # union_count = 0
    # total_count = 0
    # for instance in pdd['instances']:
    #     part_to_masks = instance['segmentations']
    #     union_count += len(part_to_masks) # Number of unique parts
    #     total_count += sum(len(masks) for masks in part_to_masks.values()) # Number of masks over all parts

    # print(f'Union count: {union_count}')
    # print(f'Total count: {total_count}')

    # Count the number of partlabels in a general PDD
    # parts = set()
    # for instance in pdd['instances']:
    #     parts.update(instance['segmentations'])
    # print(f'Number of parts: {len(parts)}')

def get_balanced_annotations(
    annotations: list[ImageAnnotation],
    exclude_objects: set[str],
    selection_strategy: Literal['max_part_annots', 'max_unique_parts']
) -> list[ImageAnnotation]:

    label_to_annots: dict[str, list[ImageAnnotation]] = defaultdict(list)
    label_to_paths: dict[str, set[str]] = defaultdict(set)
    for ann in annotations:
        for part_name, part_annot in ann.parts.items():
            assert part_annot.rles # Each part should have at least one annotation

            object_prefix = get_object_prefix(part_name)

            # If we're not excluding the object and haven't used the image for this object before
            if object_prefix not in exclude_objects and ann.image_path not in label_to_paths[object_prefix]:
                label_to_annots[object_prefix].append(ann)
                label_to_paths[object_prefix].add(ann.image_path)

    # Compute minimum number of annotations for an object
    min_count = min(len(annots) for annots in label_to_annots.values())
    logger.info(f'Minimum number of annotations for an object: {min_count}')

    # Sort labels by number of annotations and print the counts
    logger.debug(f'Counts:')
    for label, annots in sorted(label_to_annots.items(), key=lambda x: len(x[1]), reverse=True):
        logger.debug(f'{label}: {len(annots)}')

    def restrict_parts_to_object(annot: ImageAnnotation, object_label: str) -> ImageAnnotation:
        annot = annot.model_copy(deep=True)
        annot.parts = {
            part_name: part_annot
            for part_name, part_annot in annot.parts.items()
            if get_object_prefix(part_name) == object_label
        }

        return annot

    balanced_annots = []

    if selection_strategy == 'max_part_annots':
        # Select the ImageAnnotations such that we maximize the number of part annotations
        # Sort in descending order of number of part annotations
        # Images can have parts with no annotations, so we filter them out when counting
        for label, annots in label_to_annots.items():
            annots.sort(key=lambda x: len([
                p for p in x.parts.values()
                if get_object_prefix(p.name) == label # An image can have parts for multiple objects
            ]), reverse=True)

        for label, annots in label_to_annots.items():
            # Create ImageAnnotations with only the part annotations corresponding to this object
            for selected_annot in annots[:min_count]:
                balanced_annots.append(restrict_parts_to_object(selected_annot, label))

    elif selection_strategy == 'max_unique_parts':
        for label, annots in label_to_annots.items():
            # Build list of (annot, part suffix) pairs
            candidates = []
            for annot in annots:
                suffixes = {
                    get_part_suffix(part_name)
                    for part_name in annot.parts
                    if get_object_prefix(part_name) == label
                }
                candidates.append((annot, suffixes))

            covered: set[str] = set()
            selected: list[ImageAnnotation] = []

            # Greedy max-coverage loop
            for _ in range(min_count):
                # Pick candidate that adds the most new parts
                best_idx, (best_annot, best_suffixes) = max(
                    enumerate(candidates),
                    key=lambda enum_pair: len(enum_pair[1][1] - covered)
                )
                selected.append(best_annot)
                covered |= best_suffixes
                candidates.pop(best_idx)

            # Select part annotations corresponding only to this object
            for annot in selected:
                balanced_annots.append(restrict_parts_to_object(annot, label))

    else:
        raise ValueError(f'Invalid selection strategy: {selection_strategy}')

    return balanced_annots

if __name__ == '__main__':
    import coloredlogs
    coloredlogs.install(level='INFO')

    annotations_file = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
    output_dir = '/shared/nas2/blume5/sp25/annotator/data/generated_pdd'
    exclude_objects = {
        'geography--plateau'
    }

    balance_annotations = True
    selection_strategy = 'max_unique_parts'

    # Load annotations
    with open(annotations_file, 'rb') as f:
        annotations = orjson.loads(f.read())

    checked: dict[str, ImageAnnotation] = annotations['checked']
    annots = [ImageAnnotation.model_validate(annot) for annot in checked.values()]

    # Filter out parts with no annotations
    for annot in annots:
        for part_name, part_annot in list(annot.parts.items()):
            if not part_annot.rles:
                del annot.parts[part_name]

    filtered_annots = [annot for annot in annots if len(annot.parts) > 0] # Each annotation should have at least one part
    logger.info(f'Removed {len(annots) - len(filtered_annots)} annotations with no parts')
    annots = filtered_annots

    if balance_annotations:
        annots = get_balanced_annotations(annots, exclude_objects, selection_strategy)

    # Build PartDatasetDescriptor
    logger.info('Building PDD')

    pdd, instance_graph, component_graph = build_pdd(annots)
    with open(os.path.join(output_dir, 'partonomy-descriptor.json'), 'wb') as f:
        f.write(orjson.dumps(pdd.to_dict(), option=orjson.OPT_INDENT_2))

    # Save concept graph
    logger.info('Saving concept graph')

    graph_dict = {
        'concepts': sorted(set(pdi.image_label for pdi in pdd.instances)),
        'instance_graph': instance_graph,
        'component_graph': component_graph
    }

    with open(os.path.join(output_dir, 'graph.yaml'), 'w') as f:
        yaml.dump(graph_dict, f, indent=4)

    # Compute stats
    logger.info('Computing stats')
    compute_stats(annots)