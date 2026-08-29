from datetime import UTC, datetime, timedelta

import pytest

from src.auth.service import AuthService, TokenExpiredError


def test_expired_token_is_rejected(decoder):
    decoder.decode.return_value = {
        "sub": "customer-7",
        "exp": (datetime.now(UTC) - timedelta(minutes=1)).timestamp(),
        "token_type": "access",
    }
    with pytest.raises(TokenExpiredError):
        AuthService(decoder, issuer="tinyshop", audience="api").validate_token("expired")

