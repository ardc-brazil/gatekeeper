import uvicorn
from fastapi import FastAPI
from app.config import settings
from app.container import Container
from app.metrics_server import start_metrics_server
from app import setup

container = Container()

# Before anything else, so migrations and startup are logged like everything else.
setup.setup_logging()

# Its own port, published to no host: a Prometheus scrape config cannot send
# this API's headers, so the docker network is the boundary.
start_metrics_server(settings.METRICS_PORT)

# Bring the schema up to head before anything serves a request.
db = container.db()
db.run_migrations()

# Setup casbin auto reload policy
casbin_enforcer = container.casbin_enforcer()
casbin_enforcer.enable_auto_build_role_links(True)
casbin_enforcer.start_auto_load_policy(5)  # reload policy every 5 seconds

fastAPIApp = FastAPI(
    title="Gatekeeper API",
    description="Gatekeeper API is the main backend for DataMap",
    version="0.0.1",
    redirect_slashes=True,
    root_path="/api",
)

fastAPIApp.container = container

setup.setup_middleware(fastAPIApp)
setup.setup_routes(fastAPIApp)
setup.setup_error_handlers(fastAPIApp)

if __name__ == "__main__":
    uvicorn.run(
        fastAPIApp,
        host="localhost",
        port=9092,
    )
