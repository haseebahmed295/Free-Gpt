import json
import os
from .Settings import JSON_PATH
from typing import List, Tuple
no_dep = False
try:
    import g4f
except ModuleNotFoundError:
    no_dep = True

def get_models() -> List[Tuple[str, str, str]]:
    """Get a list of available models.

    Returns:
        List[Tuple[str, str, str]]: A list of tuples where each tuple contains the model name repeated three times.
    """
    file_path = JSON_PATH
    if not os.path.exists(file_path):
        deprecated_models = set()
    else:
        with open(file_path, 'r') as file:
            data = json.load(file)

        deprecated_models = set(data["deprecated"])
    if not no_dep:
        available_models: List[Tuple[str, str, str]] = [
            (model, model, model) 
            for model in g4f.models._all_models 
            if model not in deprecated_models
        ]
    else:
        available_models = []
    return available_models

