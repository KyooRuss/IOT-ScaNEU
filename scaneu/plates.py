import re


def normalize_plate(text):
    """'abc 1234' / 'ABC-1234' -> 'ABC1234'. Returns None for empty or unreadable input."""
    if not text:
        return None
    plate = re.sub(r"[^A-Z0-9]", "", text.upper())
    return plate or None


def format_plate(plate):
    """'ABC1234' -> 'ABC 1234' for display, the way plates are printed."""
    match = re.fullmatch(r"([A-Z]+)(\d+)", plate or "")
    return f"{match[1]} {match[2]}" if match else plate
