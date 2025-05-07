# %%
from utils import locate_str, load_annotations
from PIL import Image
from matplotlib import pyplot as plt

annotations_path = '/shared/nas2/blume5/sp25/annotator/data/annotations.json'
annotations = load_annotations(annotations_path)

# %%
search_str = 'highway_map_10.jpg'

matches = locate_str(search_str, annotations)

for k, l in matches.items():
    for path in l:
        print(f'Path: {path}')
        img = Image.open(path)
        plt.imshow(img)
        plt.axis('off')
        plt.show()
# %%
