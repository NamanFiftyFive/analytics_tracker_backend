from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.core.config import settings
from app.core.security import ApiKeyGenerator, PasswordService, TokenService


class TestPasswordService:
    def test_hash_is_not_the_password_and_verifies(self):
        password_hash = PasswordService.hash("Str0ng-pass-word")
        assert password_hash != "Str0ng-pass-word"
        assert PasswordService.verify("Str0ng-pass-word", password_hash)

    def test_wrong_password_fails(self):
        assert not PasswordService.verify("wrong", PasswordService.hash("Str0ng-pass-word"))

    def test_unknown_user_fails(self):
        assert not PasswordService.verify("anything", None)

    def test_broken_hash_fails_instead_of_raising(self):
        assert not PasswordService.verify("anything", "not-an-argon2-hash")


class TestTokenService:
    def test_access_token_round_trip(self):
        user_id = uuid4()
        token, lifetime = TokenService.create_access_token(user_id)
        assert lifetime == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert TokenService.decode_access_token(token) == user_id

    def test_expired_token_is_rejected(self):
        past = datetime.now(UTC) - timedelta(minutes=1)
        token = self._encode({"sub": str(uuid4()), "type": "access", "exp": past})
        assert TokenService.decode_access_token(token) is None

    def test_token_of_another_type_is_rejected(self):
        future = datetime.now(UTC) + timedelta(minutes=5)
        token = self._encode({"sub": str(uuid4()), "type": "refresh", "exp": future})
        assert TokenService.decode_access_token(token) is None

    def test_token_signed_with_another_secret_is_rejected(self):
        future = datetime.now(UTC) + timedelta(minutes=5)
        payload = {"sub": str(uuid4()), "type": "access", "exp": future}
        token = jwt.encode(payload, "some-other-secret-key-of-enough-length", algorithm="HS256")
        assert TokenService.decode_access_token(token) is None

    def test_garbage_is_rejected(self):
        assert TokenService.decode_access_token("not.a.token") is None

    def test_refresh_token_is_stored_as_its_hash(self):
        token, token_hash, expires_at = TokenService.new_refresh_token()
        assert token_hash == TokenService.hash_refresh_token(token)
        assert token_hash != token
        assert expires_at > datetime.now(UTC)

    @staticmethod
    def _encode(payload: dict) -> str:
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class TestApiKeyGenerator:
    def test_key_shape_and_hash(self):
        key, prefix, key_hash = ApiKeyGenerator.generate()
        assert key.startswith("pk_live_")
        assert prefix == key[: ApiKeyGenerator.VISIBLE_CHARS]
        assert key_hash == ApiKeyGenerator.hash(key)

    def test_keys_are_unique(self):
        assert ApiKeyGenerator.generate()[0] != ApiKeyGenerator.generate()[0]
