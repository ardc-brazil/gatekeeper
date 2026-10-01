import unittest

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app import setup
from app.controller.interceptor.authentication import authenticate
from app.controller.interceptor.authorization import authorize


class TestEmailRoutes(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        setup.setup_routes(app)
        self.routes = {
            (route.path, method): route
            for route in app.routes
            if isinstance(route, APIRoute)
            for method in route.methods
        }

    def guards(self, path: str, method: str) -> set:
        return {
            dependency.call
            for dependency in self.routes[(path, method)].dependant.dependencies
        }

    def test_the_archivist_dispatch_route_takes_client_credentials_only(self):
        guards = self.guards("/v1/internal/notifications/dispatch", "POST")

        self.assertIn(authenticate, guards)
        self.assertNotIn(authorize, guards)

    def test_the_email_record_is_behind_casbin(self):
        for key in [
            ("/v1/admin/emails/", "GET"),
            ("/v1/admin/emails/{email_id}", "GET"),
            ("/v1/admin/emails/test", "POST"),
        ]:
            self.assertTrue({authenticate, authorize} <= self.guards(*key), key)
