"""HTTP-facing models for the Tripletex challenge service."""

from __future__ import annotations

import base64
import binascii
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class AttachmentFile(BaseModel):
    """A base64-encoded attachment sent by the competition platform."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)

    @field_validator("content_base64")
    @classmethod
    def validate_content_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error as exc:
            raise ValueError("content_base64 must be valid base64") from exc
        return value


class TripletexCredentials(BaseModel):
    """Per-request proxy credentials supplied by the challenge platform."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=1)
    session_token: SecretStr

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return normalized

    def basic_auth_username(self) -> str:
        return "0"

    def basic_auth_password(self) -> str:
        return self.session_token.get_secret_value()


class SolveRequest(BaseModel):
    """Official request body for the challenge endpoint."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    files: list[AttachmentFile] = Field(default_factory=list)
    tripletex_credentials: TripletexCredentials

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("prompt must not be blank")
        return normalized


class SolveResponse(BaseModel):
    """Minimal success response expected by the challenge platform."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = "completed"


class HealthResponse(BaseModel):
    """Service health response for local checks."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
