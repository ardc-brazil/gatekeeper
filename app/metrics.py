from contextlib import AbstractContextManager
from time import perf_counter

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Shared by every DataMap service (docs/rfcs/005-platform-metrics-and-dashboards.md),
# so one dashboard query spans all of them.
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
SIZE_BUCKETS = tuple(256 * 4**power for power in range(10))

NO_CLIENT = "none"

# The file name comes from whoever uploads, so an extension outside this list
# is "other" rather than a new series.
KNOWN_FORMATS = frozenset(
    {
        "csv", "tsv", "txt", "json", "xml", "xlsx", "xls", "ods", "nc", "nc4",
        "cdf", "h5", "hdf5", "hdf", "grib", "grb", "grb2", "parquet", "zip", "gz",
        "tar", "tgz", "7z", "rar", "pdf", "png", "jpg", "jpeg", "tif", "tiff",
        "shp", "kml", "kmz", "geojson", "dat", "mat", "doc", "docx", "md", "py",
        "ipynb", "r", "sav",
    }
)  # fmt: skip

AUTH_REASONS = frozenset(
    {
        "missing_information",
        "wrong_credentials",
        "not_authorized",
        "expired",
        "invalid_token",
        "user_id_does_not_match_token",
        "token_not_issued_for_this_dataset",
    }
)


def file_format(extension: str | None) -> str:
    normalised = (extension or "").strip().lower().lstrip(".")
    return normalised if normalised in KNOWN_FORMATS else "other"


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status", None) or getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _is_timeout(exc: BaseException | None) -> bool:
    # By name: requests, urllib3 and the standard library each have their own,
    # and urllib3 wraps its timeout in a MaxRetryError's `reason`.
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if "Timeout" in type(exc).__name__:
            return True
        exc = getattr(exc, "reason", None) or exc.__cause__
        if not isinstance(exc, BaseException):
            return False
    return False


def call_outcome(status: int | None, exc: BaseException | None) -> str:
    if status is None and exc is not None:
        status = _status_of(exc)
    if status is not None:
        if status >= 500:
            return "server_error"
        if status >= 400:
            return "client_error"
        return "error" if exc is not None else "success"
    if exc is None:
        return "success"
    return "timeout" if _is_timeout(exc) else "error"


class ExternalCall:
    """Times one call to another service. Set `status` once it answers."""

    def __init__(self, histogram: Histogram, service: str, operation: str) -> None:
        self._histogram = histogram
        self._service = service
        self._operation = operation
        self.status: int | None = None

    def __enter__(self) -> "ExternalCall":
        self._started = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._histogram.labels(
            service=self._service,
            operation=self._operation,
            outcome=call_outcome(self.status, exc),
        ).observe(perf_counter() - self._started)
        return False


class Metrics:
    def __init__(self, registry: CollectorRegistry = None) -> None:
        self.registry = registry if registry is not None else CollectorRegistry()

        self._requests = Counter(
            "datamap_http_requests_total",
            "HTTP requests served",
            ["method", "route", "status", "client"],
            registry=self.registry,
        )
        self._duration = Histogram(
            "datamap_http_request_duration_seconds",
            "Time spent serving a request",
            ["method", "route"],
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self._request_size = Histogram(
            "datamap_http_request_size_bytes",
            "Size of request bodies, when declared",
            ["method", "route"],
            buckets=SIZE_BUCKETS,
            registry=self.registry,
        )
        self._response_size = Histogram(
            "datamap_http_response_size_bytes",
            "Size of response bodies, when declared",
            ["method", "route"],
            buckets=SIZE_BUCKETS,
            registry=self.registry,
        )
        self._in_progress = Gauge(
            "datamap_http_requests_in_progress",
            "Requests being served right now",
            ["method"],
            registry=self.registry,
        )
        self._external = Histogram(
            "datamap_external_request_duration_seconds",
            "Time spent in calls to other services",
            ["service", "operation", "outcome"],
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self._pool_connections = Gauge(
            "datamap_db_pool_connections",
            "Database connections held by this instance's pool",
            ["state"],
            registry=self.registry,
        )
        self._pool_size = Gauge(
            "datamap_db_pool_size",
            "Connections the pool keeps before it overflows",
            registry=self.registry,
        )
        self._dataset_events = Counter(
            "datamap_dataset_events_total",
            "Changes made to datasets and their versions",
            ["action"],
            registry=self.registry,
        )
        self._searches = Counter(
            "datamap_search_total",
            "Dataset searches",
            ["has_text", "has_filters", "empty"],
            registry=self.registry,
        )
        self._download_urls = Counter(
            "datamap_download_urls_issued_total",
            "Presigned download URLs handed out; not completed downloads",
            ["tenancy", "format"],
            registry=self.registry,
        )
        self._download_bytes = Counter(
            "datamap_download_bytes_issued_total",
            "Size of the files behind the download URLs handed out",
            ["tenancy"],
            registry=self.registry,
        )
        self._uploads = Counter(
            "datamap_uploads_completed_total",
            "Files uploaded and recorded against a dataset",
            ["tenancy", "format"],
            registry=self.registry,
        )
        self._upload_bytes = Counter(
            "datamap_upload_bytes_total",
            "Size of the files uploaded",
            ["tenancy"],
            registry=self.registry,
        )
        self._doi_operations = Counter(
            "datamap_doi_operations_total",
            "DOI operations requested by users",
            ["operation", "mode", "outcome"],
            registry=self.registry,
        )
        self._auth_failures = Counter(
            "datamap_auth_failures_total",
            "Requests refused by authentication or authorization",
            ["kind", "reason"],
            registry=self.registry,
        )
        self._tus_hooks = Counter(
            "datamap_tus_hook_total",
            "TUS hooks received",
            ["hook_type", "outcome"],
            registry=self.registry,
        )
        self._snapshots = Counter(
            "datamap_snapshot_publish_total",
            "Dataset snapshots published",
            ["outcome"],
            registry=self.registry,
        )
        self._dataset_access_events = Counter(
            "datamap_dataset_access_events_total",
            "Sharing and embargo decisions recorded in the access audit trail",
            ["event"],
            registry=self.registry,
        )
        self._collocation_pending = Gauge(
            "datamap_collocation_pending",
            "Datasets waiting for their files to be collocated",
            registry=self.registry,
        )
        self._emails = Counter(
            "datamap_emails_total",
            "Email messages by what became of them",
            ["template", "outcome"],
            registry=self.registry,
        )
        self._email_pending = Gauge(
            "datamap_email_pending",
            "Email messages waiting to be sent",
            registry=self.registry,
        )

    def request(
        self,
        method: str,
        route: str,
        status: int,
        seconds: float,
        client: str = NO_CLIENT,
        request_bytes: int | None = None,
        response_bytes: int | None = None,
    ) -> None:
        self._requests.labels(
            method=method, route=route, status=str(status), client=client or NO_CLIENT
        ).inc()
        self._duration.labels(method=method, route=route).observe(seconds)
        if request_bytes is not None:
            self._request_size.labels(method=method, route=route).observe(request_bytes)
        if response_bytes is not None:
            self._response_size.labels(method=method, route=route).observe(
                response_bytes
            )

    def in_progress(self, method: str) -> AbstractContextManager:
        return self._in_progress.labels(method=method).track_inprogress()

    def external_call(self, service: str, operation: str) -> ExternalCall:
        return ExternalCall(self._external, service, operation)

    def external_call_finished(
        self, service: str, operation: str, outcome: str, seconds: float
    ) -> None:
        self._external.labels(
            service=service, operation=operation, outcome=outcome
        ).observe(seconds)

    def watch_pool(self, pool) -> None:
        self._pool_connections.labels(state="checked_out").set_function(pool.checkedout)
        self._pool_connections.labels(state="idle").set_function(pool.checkedin)
        self._pool_connections.labels(state="overflow").set_function(
            lambda: max(pool.overflow(), 0)
        )
        self._pool_size.set_function(pool.size)

    def dataset_event(self, action: str) -> None:
        self._dataset_events.labels(action=action).inc()

    def search(self, has_text: bool, has_filters: bool, found: int) -> None:
        self._searches.labels(
            has_text=_flag(has_text),
            has_filters=_flag(has_filters),
            empty=_flag(not found),
        ).inc()

    def download_url_issued(
        self, tenancy: str | None, extension: str | None, size_bytes: int | None
    ) -> None:
        tenancy = tenancy or "none"
        self._download_urls.labels(tenancy=tenancy, format=file_format(extension)).inc()
        self._download_bytes.labels(tenancy=tenancy).inc(size_bytes or 0)

    def upload_completed(
        self, tenancy: str | None, extension: str | None, size_bytes: int | None
    ) -> None:
        tenancy = tenancy or "none"
        self._uploads.labels(tenancy=tenancy, format=file_format(extension)).inc()
        self._upload_bytes.labels(tenancy=tenancy).inc(size_bytes or 0)

    def doi_operation(self, operation: str, success: bool, mode: str = "") -> None:
        self._doi_operations.labels(
            operation=operation,
            mode=mode or "",
            outcome="success" if success else "error",
        ).inc()

    def auth_failure(self, kind: str, reason: str) -> None:
        self._auth_failures.labels(
            kind=kind, reason=reason if reason in AUTH_REASONS else "other"
        ).inc()

    def tus_hook(self, hook_type: str, status: int) -> None:
        if status >= 500:
            outcome = "error"
        elif status >= 400:
            outcome = "rejected"
        else:
            outcome = "accepted"
        self._tus_hooks.labels(hook_type=hook_type or "unknown", outcome=outcome).inc()

    def snapshot_published(self, success: bool) -> None:
        self._snapshots.labels(outcome="success" if success else "error").inc()

    def dataset_access_event(self, event: str) -> None:
        self._dataset_access_events.labels(event=event).inc()

    def collocation_pending(self, count: int) -> None:
        self._collocation_pending.set(count)

    def email_outcome(self, template: str, outcome: str) -> None:
        self._emails.labels(template=template, outcome=outcome).inc()

    def email_pending(self, count: int) -> None:
        self._email_pending.set(count)

    def render(self) -> bytes:
        return generate_latest(self.registry)


metrics = Metrics(registry=REGISTRY)
