import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.generate import BuildError, generate


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "dist"
        self.config_path = self.root / "sources.yaml"
        self.config = {
            "sources": [
                {
                    "name": "proxy-domain",
                    "policy": "proxy",
                    "behavior": "domain",
                    "path": "custom/domain/proxy.yaml",
                },
                {
                    "name": "proxy-ip",
                    "policy": "proxy",
                    "behavior": "ipcidr",
                    "path": "custom/ipcidr/proxy.yaml",
                },
                {
                    "name": "direct-domain",
                    "policy": "direct",
                    "behavior": "domain",
                    "path": "custom/domain/direct.yaml",
                },
                {
                    "name": "direct-ip",
                    "policy": "direct",
                    "behavior": "ipcidr",
                    "path": "custom/ipcidr/direct.yaml",
                },
            ],
        }
        self.write_payload(
            "custom/domain/proxy.yaml", ["+.EXAMPLE.COM.", "+.example.com", "exact.example.net"]
        )
        self.write_payload(
            "custom/ipcidr/proxy.yaml", ["203.0.113.0/25", "203.0.113.128/25", "2001:db8::/32"]
        )
        self.write_payload("custom/domain/direct.yaml", ["+.internal.example.com"])
        self.write_payload("custom/ipcidr/direct.yaml", ["203.0.113.64/26"])
        self.save_config()

    def write_payload(self, path, rules):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(yaml.safe_dump({"payload": rules}))

    def save_config(self):
        self.config_path.write_text(yaml.safe_dump(self.config))

    def payload(self, relative):
        return yaml.safe_load((self.output / relative).read_text())["payload"]

    def snapshot(self):
        return {
            path.relative_to(self.output).as_posix(): path.read_bytes()
            for path in self.output.rglob("*")
            if path.is_file()
        }

    def test_dual_exports_preserve_direct_overrides(self):
        report = generate(self.config_path, self.output)
        self.assertEqual(
            self.payload("rule-set/domain/proxy.yaml"), ["+.example.com", "exact.example.net"]
        )
        self.assertEqual(self.payload("rule-set/domain/direct.yaml"), ["+.internal.example.com"])
        self.assertEqual(
            self.payload("rule-set/ipcidr/proxy.yaml"), ["203.0.113.0/24", "2001:db8::/32"]
        )
        self.assertEqual(self.payload("rule-set/ipcidr/direct.yaml"), ["203.0.113.64/26"])
        self.assertEqual(
            (self.output / "glinet/proxy.txt").read_text(),
            "exact.example.net\nexample.com\n203.0.113.0/24\n",
        )
        self.assertEqual(
            (self.output / "glinet/direct.txt").read_text(),
            "internal.example.com\n203.0.113.64/26\n",
        )
        self.assertEqual(report["counts"]["proxy"], {"domains": 2, "ipv4": 1, "ipv6": 1})
        self.assertEqual(report["sources"][0]["input_count"], 3)
        self.assertEqual(report["sources"][0]["normalized_count"], 2)

    def test_supported_domains_and_single_addresses(self):
        self.write_payload(
            "custom/domain/proxy.yaml", ["+.123.example.com", "+.例子.测试", "exact.example.net"]
        )
        self.write_payload("custom/ipcidr/direct.yaml", ["192.0.2.9", "2001:db8:1::1"])
        generate(self.config_path, self.output)
        self.assertEqual(
            self.payload("rule-set/domain/proxy.yaml"),
            ["+.123.example.com", "+.xn--fsqu00a.xn--0zwm56d", "exact.example.net"],
        )
        self.assertEqual(
            self.payload("rule-set/ipcidr/direct.yaml"), ["192.0.2.9/32", "2001:db8:1::1/128"]
        )
        self.assertNotIn("2001:db8:1::1", (self.output / "glinet/direct.txt").read_text())

    def test_empty_local_ip_provider_is_valid(self):
        self.write_payload("custom/ipcidr/direct.yaml", [])
        generate(self.config_path, self.output)
        self.assertEqual(self.payload("rule-set/ipcidr/direct.yaml"), [])

    def test_dual_exports_preserve_top_level_suffixes(self):
        self.write_payload(
            "custom/domain/direct.yaml",
            ["+.CN.", "+.alibaba", "+.中国", "+.internal.example.com"],
        )
        generate(self.config_path, self.output)
        self.assertEqual(
            self.payload("rule-set/domain/direct.yaml"),
            ["+.alibaba", "+.cn", "+.internal.example.com", "+.xn--fiqs8s"],
        )
        self.assertEqual(
            (self.output / "glinet/direct.txt").read_text(),
            "alibaba\ncn\ninternal.example.com\nxn--fiqs8s\n203.0.113.64/26\n",
        )

    def test_repeated_build_is_deterministic(self):
        generate(self.config_path, self.output)
        before = self.snapshot()
        generate(self.config_path, self.output)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_source_preserves_previous_outputs(self):
        generate(self.config_path, self.output)
        before = self.snapshot()
        for invalid in (["*.example.com"], ["DOMAIN,example.com"], [42]):
            with self.subTest(invalid=invalid):
                self.write_payload("custom/domain/proxy.yaml", invalid)
                with self.assertRaises(BuildError):
                    generate(self.config_path, self.output)
                self.assertEqual(self.snapshot(), before)

    def test_late_invalid_source_preserves_previous_outputs(self):
        generate(self.config_path, self.output)
        before = self.snapshot()
        self.write_payload("custom/domain/proxy.yaml", ["+.new.example.com"])
        self.write_payload("custom/ipcidr/direct.yaml", ["bad network"])
        with self.assertRaises(BuildError):
            generate(self.config_path, self.output)
        self.assertEqual(self.snapshot(), before)

    def remote_source(self):
        self.config["sources"][0].pop("path")
        self.config["sources"][0]["url"] = "https://example.org/rules.yaml"
        self.save_config()

    def test_download_failure_preserves_previous_outputs(self):
        generate(self.config_path, self.output)
        before = self.snapshot()
        self.remote_source()
        with patch("scripts.generate.urlopen", side_effect=OSError("unreachable")) as fetch:
            with patch("scripts.generate.time.sleep"):
                with self.assertRaisesRegex(BuildError, "download failed"):
                    generate(self.config_path, self.output)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(self.snapshot(), before)

    def test_empty_remote_source_preserves_previous_outputs(self):
        generate(self.config_path, self.output)
        before = self.snapshot()
        self.remote_source()
        response = io.BytesIO(b"payload: []\n")
        response.status = 200
        with patch("scripts.generate.urlopen", return_value=response):
            with self.assertRaisesRegex(BuildError, "remote source is empty"):
                generate(self.config_path, self.output)
        self.assertEqual(self.snapshot(), before)

    def test_malformed_source_url_does_not_publish(self):
        self.remote_source()
        self.config["sources"][0]["url"] = "https://["
        self.save_config()
        with self.assertRaisesRegex(BuildError, "invalid source URL"):
            generate(self.config_path, self.output)
        self.assertFalse(self.output.exists())

    def test_configuration_errors_do_not_publish(self):
        for change in (
            {"policy": "unknown"},
            {"behavior": "classical"},
            {"url": "https://example.org/rules.yaml"},
            {"path": "../outside.yaml"},
        ):
            with self.subTest(change=change):
                self.config["sources"][0] = {
                    "name": "proxy-domain",
                    "policy": "proxy",
                    "behavior": "domain",
                    "path": "custom/domain/proxy.yaml",
                    **change,
                }
                self.save_config()
                with self.assertRaises(BuildError):
                    generate(self.config_path, self.output)
                self.assertFalse(self.output.exists())

    def test_unmanaged_output_and_configuration_directory_are_protected(self):
        self.output.mkdir()
        important = self.output / "important.txt"
        important.write_text("keep")
        with self.assertRaisesRegex(BuildError, "unmanaged"):
            generate(self.config_path, self.output)
        self.assertEqual(important.read_text(), "keep")
        with self.assertRaisesRegex(BuildError, "configuration"):
            generate(self.config_path, self.root)
        self.assertTrue(self.config_path.is_file())

    def test_manifest_matches_published_files(self):
        import hashlib

        report = generate(self.config_path, self.output)
        self.assertEqual(json.loads((self.output / "build-info.json").read_text()), report)
        for relative, digest in report["output_sha256"].items():
            self.assertEqual(
                hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), digest
            )


if __name__ == "__main__":
    unittest.main()
