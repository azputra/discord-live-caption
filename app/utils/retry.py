from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.4,
    sleep: Callable[[float], None] = time.sleep,
    on_error: Callable[[Exception, int], None] | None = None,
) -> T:
    last_error: Exception | None = None
    total = max(1, attempts)
    for index in range(total):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            if on_error is not None:
                on_error(exc, index)
            if index + 1 < total:
                sleep(base_delay * (2**index))
    assert last_error is not None
    raise last_error
