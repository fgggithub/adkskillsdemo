"""
OpenTelemetry Tracing configuration and W3C context propagation helpers.
"""
import logging
import os
from typing import Dict, Any, Optional

from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger("travel_concierge.telemetry")

_TRACER_INITIALIZED = False


def init_tracer(service_name: str = "travel_concierge_service") -> trace.Tracer:
    """Initializes OpenTelemetry TracerProvider and registers processors."""
    global _TRACER_INITIALIZED

    if not _TRACER_INITIALIZED:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        # In non-production or when specified, use Console exporter
        exporter_type = os.getenv("OTEL_EXPORTER_TYPE", "console").lower()

        if exporter_type == "gcp":
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
                cloud_exporter = CloudTraceSpanExporter()
                provider.add_span_processor(BatchSpanProcessor(cloud_exporter))
                logger.info("Configured Google Cloud Trace Span Exporter")
            except Exception as e:
                logger.warning(f"Could not initialize CloudTraceSpanExporter: {e}. Falling back to ConsoleSpanExporter.")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _TRACER_INITIALIZED = True

    return trace.get_tracer("travel_concierge_a2a_tracer")


def get_tracer(name: str = "travel_concierge_a2a_tracer") -> trace.Tracer:
    """Returns an OpenTelemetry tracer instance."""
    if not _TRACER_INITIALIZED:
        init_tracer()
    return trace.get_tracer(name)


def inject_trace_context(carrier: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Injects current W3C TraceContext into a dictionary for downstream agent propagation."""
    if carrier is None:
        carrier = {}
    inject(carrier)
    return carrier


def extract_trace_context(carrier: Dict[str, str]) -> Any:
    """Extracts W3C TraceContext from incoming headers/metadata."""
    return extract(carrier)
