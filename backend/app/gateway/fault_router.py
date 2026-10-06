"""
Fault Injection API Router — Phase 4.

Endpoints:
  GET    /api/v1/faults/status  — check if fault injection is enabled
  GET    /api/v1/faults          — list all faults
  GET    /api/v1/faults/active   — list effective faults only
  POST   /api/v1/faults          — create a new fault
  GET    /api/v1/faults/{id}     — get a fault by ID
  DELETE /api/v1/faults/{id}     — disable a fault
  DELETE /api/v1/faults           — clear all faults

Security:
  - Every mutation endpoint checks is_fault_injection_enabled() first.
  - When disabled, mutation endpoints return 403 Forbidden.
  - FaultType is validated against the enum — no arbitrary values accepted.
  - provider_slug is validated against the registered provider list.
  - No arbitrary code execution, no arbitrary URLs, no secrets.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator

from app.fault_injection.models import FaultConfig, FaultType, MAX_LATENCY_MS, MAX_DURATION_S
from app.fault_injection.store import FaultStore, get_fault_store, is_fault_injection_enabled
from app.providers.registry import list_providers

logger = logging.getLogger("sphinxgate.fault_injection")

router = APIRouter(prefix="/api/v1/faults", tags=["fault-injection"])


# ── Request/Response models ────────────────────────────────────────────────────

class CreateFaultRequest(BaseModel):
    provider_slug: str = Field(..., description="Target provider slug")
    fault_type: str = Field(..., description="Fault type (see /api/v1/faults/status for valid types)")
    latency_ms: int = Field(default=0, ge=0, le=MAX_LATENCY_MS,
                            description="Artificial latency in ms (only for LATENCY type)")
    duration_seconds: int = Field(default=0, ge=0, le=MAX_DURATION_S,
                                  description="Duration in seconds (0 = manual clear)")
    note: str = Field(default="", max_length=500, description="Operator note")
    created_by: str = Field(default="operator", max_length=100)

    @field_validator("fault_type")
    @classmethod
    def validate_fault_type(cls, v: str) -> str:
        valid = {ft.value for ft in FaultType}
        if v not in valid:
            raise ValueError(f"Invalid fault_type '{v}'. Valid: {sorted(valid)}")
        return v

    @field_validator("provider_slug")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if not v or len(v) > 64:
            raise ValueError("Invalid provider_slug")
        # Strip to alphanumeric + underscore/hyphen only — prevent injection.
        import re
        if not re.match(r"^[a-z0-9_\-]+$", v):
            raise ValueError("provider_slug must be lowercase alphanumeric with _ or -")
        return v

    @field_validator("created_by")
    @classmethod
    def sanitize_created_by(cls, v: str) -> str:
        import re
        # Allow safe printable characters only.
        return re.sub(r"[^\w\s\-]", "", v)[:100]



def _guard() -> None:
    """Raise 403 if fault injection is not enabled."""
    if not is_fault_injection_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Fault injection is disabled. "
                "Set FAULT_INJECTION_ENABLED=true to enable it. "
                "This feature is for development/demo environments only."
            ),
        )


def _get_store() -> FaultStore:
    return get_fault_store()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_fault_injection_status():
    """
    Return the current fault injection status and supported fault types.
    This endpoint is always available (no guard) so the frontend can check
    whether fault injection is enabled.
    """
    from app.fault_injection.models import FAULT_TYPE_LABELS
    return {
        "enabled": is_fault_injection_enabled(),
        "supported_fault_types": [
            {"value": ft.value, "label": FAULT_TYPE_LABELS[ft]}
            for ft in FaultType
        ],
        "max_latency_ms": MAX_LATENCY_MS,
        "max_duration_seconds": MAX_DURATION_S,
        "registered_providers": list_providers(),
    }


@router.get("")
async def list_faults(active_only: bool = Query(default=False)):
    """Return all fault configurations (or only active ones)."""
    store = _get_store()
    if active_only:
        faults = await store.list_active()
    else:
        faults = await store.list_all()
    return {
        "enabled": is_fault_injection_enabled(),
        "faults": [f.to_dict() for f in faults],
        "count": len(faults),
    }


@router.get("/active")
async def list_active_faults():
    """Return only currently-effective faults."""
    store = _get_store()
    faults = await store.list_active()
    return {
        "enabled": is_fault_injection_enabled(),
        "active_faults": [f.to_dict() for f in faults],
        "count": len(faults),
    }


@router.post("", status_code=201)
async def create_fault(req: CreateFaultRequest):
    """
    Create and activate a new fault.

    Returns 403 if fault injection is not enabled.
    Returns 400 if provider_slug is not registered.
    """
    _guard()

    # Validate provider exists.
    registered = list_providers()
    if req.provider_slug not in registered:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{req.provider_slug}'. Registered: {registered}",
        )

    fault = FaultConfig(
        provider_slug=req.provider_slug,
        fault_type=FaultType(req.fault_type),
        latency_ms=req.latency_ms,
        duration_seconds=req.duration_seconds,
        note=req.note,
        created_by=req.created_by,
    )

    store = _get_store()
    await store.add(fault)

    logger.warning(
        "FAULT CREATED via API: fault_id=%s provider=%s type=%s",
        fault.fault_id, fault.provider_slug, fault.fault_type.value,
    )

    return {
        "created": True,
        "fault": fault.to_dict(),
        "warning": (
            "Fault injection is now ACTIVE for provider "
            f"'{fault.provider_slug}'. "
            "All requests to this provider will simulate "
            f"'{fault.fault_type.value}' until disabled."
        ),
    }


@router.get("/{fault_id}")
async def get_fault(fault_id: str = Path(..., max_length=64)):
    """Return a single fault by ID."""
    store = _get_store()
    fault = await store.get(fault_id)
    if fault is None:
        raise HTTPException(status_code=404, detail=f"Fault '{fault_id}' not found.")
    return {"fault": fault.to_dict()}


@router.delete("/{fault_id}")
async def disable_fault(fault_id: str = Path(..., max_length=64)):
    """Disable a specific fault (keeps it in the audit log)."""
    _guard()
    store = _get_store()
    found = await store.disable(fault_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Fault '{fault_id}' not found.")
    fault = await store.get(fault_id)
    return {
        "disabled": True,
        "fault": fault.to_dict() if fault else None,
    }


@router.delete("")
async def clear_all_faults():
    """Deactivate all active faults."""
    _guard()
    store = _get_store()
    count = await store.clear_all()
    return {
        "cleared": True,
        "faults_deactivated": count,
    }
