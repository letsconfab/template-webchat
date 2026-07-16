"""Pydantic schemas for user-related operations."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from backend.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    role: Optional[str] = "user"
    is_active: Optional[bool] = True


class UserCreate(BaseModel):
    """User creation schema."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: Optional[str] = "user"


class AdminCreate(BaseModel):
    """Admin registration schema."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login schema."""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """User update schema."""
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


LastSeenSource = Literal["login", "inferred"]


class UserResponse(BaseModel):
    """User response schema."""
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None
    inferred_last_activity_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN or self.role == "admin"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def last_seen_at(self) -> Optional[datetime]:
        login = self.last_login_at
        inferred = self.inferred_last_activity_at
        if login is None and inferred is None:
            return None
        if login is None:
            return inferred
        if inferred is None:
            return login
        return login if login >= inferred else inferred

    @computed_field  # type: ignore[prop-decorator]
    @property
    def last_seen_source(self) -> Optional[LastSeenSource]:
        login = self.last_login_at
        inferred = self.inferred_last_activity_at
        if login is None and inferred is None:
            return None
        if login is None:
            return "inferred"
        if inferred is None:
            return "login"
        return "login" if login >= inferred else "inferred"


class UserListResponse(BaseModel):
    """Paginated user list envelope."""

    items: list[UserResponse]
    total: int
    skip: int
    limit: int


class Token(BaseModel):
    """Token response schema."""
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Token data schema."""
    user_id: Optional[int] = None
