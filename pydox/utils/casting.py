from typing import Any


def to_list(x: Any) -> list[Any]:
    return x if isinstance(x, list) else [x]
