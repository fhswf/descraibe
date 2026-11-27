import time

import pytest
from joserfc import jwt
from joserfc.errors import ExpiredTokenError, InvalidClaimError, MissingClaimError
from joserfc.jwk import OctKey

from backend import app as app_module


@pytest.fixture
def oidc_key(monkeypatch):
    key = OctKey.import_key("test-secret-key")
    monkeypatch.setattr(app_module, "_oidc_jwks", lambda: key)
    monkeypatch.setattr(app_module, "_OIDC_ISSUER_URL", "https://issuer.example")
    monkeypatch.setattr(app_module, "_OIDC_CLIENT_ID", "client-id")
    return key


def make_token(key, **overrides):
    claims = {
        "iss": "https://issuer.example",
        "aud": "client-id",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "sub": "user-123",
        "name": "Test User",
    }
    claims.update(overrides)
    return jwt.encode({"alg": "HS256"}, claims, key)


def test_validate_id_token_returns_verified_user(oidc_key):
    user = app_module._validate_id_token(make_token(oidc_key))

    assert user == {
        "sub": "user-123",
        "iss": "https://issuer.example",
        "name": "Test User",
        "email": None,
        "preferred_username": None,
        "picture": None,
    }


@pytest.mark.parametrize(
    ("claims", "error"),
    [
        ({"iss": "https://other.example"}, InvalidClaimError),
        ({"aud": "other-client"}, InvalidClaimError),
        ({"sub": None}, MissingClaimError),
        ({"exp": int(time.time()) - 120}, ExpiredTokenError),
    ],
)
def test_validate_id_token_rejects_invalid_claims(oidc_key, claims, error):
    with pytest.raises(error):
        app_module._validate_id_token(make_token(oidc_key, **claims))
