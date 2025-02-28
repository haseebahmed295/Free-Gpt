import json
import g4f
import os

from typing import List, Tuple

def get_models() -> List[Tuple[str, str, str]]:
    """Get a list of available models.

    Returns:
        List[Tuple[str, str, str]]: A list of tuples where each tuple contains the model name repeated three times.
    """
    file_path = os.path.join(os.path.dirname(__file__), "data", "models.json")
    if not os.path.exists(file_path):
        deprecated_models = set()
    else:
        with open(file_path, 'r') as file:
            data = json.load(file)

        deprecated_models = set(data["deprecated"])
    available_models: List[Tuple[str, str, str]] = [
        (model, model, model) 
        for model in g4f.models._all_models 
        if model not in deprecated_models
    ]
    return available_models

