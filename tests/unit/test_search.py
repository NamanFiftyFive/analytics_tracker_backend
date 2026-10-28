import pytest

from app.repositories.search import contains_pattern


@pytest.mark.parametrize(
    ("text", "pattern"),
    [
        ("pune", "%pune%"),
        ("a_b", "%a\\_b%"),
        ("50%", "%50\\%%"),
        ("c:\\temp", "%c:\\\\temp%"),
        (None, None),
    ],
)
def test_contains_pattern(text: str | None, pattern: str | None):
    assert contains_pattern(text) == pattern
