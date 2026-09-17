from typing import TypeVar

T = TypeVar("T")


def batches(items: list[T], size: int) -> list[list[T]]:
    if size < 1:
        raise ValueError("batch size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]
