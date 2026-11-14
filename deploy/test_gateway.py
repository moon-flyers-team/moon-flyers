"""Check the dedicated gateway's declarative public routing."""

import json
from pathlib import Path
import unittest


class GatewayConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        source = Path(__file__).with_name("gateway") / "serve.json"
        self.raw = source.read_text()
        self.host = "moon-flyers.tail644248.ts.net"
        self.config = json.loads(self.raw.replace("${TS_CERT_DOMAIN}", self.host))

    def test_only_expected_https_ports_are_exposed(self) -> None:
        self.assertEqual(self.config["TCP"], {"443": {"HTTPS": True}, "8443": {"HTTPS": True}})
        self.assertEqual(set(self.config["Web"]), {f"{self.host}:443", f"{self.host}:8443"})

    def test_production_and_test_have_distinct_loopback_origins(self) -> None:
        for public_port, origin_port in [(443, 18080), (8443, 18081)]:
            self.assertEqual(
                self.config["Web"][f"{self.host}:{public_port}"],
                {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{origin_port}"}}},
            )

    def test_funnel_is_enabled_for_both_routes(self) -> None:
        self.assertEqual(
            self.config["AllowFunnel"],
            {f"{self.host}:443": True, f"{self.host}:8443": True},
        )

    def test_host_is_resolved_by_containerboot_not_hard_coded(self) -> None:
        self.assertEqual(self.raw.count("${TS_CERT_DOMAIN}"), 4)
        self.assertNotIn(self.host, self.raw)


if __name__ == "__main__":
    unittest.main()
