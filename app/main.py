import uvicorn
from fastapi import FastAPI
from app.container import Container
from app import setup

container = Container()

# Create database
db = container.db()
db.create_database()

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

setup.setup_logging()
setup.setup_routes(fastAPIApp)
setup.setup_error_handlers(fastAPIApp)

if __name__ == "__main__":
    uvicorn.run(
        fastAPIApp,
        host="localhost",
        port=9092,
    )
