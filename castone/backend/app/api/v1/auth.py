"""
Google OAuth Authentication Endpoints

Flow:
  1. Frontend uses Google Sign-In → receives id_token (credential)
  2. Frontend POST /api/v1/auth/google  { credential: "<id_token>" }
  3. Backend verifies id_token with Google's public keys (no network round-trip needed)
  4. Backend upserts User in PostgreSQL
  5. Backend returns JWT + user info + needs_nickname flag
  6. If needs_nickname=True: frontend prompts for nickname
  7. Frontend PATCH /api/v1/auth/me/nickname  { nickname: "..." }

Security:
  - id_token verified against Google's public keys (google-auth library)
  - google_id and email never logged
  - JWT is HS256, expiry 24h
  - Nickname validated: 2-20 chars, alphanumeric/Korean/underscore/hyphen only
  - Unique constraint on nickname enforced at DB level
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from uuid import uuid4

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.models import User
from app.dependencies import get_db
from app.schemas.auth import GoogleTokenRequest, NicknameSetRequest, TokenResponse, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def _build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        nickname=user.nickname,
        email=user.email,
        total_games=user.total_games if user.total_games is not None else 0,
        win_rate=user.win_rate if user.win_rate is not None else 0.0,
        needs_nickname=user.nickname is None,
    )


# ---------------------------------------------------------------------------
# Google Sign-In: verify id_token → upsert user → return JWT
# ---------------------------------------------------------------------------

@router.post("/google", response_model=TokenResponse)
async def google_login(
    body: GoogleTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Verify a Google id_token from the frontend.
    Returns a JWT + user info. If needs_nickname=True, client must call PATCH /me/nickname.
    """
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server",
        )

    # 1. Verify the id_token with Google's public keys
    try:
        idinfo = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            _GOOGLE_CLIENT_ID,
        )
    except ValueError:
        # Covers: expired token, wrong audience, invalid signature
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 토큰 검증에 실패했습니다",
        )

    google_id: str = idinfo["sub"]       # Stable unique Google user ID
    email: str = idinfo.get("email", "")
    email_verified: bool = idinfo.get("email_verified", False)

    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이메일이 인증되지 않은 Google 계정입니다",
        )

    # 2. Upsert user (create if new, update email if changed)
    user = db.query(User).filter(User.google_id == google_id).first()
    if user is None:
        user = User(
            id=uuid4(),
            google_id=google_id,
            email=email or None,
            nickname=None,  # Will be set via PATCH /me/nickname
        )
        db.add(user)
        logger.info("New user registered via Google OAuth (id=%s)", str(user.id))
    else:
        # Keep email in sync (user may have changed their Google email)
        if email and user.email != email:
            user.email = email

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        # Race condition: another request created the same user simultaneously
        user = db.query(User).filter(User.google_id == google_id).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="서버 오류")

    # 3. Issue JWT
    access_token = create_access_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        user=_build_user_response(user),
    )


# ---------------------------------------------------------------------------
# Nickname setup (required after first login)
# ---------------------------------------------------------------------------

@router.patch("/me/nickname", response_model=UserResponse)
async def set_nickname(
    body: NicknameSetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Set or update the authenticated user's nickname.
    Nickname must be unique across all users.
    """
    # Prevent setting to the same value (idempotent-safe)
    if current_user.nickname == body.nickname:
        return _build_user_response(current_user)

    current_user.nickname = body.nickname
    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 닉네임입니다",
        )

    logger.info("User %s updated nickname", str(current_user.id))
    return _build_user_response(current_user)


# ---------------------------------------------------------------------------
# Current user info
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return _build_user_response(current_user)

