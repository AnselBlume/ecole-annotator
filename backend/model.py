from pydantic import BaseModel
from dataset.annotation import RLEAnnotationWithMaskPath

class PartAnnotation(BaseModel):
    name: str
    rles: list[RLEAnnotationWithMaskPath] = []

    was_checked: bool = False
    is_correct: bool = True
    is_poor_quality: bool = False
    is_complete: bool = True

class ImageAnnotation(BaseModel):
    image_path: str
    parts: dict[str, PartAnnotation]

class AnnotationState(BaseModel):
    checked: dict[str, ImageAnnotation]
    unchecked: dict[str, ImageAnnotation]

class ImageQualityUpdate(BaseModel):
    image_path: str
    is_complete: bool = None
    is_poor_quality: bool = None
    is_correct: bool = None