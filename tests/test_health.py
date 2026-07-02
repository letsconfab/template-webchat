"""Black-box smoke test for application import and health routing."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.main import app


class HealthEndpointTests(unittest.TestCase):
    def test_application_reports_healthy(self) -> None:
        response = TestClient(app).get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})


if __name__ == "__main__":
    unittest.main()
