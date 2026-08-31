"""Typed hosted boundary for the Render + Supabase product.

The existing SQLite pipeline remains the compatibility implementation for local
history.  This module contains the hosted contracts and persistence seam so the
private API and worker never need to expose a local path or browser credential.
Supabase REST/RPC calls are deliberately kept at the persistence boundary; all
application-facing values are validated Pydantic models.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import RLock
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import ConfigDict, Field, SecretStr, field_validator, model_validator

from models import DiscoveryProvider, StrictModel

HostedRunStatus = Literal["queued", "running", "released", "blocked", "failed", "cancelled"]
TerminalRunStatus = Literal["released", "blocked", "failed", "cancelled"]
CredentialName = Literal[
    "mimo_api_key",
    "luna_api_key",
    "luna_base_url",
    "luna_model",
    "exa_api_key",
    "openalex_api_key",
    "serpsearch_api_key",
    "pubmed_api_key",
    "firecrawl_api_key",
]
CREDENTIAL_NAMES: tuple[CredentialName, ...] = (
    "mimo_api_key",
    "luna_api_key",
    "luna_base_url",
    "luna_model",
    "exa_api_key",
    "openalex_api_key",
    "serpsearch_api_key",
    "pubmed_api_key",
    "firecrawl_api_key",
)


class HostedError(Exception):
    """Base error for failures at the hosted boundary."""


class HostedAuthenticationError(HostedError):
    """Raised when a bearer token cannot establish a verified account."""


class HostedOwnershipError(HostedError):
    """Raised when an account cannot access a hosted object."""


class HostedConflictError(HostedError):
    """Raised when an immutable or idempotent hosted operation conflicts."""


class HostedExecutionError(HostedError):
    """Raised when a worker cannot execute a hosted job."""


class HostedModel(StrictModel):
    """Strict base for all hosted contracts."""

    model_config = ConfigDict(extra="forbid")


class AuthenticatedUser(HostedModel):
    """Identity derived from verified Supabase JWT claims only."""

    subject: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    role: str = Field(default="authenticated", min_length=1, max_length=80)


class HostedResearchRequest(HostedModel):
    """User-controlled research choices; run identity is server generated."""

    raw_claim: str = Field(min_length=1, max_length=20_000)
    acknowledged_public: bool = False
    max_tokens: int = Field(default=500_000, ge=1, le=500_000)
    max_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0, le=Decimal("1.00"))
    max_llm_calls: int = Field(default=160, ge=1, le=160)
    support_enabled: bool = True
    challenge_enabled: bool = False
    sources_per_stance_per_round: Literal[5, 10, 15, 20] = 10
    discovery_providers: tuple[DiscoveryProvider, ...] = (
        DiscoveryProvider.SERPSEARCH,
        DiscoveryProvider.EXA,
        DiscoveryProvider.OPENALEX,
    )
    crossref_enabled: bool = False

    @field_validator("raw_claim")
    @classmethod
    def validate_claim(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("claim must not contain leading or trailing whitespace")
        return value

    @field_validator("discovery_providers")
    @classmethod
    def validate_discovery_providers(
        cls,
        value: tuple[DiscoveryProvider, ...],
    ) -> tuple[DiscoveryProvider, ...]:
        if not value:
            raise ValueError("at least one discovery provider must be enabled")
        if len(set(value)) != len(value):
            raise ValueError("discovery providers must not contain duplicates")
        canonical = tuple(provider for provider in DiscoveryProvider if provider in value)
        if value != canonical:
            raise ValueError("discovery providers must use canonical provider order")
        return value

    @model_validator(mode="after")
    def validate_directions(self) -> HostedResearchRequest:
        if not (self.support_enabled or self.challenge_enabled):
            raise ValueError("at least one research direction must be enabled")
        if not self.acknowledged_public:
            raise ValueError("public research acknowledgement is required")
        return self


class HostedRun(HostedModel):
    """Account-owned durable run state safe to return to the browser."""

    run_id: UUID
    owner_id: str = Field(min_length=1, max_length=200)
    raw_claim: str = Field(min_length=1)
    request: HostedResearchRequest
    status: HostedRunStatus
    stage: str = Field(min_length=1, max_length=120)
    progress_percent: int = Field(default=0, ge=0, le=100)
    message: str = Field(min_length=1, max_length=2_000)
    latest_checkpoint: str | None = Field(default=None, max_length=200)
    completed_checkpoints: int = Field(default=0, ge=0)
    total_checkpoints: int = Field(default=5, ge=1)
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @field_validator("created_at", "updated_at", "lease_expires_at", "completed_at")
    @classmethod
    def validate_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("hosted timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_claim_identity(self) -> HostedRun:
        if self.request.raw_claim != self.raw_claim:
            raise ValueError("run claim must match its immutable request claim")
        return self


class HostedRunEvent(HostedModel):
    """Append-only progress event for reconnectable clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    run_id: UUID
    owner_id: str = Field(min_length=1, max_length=200)
    event_type: Literal[
        "queued",
        "started",
        "checkpoint",
        "retry",
        "completed",
        "failed",
        "cancelled",
    ]
    stage: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2_000)
    checkpoint: str | None = Field(default=None, max_length=200)
    created_at: datetime


class HostedArtifact(HostedModel):
    """Immutable persisted output; JSON is text only at this storage boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: UUID
    run_id: UUID
    owner_id: str = Field(min_length=1, max_length=200)
    artifact_type: str = Field(min_length=1, max_length=160)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_json: str = Field(min_length=2)
    created_at: datetime

    @field_validator("payload_json")
    @classmethod
    def validate_json_payload(cls, value: str) -> str:
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("artifact payload must be valid JSON") from exc
        return value


class HostedJobLease(HostedModel):
    """Worker lease returned by an atomic claim operation."""

    run: HostedRun
    worker_id: str = Field(min_length=1, max_length=200)
    lease_expires_at: datetime


class HostedCheckpoint(HostedModel):
    """Typed checkpoint emitted by the worker."""

    stage: str = Field(min_length=1, max_length=120)
    checkpoint: str = Field(min_length=1, max_length=200)
    progress_percent: int = Field(ge=0, le=100)
    message: str = Field(min_length=1, max_length=2_000)


class HostedExecutionResult(HostedModel):
    """Worker result after the existing research pipeline has produced artifacts."""

    status: TerminalRunStatus
    stage: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2_000)
    final_artifact: HostedArtifact | None = None


class HostedHistoryItem(HostedModel):
    """Small history card projection."""

    run_id: UUID
    raw_claim: str = Field(min_length=1)
    status: HostedRunStatus
    stage: str = Field(min_length=1)
    updated_at: datetime
    completed_at: datetime | None = None


class HostedHistory(HostedModel):
    items: tuple[HostedHistoryItem, ...]


class HostedRunDetail(HostedModel):
    run: HostedRun
    events: tuple[HostedRunEvent, ...] = ()
    artifacts: tuple[HostedArtifact, ...] = ()


class ProviderCredentialUpdate(HostedModel):
    """Write-only provider credentials; no response model contains their values."""

    mimo_api_key: SecretStr | None = None
    luna_api_key: SecretStr | None = None
    luna_base_url: str | None = None
    luna_model: str | None = None
    exa_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    serpsearch_api_key: SecretStr | None = None
    pubmed_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None

    @field_validator("luna_base_url")
    @classmethod
    def validate_luna_url(cls, value: str | None) -> str | None:
        if value is not None and "platform.openai.com" in value.casefold():
            raise ValueError("use the API endpoint rather than the OpenAI dashboard URL")
        return value

    def secret_values(self) -> tuple[tuple[CredentialName, str], ...]:
        values: list[tuple[CredentialName, str]] = []
        for name in CREDENTIAL_NAMES:
            value = getattr(self, name)
            if value is None:
                continue
            secret = value.get_secret_value() if isinstance(value, SecretStr) else value
            if secret:
                values.append((name, secret))
        return tuple(values)


class ProviderCredentialMetadata(HostedModel):
    name: CredentialName
    configured: bool
    updated_at: datetime | None = None


class ProviderCredentialResponse(HostedModel):
    credentials: tuple[ProviderCredentialMetadata, ...]


class HostedProviderCredentials(HostedModel):
    """Provider values available only to the private worker execution boundary."""

    mimo_api_key: SecretStr | None = None
    luna_api_key: SecretStr | None = None
    luna_base_url: str | None = None
    luna_model: str | None = None
    exa_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    serpsearch_api_key: SecretStr | None = None
    pubmed_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None

    def as_environment(self) -> dict[str, str]:
        """Build a transient provider environment without persisting or logging secrets."""
        values: dict[str, str] = {}
        for name in CREDENTIAL_NAMES:
            value = getattr(self, name)
            if value is None:
                continue
            values[name.upper()] = (
                value.get_secret_value() if isinstance(value, SecretStr) else value
            )
        return values


class ProviderCredentialClear(HostedModel):
    name: CredentialName


class HostedSettings(HostedModel):
    display_name: str | None = Field(default=None, max_length=120)
    default_max_tokens: int = Field(default=500_000, ge=1, le=500_000)
    default_max_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0, le=Decimal("1.00"))
    default_max_llm_calls: int = Field(default=160, ge=1, le=160)


class LocalHistoryRun(HostedModel):
    """History-only local record used by the migration utility."""

    local_run_id: UUID
    raw_claim: str = Field(min_length=1)
    status: str = Field(min_length=1, max_length=120)
    stage: str = Field(min_length=1, max_length=120)
    updated_at: datetime
    completed_at: datetime | None = None
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete: bool = False
    source_schema_version: int = Field(ge=1)


class MigrationBundle(HostedModel):
    """Read-only, fingerprinted local history transfer payload."""

    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_schema_version: int = Field(ge=1)
    created_at: datetime
    runs: tuple[LocalHistoryRun, ...]


class MigrationResult(HostedModel):
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    imported: int = Field(ge=0)
    already_imported: int = Field(ge=0)
    collisions: tuple[UUID, ...] = ()
    history_only: int = Field(ge=0)


class HostedRepository(Protocol):
    """Persistence operations consumed by the API and worker."""

    def create_run(self, owner_id: str, request: HostedResearchRequest) -> HostedRun: ...

    def get_run(self, owner_id: str, run_id: UUID) -> HostedRun: ...

    def list_history(self, owner_id: str, limit: int) -> HostedHistory: ...

    def get_detail(self, owner_id: str, run_id: UUID) -> HostedRunDetail: ...

    def cancel_run(self, owner_id: str, run_id: UUID) -> HostedRun: ...

    def claim_job(self, worker_id: str, lease_seconds: int) -> HostedJobLease | None: ...

    def heartbeat(self, lease: HostedJobLease, checkpoint: HostedCheckpoint) -> HostedRun: ...

    def complete_job(self, lease: HostedJobLease, result: HostedExecutionResult) -> HostedRun: ...

    def fail_job(self, lease: HostedJobLease, message: str, retryable: bool) -> HostedRun: ...

    def add_artifact(self, artifact: HostedArtifact) -> HostedArtifact: ...

    def credential_metadata(self, owner_id: str) -> ProviderCredentialResponse: ...

    def provider_credentials(self, owner_id: str) -> HostedProviderCredentials: ...

    def save_credentials(
        self,
        owner_id: str,
        update: ProviderCredentialUpdate,
    ) -> ProviderCredentialResponse: ...

    def clear_credential(
        self,
        owner_id: str,
        name: CredentialName,
    ) -> ProviderCredentialResponse: ...

    def get_settings(self, owner_id: str) -> HostedSettings: ...

    def save_settings(self, owner_id: str, settings: HostedSettings) -> HostedSettings: ...

    def import_history(self, owner_id: str, bundle: MigrationBundle) -> MigrationResult: ...


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class SupabaseJWTVerifier:
    """Verify Supabase HS256 access tokens without trusting browser claims."""

    def __init__(
        self,
        secret: str,
        *,
        issuer: str | None = None,
        audience: str | None = "authenticated",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not secret:
            raise ValueError("SUPABASE_JWT_SECRET is required")
        self._secret = secret.encode("utf-8")
        self._issuer = issuer.rstrip("/") if issuer else None
        self._audience = audience
        self._clock = clock

    def verify(self, token: str) -> AuthenticatedUser:
        """Verify signature and time/issuer claims, then return a minimal identity."""
        parts = token.split(".")
        if len(parts) != 3:
            raise HostedAuthenticationError("invalid access token")
        encoded_header, encoded_payload, encoded_signature = parts
        try:
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
            signature = _b64url_decode(encoded_signature)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HostedAuthenticationError("invalid access token") from exc
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            raise HostedAuthenticationError("unsupported access token")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise HostedAuthenticationError("invalid access token")
        if not isinstance(payload, dict):
            raise HostedAuthenticationError("invalid access token")
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise HostedAuthenticationError("access token has no account subject")
        now = self._clock().timestamp()
        expires_at = payload.get("exp")
        not_before = payload.get("nbf")
        if not isinstance(expires_at, (int, float)) or expires_at <= now:
            raise HostedAuthenticationError("access token has expired")
        if isinstance(not_before, (int, float)) and not_before > now + 10:
            raise HostedAuthenticationError("access token is not active")
        if self._issuer is not None and payload.get("iss") != self._issuer:
            raise HostedAuthenticationError("access token issuer is invalid")
        if self._audience is not None:
            audience = payload.get("aud")
            audiences = audience if isinstance(audience, list) else [audience]
            if self._audience not in audiences:
                raise HostedAuthenticationError("access token audience is invalid")
        email = payload.get("email")
        role = payload.get("role", "authenticated")
        if role != "authenticated":
            raise HostedAuthenticationError("access token role is invalid")
        return AuthenticatedUser(
            subject=subject,
            email=email if isinstance(email, str) else None,
            role=role if isinstance(role, str) else "authenticated",
        )


def token_for_tests(
    subject: str,
    secret: str,
    *,
    email: str | None = None,
    issuer: str | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Create a short-lived HS256 token for boundary tests."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, object] = {
        "sub": subject,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": (expires_at or (utc_now() + timedelta(minutes=5))).timestamp(),
    }
    if email is not None:
        payload["email"] = email
    if issuer is not None:
        payload["iss"] = issuer
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"


def fingerprint_json(value: HostedModel) -> str:
    """Fingerprint a canonical hosted model representation."""
    canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hosted_run_from_row(row: Mapping[str, object]) -> HostedRun:
    """Decode a Supabase row whose request is stored as request_json."""
    values = dict(row)
    if "run_id" not in values and "id" in values:
        values["run_id"] = values.pop("id")
    if "request" not in values:
        request_json = values.get("request_json")
        if isinstance(request_json, str):
            values["request"] = json.loads(request_json)
        elif isinstance(request_json, Mapping):
            values["request"] = dict(request_json)
    values.pop("request_json", None)
    values.pop("lease_owner", None)
    return HostedRun.model_validate(values)


def hosted_artifact_from_row(row: Mapping[str, object]) -> HostedArtifact:
    """Decode a Supabase JSONB payload into the string form used by the API contract."""
    values = dict(row)
    payload = values.get("payload_json")
    if not isinstance(payload, str):
        values["payload_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return HostedArtifact.model_validate(values)


class InMemoryHostedRepository:
    """Deterministic repository for tests and local hosted-boundary development."""

    def __init__(self, *, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = RLock()
        self._runs: dict[UUID, HostedRun] = {}
        self._events: dict[UUID, list[HostedRunEvent]] = {}
        self._artifacts: dict[UUID, list[HostedArtifact]] = {}
        self._credentials: dict[str, dict[CredentialName, tuple[str, datetime]]] = {}
        self._settings: dict[str, HostedSettings] = {}
        self._imports: dict[tuple[str, str], MigrationResult] = {}
        self._historical: dict[tuple[str, UUID], str] = {}
        self._leases: dict[UUID, str] = {}

    def _owned_run(self, owner_id: str, run_id: UUID) -> HostedRun:
        run = self._runs.get(run_id)
        if run is None or run.owner_id != owner_id:
            raise HostedOwnershipError("research run not found")
        return run

    def _replace_run(self, run: HostedRun, **changes: object) -> HostedRun:
        updated = run.model_copy(update={"updated_at": self._now(), **changes})
        self._runs[run.run_id] = updated
        return updated

    def _event(
        self,
        run: HostedRun,
        event_type: Literal[
            "queued",
            "started",
            "checkpoint",
            "retry",
            "completed",
            "failed",
            "cancelled",
        ],
        message: str,
        *,
        checkpoint: str | None = None,
    ) -> HostedRunEvent:
        event = HostedRunEvent(
            event_id=uuid4(),
            run_id=run.run_id,
            owner_id=run.owner_id,
            event_type=event_type,
            stage=run.stage,
            message=message,
            checkpoint=checkpoint,
            created_at=self._now(),
        )
        self._events.setdefault(run.run_id, []).append(event)
        return event

    def create_run(self, owner_id: str, request: HostedResearchRequest) -> HostedRun:
        with self._lock:
            now = self._now()
            run = HostedRun(
                run_id=uuid4(),
                owner_id=owner_id,
                raw_claim=request.raw_claim,
                request=request,
                status="queued",
                stage="queued",
                message="Research is queued.",
                created_at=now,
                updated_at=now,
            )
            self._runs[run.run_id] = run
            self._events[run.run_id] = []
            self._event(run, "queued", run.message)
            return run

    def get_run(self, owner_id: str, run_id: UUID) -> HostedRun:
        with self._lock:
            return self._owned_run(owner_id, run_id)

    def list_history(self, owner_id: str, limit: int) -> HostedHistory:
        with self._lock:
            runs = sorted(
                (run for run in self._runs.values() if run.owner_id == owner_id),
                key=lambda item: item.updated_at,
                reverse=True,
            )[:limit]
            return HostedHistory(
                items=tuple(
                    HostedHistoryItem(
                        run_id=run.run_id,
                        raw_claim=run.raw_claim,
                        status=run.status,
                        stage=run.stage,
                        updated_at=run.updated_at,
                        completed_at=run.completed_at,
                    )
                    for run in runs
                )
            )

    def get_detail(self, owner_id: str, run_id: UUID) -> HostedRunDetail:
        with self._lock:
            run = self._owned_run(owner_id, run_id)
            return HostedRunDetail(
                run=run,
                events=tuple(self._events.get(run_id, ())),
                artifacts=tuple(self._artifacts.get(run_id, ())),
            )

    def cancel_run(self, owner_id: str, run_id: UUID) -> HostedRun:
        with self._lock:
            run = self._owned_run(owner_id, run_id)
            if run.status in ("released", "blocked", "failed", "cancelled"):
                return run
            cancelled = self._replace_run(
                run,
                status="cancelled",
                stage="cancelled",
                progress_percent=run.progress_percent,
                message="Cancellation requested.",
                lease_expires_at=None,
                completed_at=self._now(),
            )
            self._leases.pop(run_id, None)
            self._event(cancelled, "cancelled", cancelled.message)
            return cancelled

    def claim_job(self, worker_id: str, lease_seconds: int) -> HostedJobLease | None:
        with self._lock:
            now = self._now()
            candidates = sorted(self._runs.values(), key=lambda item: item.created_at)
            for run in candidates:
                expired = run.lease_expires_at is not None and run.lease_expires_at <= now
                if run.status not in ("queued", "running") or (
                    run.status == "running" and not expired
                ):
                    continue
                lease_expires = now + timedelta(seconds=lease_seconds)
                claimed = self._replace_run(
                    run,
                    status="running",
                    stage=run.stage if run.stage != "queued" else "planning",
                    message="Research is running.",
                    attempt=run.attempt + 1,
                    lease_expires_at=lease_expires,
                )
                self._leases[run.run_id] = worker_id
                self._event(claimed, "started", claimed.message)
                return HostedJobLease(
                    run=claimed,
                    worker_id=worker_id,
                    lease_expires_at=lease_expires,
                )
            return None

    def _assert_lease(self, lease: HostedJobLease) -> HostedRun:
        run = self._runs.get(lease.run.run_id)
        if (
            run is None
            or self._leases.get(run.run_id) != lease.worker_id
            or run.status != "running"
        ):
            raise HostedConflictError("worker lease is no longer active")
        if run.lease_expires_at is None or run.lease_expires_at <= self._now():
            raise HostedConflictError("worker lease has expired")
        return run

    def heartbeat(self, lease: HostedJobLease, checkpoint: HostedCheckpoint) -> HostedRun:
        with self._lock:
            run = self._assert_lease(lease)
            updated = self._replace_run(
                run,
                stage=checkpoint.stage,
                progress_percent=checkpoint.progress_percent,
                message=checkpoint.message,
                latest_checkpoint=checkpoint.checkpoint,
                completed_checkpoints=max(run.completed_checkpoints, 1),
                lease_expires_at=self._now() + (lease.lease_expires_at - lease.run.updated_at),
            )
            self._event(updated, "checkpoint", checkpoint.message, checkpoint=checkpoint.checkpoint)
            return updated

    def complete_job(self, lease: HostedJobLease, result: HostedExecutionResult) -> HostedRun:
        with self._lock:
            run = self._assert_lease(lease)
            completed = self._replace_run(
                run,
                status=result.status,
                stage=result.stage,
                progress_percent=100,
                message=result.message,
                lease_expires_at=None,
                completed_at=self._now(),
            )
            if result.final_artifact is not None:
                self.add_artifact(result.final_artifact)
            self._leases.pop(run.run_id, None)
            self._event(
                completed,
                "completed" if result.status in ("released", "blocked") else "failed",
                result.message,
            )
            return completed

    def fail_job(self, lease: HostedJobLease, message: str, retryable: bool) -> HostedRun:
        with self._lock:
            run = self._assert_lease(lease)
            should_retry = retryable and run.attempt < run.max_attempts
            failed = self._replace_run(
                run,
                status="queued" if should_retry else "failed",
                stage="retrying" if should_retry else "failed",
                message=message,
                lease_expires_at=None,
                completed_at=None if should_retry else self._now(),
            )
            self._leases.pop(run.run_id, None)
            self._event(failed, "retry" if should_retry else "failed", message)
            return failed

    def add_artifact(self, artifact: HostedArtifact) -> HostedArtifact:
        with self._lock:
            run = self._runs.get(artifact.run_id)
            if run is None or run.owner_id != artifact.owner_id:
                raise HostedOwnershipError("research run not found")
            existing = self._artifacts.setdefault(artifact.run_id, [])
            if any(item.artifact_id == artifact.artifact_id for item in existing):
                raise HostedConflictError("artifact already exists")
            if any(item.artifact_type == artifact.artifact_type for item in existing):
                raise HostedConflictError("artifact type already exists for run")
            existing.append(artifact)
            return artifact

    def credential_metadata(self, owner_id: str) -> ProviderCredentialResponse:
        with self._lock:
            saved = self._credentials.get(owner_id, {})
            return ProviderCredentialResponse(
                credentials=tuple(
                    ProviderCredentialMetadata(
                        name=name,
                        configured=name in saved,
                        updated_at=saved[name][1] if name in saved else None,
                    )
                    for name in CREDENTIAL_NAMES
                )
            )

    def provider_credentials(self, owner_id: str) -> HostedProviderCredentials:
        with self._lock:
            saved = self._credentials.get(owner_id, {})
            values: dict[str, object] = {}
            for name, value in saved.items():
                if name not in CREDENTIAL_NAMES:
                    continue
                values[name] = (
                    value[0] if name in {"luna_base_url", "luna_model"} else SecretStr(value[0])
                )
            return HostedProviderCredentials(**values)

    def save_credentials(
        self,
        owner_id: str,
        update: ProviderCredentialUpdate,
    ) -> ProviderCredentialResponse:
        with self._lock:
            saved = self._credentials.setdefault(owner_id, {})
            now = self._now()
            for name, value in update.secret_values():
                if not value or len(value) > 10_000:
                    raise ValueError("credential value is invalid")
                saved[name] = (value, now)
            return self.credential_metadata(owner_id)

    def clear_credential(self, owner_id: str, name: CredentialName) -> ProviderCredentialResponse:
        with self._lock:
            self._credentials.setdefault(owner_id, {}).pop(name, None)
            return self.credential_metadata(owner_id)

    def get_settings(self, owner_id: str) -> HostedSettings:
        with self._lock:
            return self._settings.get(owner_id, HostedSettings())

    def save_settings(self, owner_id: str, settings: HostedSettings) -> HostedSettings:
        with self._lock:
            self._settings[owner_id] = settings
            return settings

    def import_history(self, owner_id: str, bundle: MigrationBundle) -> MigrationResult:
        with self._lock:
            key = (owner_id, bundle.source_fingerprint)
            previous = self._imports.get(key)
            if previous is not None:
                return previous.model_copy(
                    update={"imported": 0, "already_imported": len(bundle.runs)}
                )
            imported = 0
            history_only = 0
            collisions: list[UUID] = []
            for run in bundle.runs:
                history_key = (owner_id, run.local_run_id)
                previous_fingerprint = self._historical.get(history_key)
                if previous_fingerprint is not None:
                    if previous_fingerprint != run.fingerprint:
                        collisions.append(run.local_run_id)
                    continue
                self._historical[history_key] = run.fingerprint
                imported += 1
                history_only += int(not run.complete)
            result = MigrationResult(
                source_fingerprint=bundle.source_fingerprint,
                imported=imported,
                already_imported=0,
                collisions=tuple(collisions),
                history_only=history_only,
            )
            self._imports[key] = result
            return result


class SupabaseHostedRepository:
    """Supabase PostgREST/RPC adapter used by the private API and worker."""

    def __init__(
        self,
        base_url: str,
        service_role_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url or not service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: Literal["GET", "POST", "PATCH"],
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        payload: HostedModel | None = None,
        prefer: str | None = None,
    ) -> httpx.Response:
        headers = dict(self._headers)
        if prefer is not None:
            headers["Prefer"] = prefer
        request_payload = _supabase_payload(payload)
        response = self._client.request(
            method,
            f"{self._base_url}{path}",
            params=params,
            headers=headers,
            json=request_payload,
        )
        if response.status_code >= 400:
            raise HostedError(f"hosted persistence request failed ({response.status_code})")
        return response

    def _rpc(self, name: str, payload: HostedModel) -> HostedModel:
        response = self._request("POST", f"/rest/v1/rpc/{name}", payload=payload)
        data = response.json()
        if not isinstance(data, dict):
            raise HostedError("hosted persistence returned an invalid RPC response")
        return HostedRPCResponse.model_validate(data)

    def create_run(self, owner_id: str, request: HostedResearchRequest) -> HostedRun:
        payload = CreateRunRPCRequest(owner_id=owner_id, request=request)
        response = self._request("POST", "/rest/v1/rpc/create_research_run", payload=payload)
        return hosted_run_from_row(response.json())

    def get_run(self, owner_id: str, run_id: UUID) -> HostedRun:
        response = self._request(
            "GET",
            "/rest/v1/research_runs",
            params={"id": f"eq.{run_id}", "owner_id": f"eq.{owner_id}", "select": "*"},
        )
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise HostedOwnershipError("research run not found")
        return hosted_run_from_row(rows[0])

    def list_history(self, owner_id: str, limit: int) -> HostedHistory:
        response = self._request(
            "GET",
            "/rest/v1/research_runs",
            params={
                "owner_id": f"eq.{owner_id}",
                "select": "id,owner_id,raw_claim,status,stage,updated_at,completed_at",
                "order": "updated_at.desc",
                "limit": str(limit),
            },
        )
        rows = response.json()
        if not isinstance(rows, list):
            raise HostedError("hosted persistence returned an invalid history response")
        items = tuple(
            HostedHistoryItem(
                run_id=row["id"],
                raw_claim=row["raw_claim"],
                status=row["status"],
                stage=row["stage"],
                updated_at=row["updated_at"],
                completed_at=row.get("completed_at"),
            )
            for row in rows
            if isinstance(row, dict)
        )
        return HostedHistory(items=items)

    def get_detail(self, owner_id: str, run_id: UUID) -> HostedRunDetail:
        run = self.get_run(owner_id, run_id)
        events_response = self._request(
            "GET",
            "/rest/v1/research_run_events",
            params={
                "run_id": f"eq.{run_id}",
                "owner_id": f"eq.{owner_id}",
                "select": "*",
                "order": "created_at.asc",
            },
        )
        artifact_response = self._request(
            "GET",
            "/rest/v1/research_artifacts",
            params={
                "run_id": f"eq.{run_id}",
                "owner_id": f"eq.{owner_id}",
                "select": "*",
                "order": "created_at.asc",
            },
        )
        event_rows = events_response.json()
        artifact_rows = artifact_response.json()
        return HostedRunDetail(
            run=run,
            events=tuple(HostedRunEvent.model_validate(row) for row in event_rows),
            artifacts=tuple(hosted_artifact_from_row(row) for row in artifact_rows),
        )

    def cancel_run(self, owner_id: str, run_id: UUID) -> HostedRun:
        response = self._request(
            "POST",
            "/rest/v1/rpc/cancel_research_run",
            payload=CancelRunRPCRequest(owner_id=owner_id, run_id=run_id),
        )
        return hosted_run_from_row(response.json())

    def claim_job(self, worker_id: str, lease_seconds: int) -> HostedJobLease | None:
        response = self._request(
            "POST",
            "/rest/v1/rpc/claim_research_job",
            payload=ClaimJobRPCRequest(worker_id=worker_id, lease_seconds=lease_seconds),
        )
        data = response.json()
        if data is None or data == []:
            return None
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise HostedError("hosted persistence returned an invalid job lease")
        return HostedJobLease.model_validate(data)

    def heartbeat(self, lease: HostedJobLease, checkpoint: HostedCheckpoint) -> HostedRun:
        response = self._request(
            "POST",
            "/rest/v1/rpc/heartbeat_research_job",
            payload=HeartbeatRPCRequest(
                run_id=lease.run.run_id,
                worker_id=lease.worker_id,
                checkpoint=checkpoint,
            ),
        )
        return hosted_run_from_row(response.json())

    def complete_job(self, lease: HostedJobLease, result: HostedExecutionResult) -> HostedRun:
        response = self._request(
            "POST",
            "/rest/v1/rpc/complete_research_job",
            payload=CompleteJobRPCRequest(
                run_id=lease.run.run_id,
                worker_id=lease.worker_id,
                result=result,
            ),
        )
        return hosted_run_from_row(response.json())

    def fail_job(self, lease: HostedJobLease, message: str, retryable: bool) -> HostedRun:
        response = self._request(
            "POST",
            "/rest/v1/rpc/fail_research_job",
            payload=FailJobRPCRequest(
                run_id=lease.run.run_id,
                worker_id=lease.worker_id,
                message=message,
                retryable=retryable,
            ),
        )
        return hosted_run_from_row(response.json())

    def add_artifact(self, artifact: HostedArtifact) -> HostedArtifact:
        response = self._request(
            "POST",
            "/rest/v1/research_artifacts",
            payload=artifact,
            prefer="return=representation",
        )
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise HostedError("hosted persistence returned no artifact")
        return hosted_artifact_from_row(rows[0])

    def credential_metadata(self, owner_id: str) -> ProviderCredentialResponse:
        response = self._request(
            "GET",
            "/rest/v1/provider_credential_metadata",
            params={"owner_id": f"eq.{owner_id}", "select": "name,configured,updated_at"},
        )
        rows = response.json()
        return ProviderCredentialResponse(
            credentials=tuple(ProviderCredentialMetadata.model_validate(row) for row in rows)
        )

    def provider_credentials(self, owner_id: str) -> HostedProviderCredentials:
        values: dict[str, object] = {}
        for name in CREDENTIAL_NAMES:
            response = self._request(
                "POST",
                "/rest/v1/rpc/read_provider_secret",
                payload=ReadProviderSecretRPCRequest(owner_id=owner_id, name=name),
            )
            value = response.json()
            if isinstance(value, str) and value:
                values[name] = (
                    value if name in {"luna_base_url", "luna_model"} else SecretStr(value)
                )
            elif value not in (None, "", []):
                raise HostedError("hosted persistence returned an invalid provider secret")
        return HostedProviderCredentials(**values)

    def save_credentials(
        self,
        owner_id: str,
        update: ProviderCredentialUpdate,
    ) -> ProviderCredentialResponse:
        payload = SaveCredentialsRPCRequest(owner_id=owner_id, update=update)
        response = self._request("POST", "/rest/v1/rpc/save_provider_credentials", payload=payload)
        rows = response.json()
        if not isinstance(rows, list):
            rows = [rows]
        return ProviderCredentialResponse(
            credentials=tuple(ProviderCredentialMetadata.model_validate(row) for row in rows)
        )

    def clear_credential(self, owner_id: str, name: CredentialName) -> ProviderCredentialResponse:
        response = self._request(
            "POST",
            "/rest/v1/rpc/clear_provider_credential",
            payload=ClearCredentialRPCRequest(owner_id=owner_id, name=name),
        )
        rows = response.json()
        if not isinstance(rows, list):
            rows = [rows]
        return ProviderCredentialResponse(
            credentials=tuple(ProviderCredentialMetadata.model_validate(row) for row in rows)
        )

    def get_settings(self, owner_id: str) -> HostedSettings:
        response = self._request(
            "GET",
            "/rest/v1/user_settings",
            params={
                "owner_id": f"eq.{owner_id}",
                "select": (
                    "display_name,default_max_tokens,default_max_cost_usd,default_max_llm_calls"
                ),
            },
        )
        rows = response.json()
        return HostedSettings.model_validate(rows[0]) if rows else HostedSettings()

    def save_settings(self, owner_id: str, settings: HostedSettings) -> HostedSettings:
        response = self._request(
            "POST",
            "/rest/v1/rpc/save_user_settings",
            payload=SaveSettingsRPCRequest(owner_id=owner_id, settings=settings),
        )
        return HostedSettings.model_validate(response.json())

    def import_history(self, owner_id: str, bundle: MigrationBundle) -> MigrationResult:
        response = self._request(
            "POST",
            "/rest/v1/rpc/import_local_history",
            payload=ImportHistoryRPCRequest(owner_id=owner_id, bundle=bundle),
        )
        return MigrationResult.model_validate(response.json())


class CreateRunRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    request: HostedResearchRequest


class CancelRunRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    run_id: UUID


class ClaimJobRPCRequest(HostedModel):
    worker_id: str = Field(min_length=1, max_length=200)
    lease_seconds: int = Field(ge=30, le=3_600)


class HeartbeatRPCRequest(HostedModel):
    run_id: UUID
    worker_id: str = Field(min_length=1, max_length=200)
    checkpoint: HostedCheckpoint


class CompleteJobRPCRequest(HostedModel):
    run_id: UUID
    worker_id: str = Field(min_length=1, max_length=200)
    result: HostedExecutionResult


class FailJobRPCRequest(HostedModel):
    run_id: UUID
    worker_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2_000)
    retryable: bool


class SaveCredentialsRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    update: ProviderCredentialUpdate


class ClearCredentialRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    name: CredentialName


class SaveSettingsRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    settings: HostedSettings


class ImportHistoryRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    bundle: MigrationBundle


class ReadProviderSecretRPCRequest(HostedModel):
    owner_id: str = Field(min_length=1, max_length=200)
    name: CredentialName


class HostedRPCResponse(HostedModel):
    value: str | None = None


def _supabase_payload(payload: HostedModel | None) -> object | None:
    """Map typed RPC envelopes to PostgREST argument names at the wire boundary."""
    if payload is None:
        return None
    if isinstance(payload, CreateRunRPCRequest):
        return {
            "p_owner_id": payload.owner_id,
            "p_request": payload.request.model_dump(mode="json"),
        }
    if isinstance(payload, CancelRunRPCRequest):
        return {"p_owner_id": payload.owner_id, "p_run_id": str(payload.run_id)}
    if isinstance(payload, ClaimJobRPCRequest):
        return {"p_worker_id": payload.worker_id, "p_lease_seconds": payload.lease_seconds}
    if isinstance(payload, HeartbeatRPCRequest):
        return {
            "p_run_id": str(payload.run_id),
            "p_worker_id": payload.worker_id,
            "p_checkpoint": payload.checkpoint.model_dump(mode="json"),
        }
    if isinstance(payload, CompleteJobRPCRequest):
        return {
            "p_run_id": str(payload.run_id),
            "p_worker_id": payload.worker_id,
            "p_result": payload.result.model_dump(mode="json"),
        }
    if isinstance(payload, FailJobRPCRequest):
        return {
            "p_run_id": str(payload.run_id),
            "p_worker_id": payload.worker_id,
            "p_message": payload.message,
            "p_retryable": payload.retryable,
        }
    if isinstance(payload, SaveCredentialsRPCRequest):
        return {
            "p_owner_id": payload.owner_id,
            "p_credentials": {name: value for name, value in payload.update.secret_values()},
        }
    if isinstance(payload, ReadProviderSecretRPCRequest):
        return {"p_owner_id": payload.owner_id, "p_name": payload.name}
    if isinstance(payload, ClearCredentialRPCRequest):
        return {"p_owner_id": payload.owner_id, "p_name": payload.name}
    if isinstance(payload, SaveSettingsRPCRequest):
        return {
            "p_owner_id": payload.owner_id,
            "p_settings": payload.settings.model_dump(mode="json"),
        }
    if isinstance(payload, ImportHistoryRPCRequest):
        return {
            "p_owner_id": payload.owner_id,
            "p_bundle": payload.bundle.model_dump(mode="json"),
        }
    if isinstance(payload, HostedArtifact):
        values = payload.model_dump(mode="json")
        values["payload_json"] = json.loads(payload.payload_json)
        return values
    return payload.model_dump(mode="json")


class HostedPipelineExecutor(Protocol):
    """Adapter for running the canonical pipeline from a durable hosted job."""

    def execute(
        self,
        lease: HostedJobLease,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> HostedExecutionResult: ...


class UnavailableHostedExecutor:
    """Safe default until a deployment supplies the hosted pipeline adapter."""

    def execute(
        self,
        lease: HostedJobLease,
        heartbeat: Callable[[HostedCheckpoint], HostedRun],
    ) -> HostedExecutionResult:
        raise HostedExecutionError(
            "the hosted pipeline executor is not configured; no local database fallback "
            "is available"
        )


class HostedJobRunner:
    """Lease-based worker loop with bounded retries and cancellation-safe failure."""

    def __init__(
        self,
        repository: HostedRepository,
        executor: HostedPipelineExecutor,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 300,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.worker_id = worker_id or f"worker-{secrets.token_hex(8)}"
        self.lease_seconds = lease_seconds

    def run_once(self) -> HostedRun | None:
        """Claim and execute one job, returning its terminal/retry state."""
        lease = self.repository.claim_job(self.worker_id, self.lease_seconds)
        if lease is None:
            return None
        try:
            result = self.executor.execute(
                lease,
                lambda checkpoint: self.repository.heartbeat(lease, checkpoint),
            )
        except HostedConflictError:
            return self.repository.get_run(lease.run.owner_id, lease.run.run_id)
        except HostedExecutionError as exc:
            try:
                return self.repository.fail_job(lease, str(exc), retryable=False)
            except HostedConflictError:
                return self.repository.get_run(lease.run.owner_id, lease.run.run_id)
        except Exception:
            try:
                return self.repository.fail_job(
                    lease,
                    "Hosted research execution failed.",
                    retryable=True,
                )
            except HostedConflictError:
                return self.repository.get_run(lease.run.owner_id, lease.run.run_id)
        try:
            return self.repository.complete_job(lease, result)
        except HostedConflictError:
            return self.repository.get_run(lease.run.owner_id, lease.run.run_id)

    def drain(self, *, max_jobs: int = 1) -> tuple[HostedRun, ...]:
        """Process at most max_jobs and stop when the queue is empty."""
        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")
        results: list[HostedRun] = []
        for _ in range(max_jobs):
            result = self.run_once()
            if result is None:
                break
            results.append(result)
        return tuple(results)


def build_repository_from_environment(
    environ: Mapping[str, str] | None = None,
) -> HostedRepository:
    """Build Supabase persistence when configured, otherwise an explicit memory adapter."""
    values = os.environ if environ is None else environ
    url = values.get("SUPABASE_URL", "")
    service_key = values.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if url and service_key:
        return SupabaseHostedRepository(url, service_key)
    return InMemoryHostedRepository()


def redact_secret_text(value: str) -> str:
    """Return a non-reversible diagnostic marker without exposing secret material."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"secret:{digest}"


def canonical_migration_fingerprint(runs: Iterable[LocalHistoryRun], schema_version: int) -> str:
    """Fingerprint local history metadata without copying mutable local artifacts."""
    payload = {
        "schema_version": schema_version,
        "runs": [
            run.model_dump(mode="json")
            for run in sorted(runs, key=lambda item: str(item.local_run_id))
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
