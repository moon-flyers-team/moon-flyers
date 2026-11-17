"""Validate the deployment security baseline using Compose (no containers started)."""

import json
import os
from pathlib import Path
import subprocess
import unittest


class ContainerSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["docker", "compose", "-f", str(Path(__file__).with_name("compose.yaml")),
             "config", "--format", "json"],
            env={**os.environ, "REVISION": "a" * 40, "HTTP_PORT": "18082"},
            check=True, capture_output=True, text=True,
        )
        cls.services = json.loads(result.stdout)["services"]

    def test_resource_budgets_and_no_swap(self) -> None:
        for name, cpus, memory, pids in (
            ("backend", 1.5, 3 * 1024**3, 128),
            ("frontend", 0.5, 128 * 1024**2, 64),
        ):
            with self.subTest(service=name):
                service = self.services[name]
                self.assertEqual(float(service["cpus"]), cpus)
                # Compose versions serialize byte counts as strings or numbers.
                self.assertEqual(int(service["mem_limit"]), memory)
                self.assertEqual(int(service["memswap_limit"]), memory)
                self.assertEqual(int(service["pids_limit"]), pids)

    def test_only_frontend_is_published_on_loopback(self) -> None:
        self.assertFalse(self.services["backend"].get("ports"))
        ports = self.services["frontend"]["ports"]
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["host_ip"], "127.0.0.1")
        self.assertEqual(ports[0]["target"], 8080)

    def test_unprivileged_container_configuration(self) -> None:
        for name, service in self.services.items():
            with self.subTest(service=name):
                self.assertTrue(service["read_only"])
                self.assertFalse(service.get("privileged", False))
                self.assertNotEqual(service.get("network_mode"), "host")
                self.assertEqual(service["cap_drop"], ["ALL"])
                self.assertIn("no-new-privileges:true", service["security_opt"])
                self.assertFalse(service.get("volumes"))


if __name__ == "__main__":
    unittest.main()
