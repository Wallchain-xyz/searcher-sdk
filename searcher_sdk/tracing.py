import platform
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from pydantic import BaseModel


class TracingConfig(BaseModel):
    service_name: str
    service_version: str = "unknown"
    service_instance_id: Optional[str] = None

    otlp_exporter_endpoint: Optional[str] = None


def setup_tracing(config: TracingConfig) -> TracerProvider:
    resource = resources.Resource(
        attributes={
            resources.SERVICE_NAME: config.service_name,
            resources.SERVICE_VERSION: config.service_version,
            resources.SERVICE_INSTANCE_ID: config.service_instance_id
            or platform.node(),
        }
    )
    provider = TracerProvider(resource=resource)
    exporter: SpanExporter
    if config.otlp_exporter_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=config.otlp_exporter_endpoint, insecure=True
        )
    else:
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    return provider
