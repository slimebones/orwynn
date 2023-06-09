"""Common types.
"""
from typing import Any, Callable, TypeVar

Class = TypeVar("Class", bound=type)
DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Any])

Timestamp = float
Delta = float

CashOperator = str
"""
Special string literal starts with dollar sign `$` which holds a special
meaning to the acceptor logic.
"""
