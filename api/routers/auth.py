"""JWT login for deployments that enable authentication."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.db.models import User
from api.errors import APIError
from api.security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


@router.post("/login")
def login(body: LoginRequest, request: Request) -> dict[str, object]:
    """Authenticate an environment-seeded user and issue a JWT."""
    if request.app.state.settings.auth_mode != "jwt":
        raise APIError(404, "not_found", "This sign-in method is not enabled.")
    with request.app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.username == body.username))
        if user is None or not verify_password(body.password, user.password_hash):
            raise APIError(401, "invalid_credentials", "The username or password was not recognized.")
        token = create_access_token(user.username, request.app.state.settings)
        return {"access_token": token, "token_type": "bearer", "expires_in": 2700}
