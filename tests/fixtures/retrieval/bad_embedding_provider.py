from __future__ import annotations


def zero(texts: list[str], *, model: str) -> list[list[float]]:
    return [[0.0, 0.0] for _ in texts]


def non_finite(texts: list[str], *, model: str) -> list[list[float]]:
    return [[float("nan"), 1.0] for _ in texts]


def inconsistent(texts: list[str], *, model: str) -> list[list[float]]:
    return [[1.0] if index == 0 else [1.0, 2.0] for index, _ in enumerate(texts)]
