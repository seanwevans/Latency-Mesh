"""Utilities for parsing human-friendly duration strings."""

from datetime import timedelta


def parse_duration(expr: str) -> timedelta:
    """Convert a duration expression into a :class:`~datetime.timedelta`.

    The parser accepts numbers with optional units: seconds (``s``), minutes
    (``m``), hours (``h``), or days (``d``). When a unit is omitted the value is
    interpreted as seconds. Whitespace is ignored. For example ``"5m"``
    corresponds to five minutes.

    Parameters
    ----------
    expr:
        Duration expression to parse.

    Returns
    -------
    datetime.timedelta
        A timedelta representing the supplied duration.

    Raises
    ------
    ValueError
        If the expression is empty or cannot be parsed as a floating point
        value with an optional unit suffix.
    """

    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    expr = expr.strip().lower()
    if not expr:
        raise ValueError("Duration expression cannot be empty")
    value = expr[:-1]
    unit = expr[-1]
    if unit not in units:
        value = expr
        unit = "s"
    try:
        amount = float(value)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid duration: {expr}") from exc
    return timedelta(seconds=amount * units[unit])
