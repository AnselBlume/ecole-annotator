from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import time
from pathlib import Path
from contextlib import asynccontextmanager
from services.image_queue import initialize_queue
from services.annotator import load_annotation_state, save_annotation_state
from routes.mask_rendering import router as render_mask_router
from routes.image_queue import router as image_queue_router
from routes.annotation import router as annotation_router, get_sam2_predictor
import logging
import coloredlogs

logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG', isatty=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SAM2 model on startup
    logger.info("Initializing SAM2 model...")
    get_sam2_predictor()  # Initialize the singleton

    # Initialize image queue from disk
    logger.info("Initializing image queue...")
    annotation_state = load_annotation_state()
    save_annotation_state(annotation_state, to_file=False)
    initialize_queue(annotation_state)

    logger.info("Startup complete")
    yield
    # Cleanup on shutdown
    logger.info("Shutting down...")

app = FastAPI(
    title="Image Annotation API",
    description="API for image annotation with SAM2",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)

    # Log endpoint timing for performance monitoring
    logger.info(f"Request to {request.url.path} completed in {process_time:.4f} seconds")

    return response

# Exception handler for better error logging
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception in {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )

# Mount routes
app.include_router(render_mask_router, prefix='/mask') # Include the render_mask endpoints
app.include_router(image_queue_router, prefix='/queue') # Include the image_queue endpoints
app.include_router(annotation_router, prefix='/annotate') # Include the annotation endpoints

# Add a route to serve images for annotation
@app.get("/images/{image_path:path}")
async def get_image(image_path: str):
    """
    Serve an image file for annotation.
    This allows the frontend to display images for annotation.
    """
    try:
        # Ensure the path is safe and within the allowed directory
        full_path = Path(image_path)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Image not found")

        return FileResponse(full_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve image: {str(e)}")

# Mount static files
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning(f"Static directory {static_dir} does not exist, static files not mounted")

@app.get("/")
def read_root():
    return {
        "message": "Image Annotation API",
        "version": "0.1.0",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}