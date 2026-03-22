from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
import os

# Secret key for JWT signing.
# In production, set SECRET_KEY env var. In local dev, a fallback is used.
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    import warnings
    _secret_key = "dev-only-insecure-key-set-SECRET_KEY-in-production"
    warnings.warn(
        "SECRET_KEY env var not set. Using insecure default — DO NOT use in production.",
        stacklevel=2,
    )
SECRET_KEY = _secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.JWTError:
        return None
