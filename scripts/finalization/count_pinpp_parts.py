import json
from collections import Counter

# Load JSON data
in_file = '/shared/nas2/blume5/sp25/annotator/scripts/finalization/pinpp_category_name.json'

with open(in_file, "r") as f:
    data = json.load(f)

def extract_part_name(full_part_name: str, object_name: str) -> str:
    """
    Return the part name with the object prefix removed (case-insensitive).
    If the part does not start with the object name, the original string is returned.
    """
    obj = object_name.replace("_", " ").lower()
    part = full_part_name.lower().strip()

    if part == obj:
        return part

    assert part.startswith(obj)
    return part.removeprefix(obj).strip()

# Collect cleaned part names
part_names = {
    extract_part_name(part, item["object name"])
    for item in data
    for part in item["part name"]
}

# Report
print("Unique object-independent part names:")
for name in sorted(part_names):
    print("-", name)
print("\nTotal unique part names:", len(part_names))