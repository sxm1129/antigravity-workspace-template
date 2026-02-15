from __future__ import annotations
"""Metrics API — generation service usage statistics."""

from fastapi import APIRouter

router = APIRouter()

# Service registries for metrics collection
_service_instances: dict = {}


def register_service(service):
    """Register a generation service instance for metrics tracking."""
    _service_instances[service.service_name] = service


def _auto_register_services():
    """Auto-register known service singletons at import time."""
    try:
        from app.services.image_gen import get_image_service
        register_service(get_image_service())
    except Exception:
        pass
    try:
        from app.services.video_gen import get_video_service
        register_service(get_video_service())
    except Exception:
        pass


_auto_register_services()


@router.get("/generation")
async def generation_metrics():
    """Return usage statistics for all registered generation services."""
    metrics = []
    for name, svc in _service_instances.items():
        if hasattr(svc, "get_metrics"):
            metrics.append(svc.get_metrics())
        else:
            metrics.append({"service": name, "status": "no_metrics"})
    return {"services": metrics}

