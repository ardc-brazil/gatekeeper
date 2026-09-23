import logging
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

from prometheus_client import REGISTRY, CollectorRegistry, make_wsgi_app

logger = logging.getLogger("metrics")


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args) -> None:
        pass


class MetricsServer:
    def __init__(self, server, thread) -> None:
        self._server = server
        self._thread = thread

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def shutdown(self) -> None:
        self._server.shutdown()
        # Without this the socket stays bound and a caller hangs instead of
        # being refused.
        self._server.server_close()
        self._thread.join(timeout=5)


def start_metrics_server(
    port: int, registry: CollectorRegistry = None, host: str = "0.0.0.0"
) -> MetricsServer:
    """Serve the registry on its own port, in a daemon thread.

    Published to no host in Compose, so only the docker network reaches it.
    That is the boundary, because a Prometheus scrape config cannot send this
    API's headers.
    """
    # make_wsgi_app defaults to the global registry, but an explicit None
    # overrides that default and serves nothing but a 500.
    app = make_wsgi_app(registry if registry is not None else REGISTRY)
    server = make_server(host, port, app, handler_class=_QuietHandler)
    thread = threading.Thread(target=server.serve_forever, name="metrics", daemon=True)
    thread.start()
    logger.info("metrics server listening", extra={"port": port})
    return MetricsServer(server, thread)
