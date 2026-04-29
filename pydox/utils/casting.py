from typing import Any


def to_list(x: Any) -> list[Any]:
    """Convert object to a list"""
    return x if isinstance(x, list) else [x]


def ulist(l: list[Any]) -> list[Any]:
    """Get unique item in list, even if not hashable"""
    u: list[Any] = []
    for item in l:
        if item not in u:
            u.append(item)
    return u


def is_ulist(l: list[Any]) -> bool:
    """Has the list only unique values ?"""
    return len(l) == len(ulist(l))


def is_ctelist(l: list[Any]) -> bool:
    """Has the list a single unique value ?"""
    return len(ulist(l)) == 1
