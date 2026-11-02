"""Tests for the public surface of the auth router."""

from __future__ import annotations

import unittest

from backend.routers import auth as auth_router


class AdminCreationRouteTests(unittest.TestCase):
    def test_no_public_route_creates_admins(self) -> None:
        paths = {route.path for route in auth_router.router.routes}
        self.assertNotIn("/api/auth/admin/register", paths)
        self.assertIn("/api/auth/register", paths)
