"""Schemas validados para rotas de autenticação."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class _AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).casefold()


class RegisterRequest(_AuthInput):
    password: SecretStr = Field(min_length=12, max_length=1024)


class LoginRequest(_AuthInput):
    password: SecretStr = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    """Lista explícita de campos públicos; não serializa o modelo ORM inteiro."""

    id: UUID
    email: str
    created_at: datetime


class GenericMessageResponse(BaseModel):
    message: str
