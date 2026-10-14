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


import atexit

def init_tracer(service_name: str = "travel_concierge_service") -> trace.Tracer:
    """Initializes OpenTelemetry TracerProvider and registers processors."""
    global _TRACER_INITIALIZED

    if not _TRACER_INITIALIZED:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
        resource = Resource.create({
            "service.name": service_name,
            "gcp.project_id": project_id or "",
        })
        provider = TracerProvider(resource=resource)

        exporter_type = os.getenv("OTEL_EXPORTER_TYPE", "").lower()
        enable_cloud_trace = os.getenv("ENABLE_CLOUD_TRACE", "").lower() in ("true", "1", "yes")
        use_gcp = enable_cloud_trace or exporter_type in ("gcp", "cloud_trace")

        if use_gcp:
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
                cloud_exporter = CloudTraceSpanExporter(project_id=project_id) if project_id else CloudTraceSpanExporter()
                provider.add_span_processor(BatchSpanProcessor(cloud_exporter, schedule_delay_millis=500))
                logger.info("Configured Google Cloud Trace Span Exporter")
            except Exception as e:
                logger.warning(f"Could not initialize CloudTraceSpanExporter: {e}. Falling back to ConsoleSpanExporter.")
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _TRACER_INITIALIZED = True
        atexit.register(flush_tracer)

    return trace.get_tracer("travel_concierge_a2a_tracer")


def flush_tracer() -> None:
    """Flushes any buffered spans to the exporter."""
    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except (ValueError, Exception) as e:
        pass


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


from opentelemetry.context import attach, detach


def extract_trace_context(carrier: Optional[Dict[str, str]] = None) -> Any:
    """
    Extracts W3C TraceContext from incoming headers/metadata.
    Supports both standard W3C 'traceparent' and Google Cloud Run 'x-cloud-trace-context'.
    """
    if not carrier:
        return extract({})
    headers = dict(carrier)
    lower_headers = {str(k).lower(): str(v) for k, v in headers.items()}
    if "traceparent" not in lower_headers and "x-cloud-trace-context" in lower_headers:
        val = lower_headers["x-cloud-trace-context"]
        parts = val.split(";")[0].split("/")
        trace_id = parts[0].strip()
        span_id_raw = parts[1].strip() if len(parts) > 1 else "0"
        try:
            span_id_hex = format(int(span_id_raw), "016x")
            headers["traceparent"] = f"00-{trace_id.lower()}-{span_id_hex}-01"
        except Exception:
            pass
    return extract(headers)


class TraceContextMiddleware:
    """ASGI middleware ensuring incoming trace context is attached to the request lifecycle."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {
                k.decode("latin1"): v.decode("latin1")
                for k, v in scope.get("headers", [])
            }
            ctx = extract_trace_context(headers)
            token = attach(ctx)
            try:
                await self.app(scope, receive, send)
            finally:
                detach(token)
                flush_tracer()
        else:
            await self.app(scope, receive, send)
