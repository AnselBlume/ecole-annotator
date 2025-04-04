import os
from PIL import Image, ImageOps
from PIL.Image import Image as PILImage

def open_image(path: str) -> PILImage:
    return ImageOps.exif_transpose(Image.open(path)).convert('RGB')

def label_from_directory(path: str):
    if not os.path.isdir(path):
        path = os.path.dirname(path)

    return os.path.basename(path).lower()

def list_paths(
    root_dir: str,
    exts: list[str] = None,
    follow_links: bool = True
):
    '''
        Lists all files in a directory with a given extension.

        Arguments:
            root_dir (str): Directory to search.
            exts (list[str]): List of file extensions to consider.

        Returns: List of paths.
    '''
    exts = set(exts) if exts else None
    paths = []
    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=follow_links):
        for filename in filenames:
            path = os.path.join(dirpath, filename)

            if not exts or os.path.splitext(path)[1].lower() in exts:
                paths.append(path)

    paths = sorted(paths)

    return paths