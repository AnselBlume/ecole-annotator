from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from services.image_queue import initialize_queue
from services.annotator import load_annotation_state
from routes.mask_rendering import router as render_mask_router
from routes.image_queue import router as image_queue_router
from routes.annotation import router as annotation_router
import logging
import coloredlogs

logger = logging.getLogger(__name__)
coloredlogs.install(level='INFO')

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    annotation_state = load_annotation_state()
    initialize_queue(annotation_state)
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)
app.include_router(render_mask_router, prefix='/mask') # Include the render_mask endpoints
app.include_router(image_queue_router, prefix='/queue') # Include the image_queue endpoints
app.include_router(annotation_router, prefix='/annotate') # Include the annotation endpoints

# Allow local frontend to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)