#!/usr/bin/env python3
"""Generate GL.iNet and Mihomo subscriptions from YAML rule providers."""

import argparse
import hashlib
import ipaddress
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 16 * 1024 * 1024
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class BuildError(ValueError):
    """An input or output cannot be safely used for publication."""


def yaml_document(data: bytes, label: str) -> dict:
    try:
        document = yaml.safe_load(data.decode("utf-8-sig"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise BuildError(f"{label}: invalid UTF-8 YAML") from exc
    if not isinstance(document, dict):
        raise BuildError(f"{label}: expected a YAML mapping")
    return document


def domain_rule(value: str) -> str:
    suffix = value.startswith("+.")
    host = value[2:] if suffix else value
    if host.endswith("."):
        host = host[:-1]
    try:
        host = host.lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise BuildError("invalid domain") from exc
    labels = host.split(".")
    if (
        len(host) > 253
        or (len(labels) < 2 and not suffix)
        or labels[-1].isdigit()
        or any(not HOST_LABEL.fullmatch(label) for label in labels)
    ):
        raise BuildError("invalid domain or unsupported wildcard")
    return f"+.{host}" if suffix else host


def cidr_rules(values: list[str]) -> list[str]:
    networks = [ipaddress.ip_network(value, strict=False) for value in values]
    return [
        str(network)
        for version in (4, 6)
        for network in ipaddress.collapse_addresses(
            network for network in networks if network.version == version
        )
    ]


def parse_rules(data: bytes, behavior: str, label: str) -> tuple[list[str], int]:
    payload = yaml_document(data, label).get("payload")
    if not isinstance(payload, list):
        raise BuildError(f"{label}: expected a payload list")
    rules = []
    for index, value in enumerate(payload, 1):
        if not isinstance(value, str) or not value.strip():
            raise BuildError(f"{label}: rule {index} must be a nonempty string")
        try:
            rule = (
                domain_rule(value.strip())
                if behavior == "domain"
                else str(ipaddress.ip_network(value.strip(), strict=False))
            )
        except ValueError as exc:
            raise BuildError(f"{label}: rule {index} is invalid for {behavior}") from exc
        rules.append(rule)
    normalized = sorted(set(rules)) if behavior == "domain" else cidr_rules(rules)
    return normalized, len(payload)


def local_path(value: str, root: Path) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise BuildError("source paths must be relative to the configuration file")
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise BuildError("source paths must stay inside the configuration directory")
    return path


def source_bytes(source: dict, root: Path) -> bytes:
    name = source["name"]
    if "path" in source:
        with local_path(source["path"], root).open("rb") as handle:
            data = handle.read(MAX_SOURCE_BYTES + 1)
    else:
        url = source["url"]
        if not isinstance(url, str):
            raise BuildError(f"{name}: URL must be a string")
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise BuildError(f"{name}: invalid source URL") from exc
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(character.isspace() for character in url)
        ):
            raise BuildError(f"{name}: expected an HTTP(S) URL without credentials")
        request = Request(url, headers={"User-Agent": "rules/0.1.0"})
        for attempt in range(3):
            try:
                with urlopen(request, timeout=20) as response:
                    if response.status != 200:
                        raise BuildError(f"{name}: unexpected HTTP status {response.status}")
                    data = response.read(MAX_SOURCE_BYTES + 1)
                break
            except OSError as exc:
                if attempt == 2:
                    raise BuildError(f"{name}: download failed after 3 attempts") from exc
                time.sleep(attempt + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise BuildError(f"{name}: source exceeds the 16 MiB limit")
    return data


def validate_sources(config: dict) -> list[dict]:
    if set(config) - {"sources"}:
        raise BuildError("configuration has unknown keys")
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise BuildError("configuration requires a nonempty sources list")
    names = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) - {
            "name",
            "behavior",
            "policy",
            "path",
            "url",
        }:
            raise BuildError("invalid source configuration")
        name = source.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise BuildError("source names must be nonempty and unique")
        names.add(name)
        if source.get("behavior") not in ("domain", "ipcidr"):
            raise BuildError(f"{name}: behavior must be domain or ipcidr")
        if source.get("policy") not in ("proxy", "direct"):
            raise BuildError(f"{name}: policy must be proxy or direct")
        if ("path" in source) == ("url" in source):
            raise BuildError(f"{name}: specify exactly one of path or url")
    return sources


def rules_yaml(rules: list[str]) -> bytes:
    return yaml.safe_dump({"payload": rules}, sort_keys=False).encode("utf-8")


def write_output(output: Path, files: dict[str, bytes], config_path: Path) -> None:
    if output.is_symlink():
        raise BuildError("output directory must not be a symlink")
    output = output.resolve()
    if ROOT.is_relative_to(output) or config_path.is_relative_to(output):
        raise BuildError("output directory must not contain project sources or configuration")
    if output.exists():
        if not output.is_dir():
            raise BuildError("output must be a directory")
        if any(output.iterdir()):
            try:
                manifest = json.loads((output / "build-info.json").read_text())
            except (OSError, ValueError) as exc:
                raise BuildError("refusing to replace an unmanaged output directory") from exc
            if not isinstance(manifest, dict) or manifest.get("generator") != "rules":
                raise BuildError("refusing to replace an unmanaged output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".rules-build-", dir=output.parent) as temporary:
        staging = Path(temporary) / "next"
        staging.mkdir()
        for relative, data in files.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        previous = Path(temporary) / "previous"
        if output.exists():
            output.rename(previous)
        try:
            staging.rename(output)
        except OSError:
            if previous.exists():
                previous.rename(output)
            raise


def generate(config_path: Path, output: Path) -> dict:
    config_path = config_path.resolve()
    config_data = config_path.read_bytes()
    sources = validate_sources(yaml_document(config_data, "configuration"))
    groups = {
        policy: {behavior: [] for behavior in ("domain", "ipcidr")}
        for policy in ("proxy", "direct")
    }
    files = {}
    records = []
    for source in sources:
        name, behavior = source["name"], source["behavior"]
        data = source_bytes(source, config_path.parent)
        rules, input_count = parse_rules(data, behavior, name)
        if "url" in source and not rules:
            raise BuildError(f"{name}: remote source is empty")
        record = {
            "name": name,
            "policy": source["policy"],
            "behavior": behavior,
            "sha256": hashlib.sha256(data).hexdigest(),
            "input_count": input_count,
            "normalized_count": len(rules),
        }
        groups[source["policy"]][behavior].extend(rules)
        location = source.get("path")
        if location is None:
            # Keep URL query parameters out of the published provenance.
            location = source["url"].split("?", 1)[0].split("#", 1)[0]
        record["path" if "path" in source else "url"] = location
        records.append(record)

    counts = {}
    for policy, values in groups.items():
        domains = sorted(set(values["domain"]))
        networks = cidr_rules(values["ipcidr"])
        ipv4 = [network for network in networks if ":" not in network]
        ipv6 = [network for network in networks if ":" in network]
        files[f"rule-set/domain/{policy}.yaml"] = rules_yaml(domains)
        files[f"rule-set/ipcidr/{policy}.yaml"] = rules_yaml(networks)
        targets = sorted({rule.removeprefix("+.") for rule in domains}) + ipv4
        if not targets:
            raise BuildError(f"{policy}: GL.iNet list must contain a domain or IPv4 target")
        files[f"glinet/{policy}.txt"] = ("\n".join(targets) + "\n").encode("utf-8")
        counts[policy] = {"domains": len(domains), "ipv4": len(ipv4), "ipv6": len(ipv6)}

    report = {
        "generator": "rules",
        "configuration_sha256": hashlib.sha256(config_data).hexdigest(),
        "sources": records,
        "counts": counts,
        "output_sha256": {
            relative: hashlib.sha256(data).hexdigest() for relative, data in sorted(files.items())
        },
    }
    files["build-info.json"] = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    write_output(output, files, config_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "sources.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        report = generate(args.config, args.output)
    except (BuildError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Generated subscriptions in {args.output}")
    for policy, counts in report["counts"].items():
        print(
            f"{policy}: {counts['domains']} domains, {counts['ipv4']} IPv4, {counts['ipv6']} IPv6"
        )


if __name__ == "__main__":
    main()
