"""Turning a user's search text into a safe ILIKE pattern."""


def contains_pattern(text: str | None) -> str | None:
    """'50%_off' -> '%50\\%\\_off%': matches the text anywhere, with % and _ taken literally.

    In LIKE/ILIKE, % and _ are wildcards, so a raw search for "a_b" would also match "axb".
    Use as `column ILIKE $n`; backslash is Postgres's default LIKE escape character.
    """
    if text is None:
        return None
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
