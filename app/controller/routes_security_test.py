"""Every route is authenticated unless listed below.

A router that forgets its guard fails here. A route meant to be public goes in
PUBLIC_ROUTES, so the decision is written down rather than implied by absence.
"""

import unittest

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app import setup
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize, authorize_tus

# Routes that are deliberately reachable without client credentials.
PUBLIC_ROUTES = {
    # Public dataset metadata (RFC 003).
    ("/v1/datasets/{dataset_id}/snapshot", "GET"),
    ("/v1/datasets/{dataset_id}/versions/{version_name}/snapshot", "GET"),
    # Liveness probe.
    ("/v1/health-check/", "GET"),
}

# Routes authenticated by something other than the client key and secret.
ALTERNATIVE_AUTH = {
    # TUSd forwards no client credentials; the signed upload token is the proof.
    ("/v1/tus/hooks", "POST"): authorize_tus,
}

GUARDS = {authenticate, authorize, authorize_tus}


def _guards_of(route: APIRoute) -> set:
    return {
        dependency.call
        for dependency in route.dependant.dependencies
        if dependency.call in GUARDS
    }


class TestRouteSecurity(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        setup.setup_routes(app)
        self.routes = [
            route
            for route in app.routes
            if isinstance(route, APIRoute) and not route.path.startswith("/openapi")
        ]

    def test_there_are_routes_to_check(self):
        self.assertGreater(len(self.routes), 20)

    def test_every_route_is_authenticated_or_listed_as_public(self):
        unguarded = []

        for route in self.routes:
            for method in route.methods:
                key = (route.path, method)

                if key in PUBLIC_ROUTES:
                    continue

                guards = _guards_of(route)

                if key in ALTERNATIVE_AUTH:
                    if ALTERNATIVE_AUTH[key] not in guards:
                        unguarded.append(
                            f"{method} {route.path} (expected its own guard)"
                        )
                    continue

                if authenticate not in guards:
                    unguarded.append(f"{method} {route.path}")

        self.assertEqual(
            unguarded,
            [],
            "These routes accept a request without authentication. Add the guard, "
            "or list them in PUBLIC_ROUTES with the reason:\n  "
            + "\n  ".join(unguarded),
        )

    def test_public_routes_are_still_registered(self):
        # A stale exemption would silently excuse a future route on the same path.
        registered = {
            (route.path, method) for route in self.routes for method in route.methods
        }

        for key in PUBLIC_ROUTES | set(ALTERNATIVE_AUTH):
            self.assertIn(key, registered, f"{key} is exempted but no longer exists")
