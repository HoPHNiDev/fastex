import inspect
from collections.abc import Callable
from typing import Any


def singleton(cls):
    instances = {}

    def getinstance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return getinstance


def _filter_arguments(
    func: Callable[[Any], Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    sig = inspect.signature(func)
    bound = sig.bind_partial(*args, **kwargs)
    bound.apply_defaults()
    filtered_arguments = {k: v for k, v in bound.arguments.items()}

    return filtered_arguments
