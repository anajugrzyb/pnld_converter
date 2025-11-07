"""Minimal multipart parsing helpers for tests."""

from typing import Dict, Tuple


def parse_options_header(header_value: str) -> Tuple[str, Dict[str, str]]:
    """Return the header value and parameters.

    This simplified implementation only splits the header by ';' and builds a
    dictionary of key=value pairs. It's sufficient for tests that only need the
    function to exist.
    """

    if not header_value:
        return "", {}

    parts = [part.strip() for part in header_value.split(";") if part.strip()]
    value = parts[0] if parts else ""
    params: Dict[str, str] = {}

    for item in parts[1:]:
        if "=" in item:
            key, val = item.split("=", 1)
            params[key.strip().lower()] = val.strip().strip('"')

    return value, params