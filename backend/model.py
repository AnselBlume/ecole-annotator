from pydantic import BaseModel
from dataset.annotation import RLEAnnotationWithMaskPath

class PartAnnotation(BaseModel):
    name: str
    rles: list[RLEAnnotationWithMaskPath] = []

    was_checked: bool = False
    is_poor_quality: bool = False
    is_incorrect: bool = False

class ImageAnnotation(BaseModel):
    image_path: str
    parts: dict[str, PartAnnotation]

class AnnotationState(BaseModel):
    checked: dict[str, ImageAnnotation]
    unchecked: dict[str, ImageAnnotation]

class ImageQualityUpdate(BaseModel):
    image_path: str
    is_poor_quality: bool = False
    is_incorrect: bool = False