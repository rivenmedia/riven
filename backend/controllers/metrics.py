from fastapi import APIRouter, Response
from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# Initialize OpenTelemetry MeterProvider with PrometheusMetricReader
resource = Resource.create({"service.name": "my-fastapi-service"})
prometheus_exporter = PrometheusMetricReader()
meter_provider = MeterProvider(resource=resource, metric_readers=[prometheus_exporter])
metrics.set_meter_provider(meter_provider)

# Create a meter
meter = metrics.get_meter(__name__)

# Example metric
counter = meter.create_counter(
    name="example_counter",
    description="An example counter",
    unit="1",
)

router = APIRouter()

@router.get("/metrics")
async def get_metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)