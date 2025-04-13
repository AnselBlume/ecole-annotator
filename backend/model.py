from pydantic import BaseModel
from dataset.annotation import RLEAnnotationWithMaskPath
from typing import List

class Point(BaseModel):
    x: int
    y: int

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

class PointPrompt(BaseModel):
    image_path: str
    part_name: str
    positive_points: List[Point]
    negative_points: List[Point] = []
    mask_input: dict = None  # Optional: RLE encoded mask to improve prediction

class PolygonPrompt(BaseModel):
    image_path: str
    part_name: str
    polygon_points: List[Point]