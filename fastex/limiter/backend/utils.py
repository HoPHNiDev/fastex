import inspect
from collections.abc import Callable
from typing import Any


def filter_arguments(
    func: Callable[[Any], Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    sig = inspect.signature(func)
    try:
        bound = sig.bind_partial(*args, **kwargs)
    except TypeError:
        bound = sig.bind_partial()
        for name, param in sig.parameters.items():
            if name in kwargs:
                bound.arguments[name] = kwargs[name]
    bound.apply_defaults()
    return bound.arguments
