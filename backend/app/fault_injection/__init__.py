"""
Fault Injection subsystem — Phase 4.

This package provides controlled simulation of upstream provider failures
for development/demo/testing purposes.

Public surface:
  from app.fault_injection.store import FaultStore, get_fault_store
  from app.fault_injection.models import FaultConfig, FaultType
  from app.fault_injection.middleware import apply_fault_if_active

Safety guarantee:
  - Fault injection is DISABLED by default (FAULT_INJECTION_ENABLED env var).
  - When disabled, every call to apply_fault_if_active is a no-op.
  - FaultType is a strict enum — no arbitrary exception injection is possible.
"""
