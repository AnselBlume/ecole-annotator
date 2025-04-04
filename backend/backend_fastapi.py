from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Dict
import json
import os
import redis
from dataset.annotation import collect_annotations, DatasetMetadata
import fcntl
from render_mask import router as render_mask_router
import logging
import coloredlogs

logger = logging.getLogger(__name__)
coloredlogs.install(level='INFO')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    initialize_queue()
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)
app.include_router(render_mask_router, prefix='/api') # Include the render_mask endpoints

# Allow local frontend to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

PARTONOMY_DIR = '/shared/nas2/blume5/fa24/concept_downloading/data/image_annotations/partonomy'
DATA_DIR = '/shared/nas2/blume5/sp25/annotator/data'
ANNOTATION_FILE = os.path.join(DATA_DIR, 'annotations.json')

# Redis client for concurrency-safe queueing
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class Part(BaseModel):
    label: str
    masks: List[str] = []

class ImageData(BaseModel):
    imagePath: str
    parts: List[Part]

class Annotation(BaseModel):
    imagePath: str
    partStatus: Dict[str, bool]

# Load image metadata into Redis queue (one-time initialization)
def initialize_queue():
    # Load annotations
    annotations: DatasetMetadata = collect_annotations(
        os.path.join(PARTONOMY_DIR, 'images'),
        os.path.join(PARTONOMY_DIR, 'masks')
    )

    if r.llen('image_queue') == 0:
        # Load existing annotations
        existing_annotations = set()
        if os.path.exists(ANNOTATION_FILE):
            with open(ANNOTATION_FILE) as f:
                all_anns = json.load(f)
                existing_annotations = {ann['imagePath'] for ann in all_anns}

        with open(os.path.join(DATA_DIR, 'images.json')) as f:
            image_list = json.load(f)
            for img in image_list:
                image_key = f'annotated:{img['imagePath']}'
                # Skip if annotated in either Redis or annotations.json
                if not r.exists(image_key) and img['imagePath'] not in existing_annotations:
                    r.rpush('image_queue', json.dumps(img))

@app.get('/api/next-image')
def get_next_image():
    while r.llen('image_queue') > 0:
        image_json = r.lpop('image_queue')
        if image_json:
            image_data = json.loads(image_json)
            image_key = f'annotated:{image_data['imagePath']}'
            if not r.exists(image_key):
                r.setex(f'lock:{image_data['imagePath']}', 600, 'locked')
                return image_data
    return {}

@app.post('/api/save-annotation')
def save_annotation(annotation: Annotation):
    # Save annotation to file with file locking
    with open(ANNOTATION_FILE, 'a+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Acquire exclusive lock
        try:
            f.seek(0)  # Move to start of file
            try:
                all_anns = json.load(f)
            except json.JSONDecodeError:
                all_anns = []
            all_anns.append(annotation.model_dump())
            f.seek(0)  # Move back to start
            f.truncate()  # Clear file
            json.dump(all_anns, f, indent=2)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock

    # Mark image as annotated in Redis
    r.set(f'annotated:{annotation.imagePath}', 1)
    r.delete(f'lock:{annotation.imagePath}')

    return {'status': 'saved'}