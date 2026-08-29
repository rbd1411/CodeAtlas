# TinyShop API

TinyShop is the bundled CodeAtlas demonstration repository. It models a small order API with token authentication.

## Request flow

Incoming requests pass through `AuthMiddleware`. The middleware extracts a Bearer token and delegates JWT validation to `AuthService.validate_token`. Authenticated requests can then reach `OrderService.create_order`.

## Authentication rules

- Access tokens must have the `access` token type.
- The JWT decoder validates the signature, issuer, audience, and expiration claim.
- Expired tokens become `TokenExpiredError` and produce HTTP 401.

