from __future__ import annotations


def embed(texts: list[str], *, model: str) -> list[list[float]]:
    if model != "fixture-embedding-v1":
        raise ValueError(f"unsupported fixture model: {model}")
    vectors: list[list[float]] = []
    for text in texts:
        normalized = text.casefold()
        vectors.append(
            [
                float(normalized.count("citation") + normalized.count("audit")),
                float(normalized.count("retrieval") + normalized.count("检索")),
                1.0,
            ]
        )
    return vectors
