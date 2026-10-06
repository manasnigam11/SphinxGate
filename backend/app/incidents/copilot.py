import json
import logging
from typing import Any, Dict

from app.incidents.models import Incident
from app.telemetry.store import get_telemetry_store
from app.providers.registry import get_provider

logger = logging.getLogger("sphinxgate.copilot")

async def analyze_incident(incident: Incident) -> Dict[str, Any]:
    """
    Analyzes an incident using the primary LLM provider (e.g. Gemini).
    Returns a structured analysis dictionary.
    """
    store = get_telemetry_store()
    
    # Gather evidence
    affected_requests = []
    for req_id in incident.affected_request_ids[:10]:
        req = await store.get(req_id)
        if req:
            affected_requests.append({
                "provider": req.provider_slug,
                "error_type": req.error_type,
                "status_code": req.status_code,
                "latency_ms": req.latency_ms,
                "circuit_state": req.circuit_state,
                "fallback_used": req.fallback_used
            })

    timeline = [{"event": t.event, "timestamp": t.timestamp} for t in incident.timeline]

    evidence_payload = {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "provider": incident.provider_slug,
        "failure_category": incident.failure_category.value,
        "severity": incident.severity.value,
        "error_count": incident.error_count,
        "circuit_opened": incident.circuit_opened,
        "affected_requests_sample": affected_requests,
        "timeline": timeline,
        "fault_injected": incident.fault_injected
    }

    prompt = f"""
You are the SphinxGate AI Engineering Copilot. Your job is to analyze the following incident evidence and provide a structured root-cause analysis (RCA).

Evidence:
{json.dumps(evidence_payload, indent=2)}

Provide your analysis strictly as a JSON object with the following schema:
{{
  "summary": "A 1-2 sentence summary of what happened.",
  "observedPatterns": ["pattern 1", "pattern 2"],
  "likelyCause": "The most probable root cause based on evidence.",
  "actionsTaken": ["action 1", "action 2"],
  "recommendations": ["engineering recommendation 1", "engineering recommendation 2"],
  "confidence": 85,
  "affectedComponents": ["component1", "component2"]
}}

Do NOT include any markdown formatting like ```json or anything else. Output ONLY valid JSON.
"""

    try:
        # We can use Gemini directly or via registry if available. We'll use Gemini as default.
        gemini = get_provider("gemini")
        if gemini is None:
            raise ValueError("Gemini provider not found")
        
        # We need to construct a message for the provider interface
        request_body = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}]
        }
        
        # We need to use a direct call if we can, but since providers might be rate-limited,
        # we can just use the adapter's raw method if possible, or we just rely on `call`.
        # However, it's easier to use the raw `gemini` adapter `call`.
        from app.config import get_settings
        api_key = get_settings().get_provider_api_key("gemini")
        response = await gemini.call(request_body, api_key=api_key)
        
        if response.get("error"):
            logger.error(f"Copilot LLM error: {response['error']}")
            return _fallback_analysis(incident)
            
        content = response["choices"][0]["message"]["content"]
        
        # Parse JSON
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        analysis = json.loads(content)
        return analysis
        
    except Exception as e:
        logger.error(f"Failed to generate Copilot analysis: {e}", exc_info=True)
        return _fallback_analysis(incident)

def _fallback_analysis(incident: Incident) -> Dict[str, Any]:
    return {
        "summary": f"Incident {incident.incident_id} detected affecting {incident.provider_display_name}.",
        "observedPatterns": [
            f"Failure category: {incident.failure_category.value}",
            f"{incident.error_count} recent errors observed",
            f"Circuit opened: {incident.circuit_opened}"
        ],
        "likelyCause": "Unknown due to AI analysis failure or lack of configured LLM provider.",
        "actionsTaken": [f"Status changed to {incident.status.value}"],
        "recommendations": ["Check provider status page", "Review raw logs"],
        "confidence": 50,
        "affectedComponents": [incident.provider_slug]
    }

async def ask_copilot(incident: Incident, question: str) -> str:
    """
    Asks the Copilot a follow-up question based on the incident context.
    """
    # Context payload
    context_payload = {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "provider": incident.provider_slug,
        "failure_category": incident.failure_category.value,
        "severity": incident.severity.value,
        "error_count": incident.error_count,
        "circuit_opened": incident.circuit_opened,
    }
    if "ai_analysis" in incident.metadata:
        context_payload["previous_analysis"] = incident.metadata["ai_analysis"]

    prompt = f"""
You are the SphinxGate AI Engineering Copilot. A user is asking a follow-up question about an incident you analyzed.

Incident Context:
{json.dumps(context_payload, indent=2)}

User Question:
{question}

Provide a concise, helpful, and technical engineering answer based on the incident context. Do not use markdown code blocks unless writing code. Keep the answer plain text or simple markdown formatting (bullet points, bolding).
"""

    try:
        gemini = get_provider("gemini")
        if gemini is None:
            raise ValueError("Gemini provider not found")
        
        request_body = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}]
        }
        
        from app.config import get_settings
        api_key = get_settings().get_provider_api_key("gemini")
        response = await gemini.call(request_body, api_key=api_key)
        
        if response.get("error"):
            logger.error(f"Copilot LLM error in ask: {response['error']}")
            return "I'm currently running in a degraded state and cannot answer follow-up questions at the moment."
            
        return response["choices"][0]["message"]["content"]
        
    except Exception as e:
        logger.error(f"Failed to answer Copilot question: {e}", exc_info=True)
        return "I'm currently running in a degraded state and cannot answer follow-up questions at the moment."
