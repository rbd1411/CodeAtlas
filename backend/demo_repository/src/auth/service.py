"""Token validation for the TinyShop demonstration API."""

from dataclasses import dataclass
from datetime import UTC, datetime


class TokenExpiredError(Exception):
    """Raised when an access token is no longer valid."""


class InvalidTokenError(Exception):
    """Raised when a token has invalid claims."""


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    expires_at: datetime
    token_type: str


class AuthService:
    def __init__(self, decoder, *, issuer: str, audience: str):
        self.decoder = decoder
        self.issuer = issuer
        self.audience = audience

    def validate_token(self, token: str) -> TokenClaims:
        """Validate an access token and return normalized claims."""
        payload = self.decoder.decode(
            token,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.audience,
        )
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        if expires_at <= datetime.now(UTC):
            raise TokenExpiredError("Access token has expired")
        if payload.get("token_type") != "access":
            raise InvalidTokenError("Expected an access token")
        return TokenClaims(
            subject=payload["sub"],
            expires_at=expires_at,
            token_type=payload["token_type"],
        )

