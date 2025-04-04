PART_SEP = '--part:'

def is_part_name(label: str) -> bool:
    return PART_SEP in label

def get_part_suffix(label: str, safe: bool = False) -> str:
    if safe and not is_part_name(label):
        raise ValueError(f'Label is not a part name: {label}')
    return label.split(PART_SEP)[-1]

def get_object_prefix(label: str) -> str:
    return label.split(PART_SEP)[0]

def get_category_name(label: str):
    return label.split('--')[0]

def join_object_and_part(object_name: str, part_name: str) -> str:
    return f'{object_name}{PART_SEP}{part_name}'