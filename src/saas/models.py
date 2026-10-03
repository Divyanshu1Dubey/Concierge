"""Multi-tenant SaaS data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    id: int | None = None
    slug: str
    name: str
    enabled: bool = True
    plan: str = "trial"
    metadata: dict[str, Any] = Field(default_factory=dict)


class User(BaseModel):
    id: int | None = None
    tenant_id: int
    email: str
    display_name: str | None = None
    hashed_password: str | None = None
    role: str = "owner"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Domain(BaseModel):
    id: int | None = None
    tenant_id: int
    domain: str
    verified: bool = False


class ApiKey(BaseModel):
    id: int | None = None
    tenant_id: int
    label: str
    public_key: str
    secret_key_hash: str
    revoked_at: str | None = None
    last_used_at: str | None = None


class Conversation(BaseModel):
    id: int | None = None
    tenant_id: int
    visitor_id: str | None = None
    page_url: str | None = None
    referrer: str | None = None
    user_agent: str | None = None
    status: str = "started"
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    id: int | None = None
    conversation_id: int
    role: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Lead(BaseModel):
    id: int | None = None
    tenant_id: int
    conversation_id: int | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    intent: str | None = None
    service: str | None = None
    urgency: str | None = None
    preferred_date: str | None = None
    preferred_time: str | None = None
    insurance: str | None = None
    financing: str | None = None
    message: str | None = None
    conversation_summary: str | None = None
    source: str | None = None
    page_url: str | None = None
    status: str = "new"
    metadata: dict[str, Any] = Field(default_factory=dict)
