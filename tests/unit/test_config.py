import pytest

from app.core.config import Settings


def make_settings(password: str = "abc123XYZ") -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        POSTGRES_USER="postgres.abcref",
        POSTGRES_PASSWORD=password,
        POSTGRES_DB="postgres",
        POSTGRES_HOST="db.example.com",
        POSTGRES_PORT=5432,
        JWT_SECRET_KEY="test",
    )


def test_database_url_keeps_a_plain_password_unchanged():
    url = make_settings("abc123XYZ").database_url
    assert url == "postgresql://postgres.abcref:abc123XYZ@db.example.com:5432/postgres"


def test_database_url_encodes_special_characters_in_the_password():
    url = make_settings("p@ss:w/rd#1?%").database_url
    assert url == "postgresql://postgres.abcref:p%40ss%3Aw%2Frd%231%3F%25@db.example.com:5432/postgres"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["https://a.com","https://b.com"]', ["https://a.com", "https://b.com"]),  # JSON
        ("https://a.com,https://b.com", ["https://a.com", "https://b.com"]),  # comma list
        (" https://a.com , https://b.com ", ["https://a.com", "https://b.com"]),  # spaces
        ("https://a.com", ["https://a.com"]),  # single origin
        ("[https://a.com,https://b.com]", ["https://a.com", "https://b.com"]),  # shell stripped the quotes
        ("", []),  # empty
        ("[]", []),
    ],
)
def test_cors_origins_from_the_environment(monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]):
    """Environment variables are where hosts like Fly.io put the value (the .env file is not used there)."""
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert make_settings().CORS_ORIGINS == expected
