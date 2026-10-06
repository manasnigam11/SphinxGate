"""
Incident Management API Router — Phase 4.

Endpoints:
  GET  /api/v1/incidents                      — list incidents
  GET  /api/v1/incidents/summary              — aggregate stats
  GET  /api/v1/incidents/{id}                 — get single incident
  POST /api/v1/incidents/{id}/acknowledge     — acknowledge
  POST /api/v1/incidents/{id}/investigate     — mark investigating
  POST /api/v1/incidents/{id}/resolve         — resolve

Security:
  - No secrets, no raw API keys exposed.
  - affected_request_ids are just request IDs (opaque strings).
  - Notes are bounded in length.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.incidents.store import IncidentStore, get_incident_store

logger = logging.getLogger("sphinxgate.incidents")

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


class ResolveRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def _get_store() -> IncidentStore:
    return get_incident_store()


@router.get("")
async def list_incidents(
    status: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    List incidents, newest first.

    Filter by status (open|acknowledged|investigating|resolved) or provider slug.
    """
    store = _get_store()
    incidents = await store.list_all(status=status, provider=provider, limit=limit, offset=offset)
    total = await store.count(status=status)
    return {
        "incidents": [i.to_dict() for i in incidents],
        "count": len(incidents),
        "total": total,
    }


@router.get("/summary")
async def get_incident_summary():
    """Return aggregate incident statistics."""
    store = _get_store()
    all_incidents = await store.list_all(limit=1000)
    open_count = sum(1 for i in all_incidents if i.status.value == "open")
    ack_count = sum(1 for i in all_incidents if i.status.value == "acknowledged")
    inv_count = sum(1 for i in all_incidents if i.status.value == "investigating")
    resolved_count = sum(1 for i in all_incidents if i.status.value == "resolved")
    critical_count = sum(1 for i in all_incidents if i.severity.value == "critical" and i.status.value != "resolved")

    return {
        "total": len(all_incidents),
        "open": open_count,
        "acknowledged": ack_count,
        "investigating": inv_count,
        "resolved": resolved_count,
        "critical_active": critical_count,
        "needs_attention": open_count + ack_count,
    }


@router.get("/{incident_id}")
async def get_incident(incident_id: str = Path(..., max_length=32)):
    """Return a single incident by ID."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    return {"incident": incident.to_dict()}


@router.post("/{incident_id}/acknowledge", status_code=200)
async def acknowledge_incident(incident_id: str = Path(..., max_length=32)):
    """Acknowledge an incident — signals that an operator is aware."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    if incident.status.value == "resolved":
        raise HTTPException(status_code=409, detail="Cannot acknowledge a resolved incident.")
    incident.acknowledge()
    await store.update(incident)
    return {"acknowledged": True, "incident": incident.to_dict()}


@router.post("/{incident_id}/investigate", status_code=200)
async def investigate_incident(incident_id: str = Path(..., max_length=32)):
    """Mark incident as under investigation."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    if incident.status.value == "resolved":
        raise HTTPException(status_code=409, detail="Cannot investigate a resolved incident.")
    incident.investigate()
    await store.update(incident)
    return {"investigating": True, "incident": incident.to_dict()}


@router.post("/{incident_id}/resolve", status_code=200)
async def resolve_incident(
    incident_id: str = Path(..., max_length=32),
    body: ResolveRequest = ResolveRequest(),
):
    """Resolve an incident. An optional note can be provided."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    if incident.status.value == "resolved":
        raise HTTPException(status_code=409, detail="Incident is already resolved.")
    incident.resolve(note=body.note)
    await store.update(incident)
    return {"resolved": True, "incident": incident.to_dict()}


@router.get("/{incident_id}/copilot")
async def get_incident_copilot_analysis(incident_id: str = Path(..., max_length=32)):
    """Fetch AI Copilot analysis for an incident."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    
    # Check if analysis is already cached in metadata
    if "ai_analysis" in incident.metadata:
        return incident.metadata["ai_analysis"]

    from app.incidents.copilot import analyze_incident
    analysis = await analyze_incident(incident)
    
    # Save the analysis in the incident metadata to avoid re-generating
    incident.metadata["ai_analysis"] = analysis
    await store.update(incident)
    
    return analysis


class CopilotAskRequest(BaseModel):
    question: str = Field(..., max_length=1000)

@router.post("/{incident_id}/copilot/ask")
async def ask_incident_copilot(
    incident_id: str = Path(..., max_length=32),
    body: CopilotAskRequest = ...
):
    """Ask a follow-up question to the AI Copilot about an incident."""
    store = _get_store()
    incident = await store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found.")
    
    from app.incidents.copilot import ask_copilot
    
    try:
        answer = await ask_copilot(incident, body.question)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Copilot ask failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Copilot failed to answer the question. It may be degraded.")

