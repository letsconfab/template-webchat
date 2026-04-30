"""Authentication service for JWT token handling and password management."""
import secrets
from datetime import datetime, timedelta
from typing import Optional, Union

from jose import JWTError, jwt
import bcrypt
from passlib.context import CryptContext

# from config import config
from backend.config import config

# Fix for bcrypt 4.x compatibility with passlib 1.7.4
if not hasattr(bcrypt, '__about__'):
    import types
    bcrypt.__about__ = types.SimpleNamespace()
    # Set a dummy version to prevent AttributeError
    bcrypt.__about__.__version__ = "4.2.0"

# Initialize bcrypt backend properly
try:
    import passlib.handlers.bcrypt
    passlib.handlers.bcrypt._load_backend_mixin("bcrypt")
except Exception:
    pass

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _bcrypt_safe_password(password: str) -> str:
    """Convert password to bcrypt-safe format (max 72 bytes)."""
    # Encode to bytes and truncate to 72 bytes, then decode back to string
    # Use errors='ignore' to handle any partial UTF-8 sequences at the truncation point
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        # Try using passlib first
        return pwd_context.verify(
            _bcrypt_safe_password(plain_password),
            hashed_password
        )
    except (ValueError, AttributeError):
        # Fallback to direct bcrypt
        return bcrypt.checkpw(
            _bcrypt_safe_password(plain_password).encode('utf-8'),
            hashed_password.encode('utf-8')
        )


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    try:
        # Try using passlib first
        return pwd_context.hash(
            _bcrypt_safe_password(password)
        )
    except (ValueError, AttributeError):
        # Fallback to direct bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(
            _bcrypt_safe_password(password).encode('utf-8'),
            salt
        ).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(
            token, 
            config.SECRET_KEY, 
            algorithms=[config.ALGORITHM],
            options={"verify_exp": True}  # Explicitly verify expiration
        )
        return payload
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except jwt.JWTError:
        # Invalid token (bad signature, malformed, etc.)
        return None
    except Exception:
        # Any other unexpected error
        return None


def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(length)


def create_password_reset_token(email: str) -> str:
    """Create password reset token."""
    delta = timedelta(hours=1)  # Reset token expires in 1 hour
    now = datetime.utcnow()
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        config.SECRET_KEY,
        algorithm=config.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and return email."""
    try:
        decoded_token = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        return decoded_token["sub"]
    except JWTError:
        return None
