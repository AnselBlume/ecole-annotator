import os
import shutil
import time
import orjson

def backup_annotations(annotations_path: str, backup_dir: str = None):
    if backup_dir is None:
        backup_dir = os.path.dirname(annotations_path)

    os.makedirs(backup_dir, exist_ok=True)

    time_str = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
    backup_path = os.path.join(backup_dir, f'{time_str}_annotations.json')

    shutil.copy(annotations_path, backup_path)

    return backup_path

def load_annotations(annotations_path: str) -> dict:
    with open(annotations_path, 'rb') as f:
        return orjson.loads(f.read())

def save_annotations(annotations: dict, annotations_path: str, indent=True):
    kwargs = {}
    if indent:
        kwargs['option'] = orjson.OPT_INDENT_2

    with open(annotations_path, 'wb') as f:
        f.write(orjson.dumps(annotations, **kwargs))