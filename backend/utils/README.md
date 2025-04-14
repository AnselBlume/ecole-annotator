# Backend Utilities Module

This module contains reusable utility functions for the backend application, organized by functionality.

## Module Structure

- `__init__.py` - Package initialization
- `api_utils.py` - API response handling utilities
- `image_utils.py` - Image processing and conversion utilities
- `mask_utils.py` - Mask and RLE handling utilities

## Usage

### API Utilities

Contains functions for handling API responses consistently:

```python
from utils.api_utils import error_response, success_response, image_response

# Return error response
return error_response("Invalid input", status_code=400)

# Return success response with data
return success_response({"data": result})

# Return an image as a streaming response
return image_response(pil_image, format='JPEG')
```

### Image Utilities

Functions for image processing and manipulation:

```python
from utils.image_utils import load_image_from_path, image_to_base64, create_debug_overlay

# Load an image with dimensions
image, width, height = load_image_from_path(image_path)

# Convert an image to base64 string
base64_str = image_to_base64(pil_image)

# Create a debug visualization
debug_image = create_debug_overlay(base_image, "Debug message")
```

### Mask Utilities

Utilities for working with binary masks and RLE format:

```python
from utils.mask_utils import process_rle_data, decode_rle_to_mask, create_mask_image

# Process raw RLE data with validation
rle_dict = process_rle_data(rle_data, width, height)

# Decode RLE to binary mask
mask = decode_rle_to_mask(rle_dict)

# Create a visualization of a mask
mask_image = create_mask_image(mask, base_image, overlay=True)
```

## Benefits of Modularization

1. **Reusability**: Common functions are extracted to avoid code duplication
2. **Maintainability**: Changes to functionality only need to be made in one place
3. **Testability**: Functions with focused responsibility are easier to test
4. **Readability**: Route handlers are simplified with clear separation of concerns
5. **Consistency**: Standardized response formats and error handling