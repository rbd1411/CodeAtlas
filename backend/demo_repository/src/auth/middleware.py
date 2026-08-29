"""HTTP authentication middleware."""

from .service import AuthService, InvalidTokenError, TokenExpiredError


class AuthMiddleware:
    def __init__(self, app, auth_service: AuthService):
        self.app = app
        self.auth_service = auth_service

    async def __call__(self, request, call_next):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return {"status": 401, "error": "missing_bearer_token"}
        token = header.removeprefix("Bearer ").strip()
        try:
            request.state.claims = self.auth_service.validate_token(token)
        except TokenExpiredError:
            return {"status": 401, "error": "token_expired"}
        except InvalidTokenError:
            return {"status": 401, "error": "invalid_token"}
        return await call_next(request)

