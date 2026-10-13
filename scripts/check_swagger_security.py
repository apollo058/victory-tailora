"""Pinned Swagger assets, browser dependency inventory, and OSV advisories audit.

The upstream lockfile is a conservative version inventory for modules listed in
the published source map. It does not prove that every advisory is exploitable.
Unmapped modules or an unavailable advisory service fail the check.
"""

import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024


def fetch(url: str, payload: dict | None = None) -> bytes:
    """Fetch bounded HTTPS audit data without executing downloaded code."""
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "User-Agent": "tailora-security"},
    )
    with urlopen(request, timeout=30) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError("audit download exceeded its size limit")
    return data


def asset_config() -> dict[str, str]:
    """Read literal pins without importing optional runtime dependencies."""
    tree = ast.parse(
        (PROJECT_ROOT / "src/tailora/adapters/fastapi/docs.py").read_text(),
    )
    names = {
        "SUPPORTED_SWAGGER_UI_VERSION",
        "_SWAGGER_UI_CSS_INTEGRITY",
        "_SWAGGER_UI_JS_INTEGRITY",
    }
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    result[target.id] = ast.literal_eval(node.value)
    if result.keys() != names:
        raise ValueError("Swagger asset configuration is incomplete")
    if not re.fullmatch(r"\d+\.\d+\.\d+", result["SUPPORTED_SWAGGER_UI_VERSION"]):
        raise ValueError("Swagger version must be an exact release")
    return result


def browser_inventory(
    source_map: dict,
    lock: dict,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Inventory imported modules, excluding upstream CLI-only dependencies."""
    lock_packages = lock["packages"]
    keys = sorted(
        (key for key in lock_packages if "node_modules/" in key),
        key=len,
        reverse=True,
    )
    inventory = set()
    unmapped = set()
    for source in source_map["sources"]:
        position = source.find("node_modules/")
        if position < 0:
            continue
        module_path = source[position:]
        matching = [key for key in keys if module_path.startswith(key + "/")]
        if matching:
            matching = matching[:1]
        else:
            parts = module_path.removeprefix("node_modules/").split("/")
            name = "/".join(parts[:2]) if parts[0].startswith("@") else parts[0]
            matching = [
                key for key in keys if key.rsplit("node_modules/", 1)[1] == name
            ]
        if not matching:
            unmapped.add(module_path)
            continue
        for key in matching:
            item = lock_packages[key]
            name = item.get("name") or key.rsplit("node_modules/", 1)[1]
            inventory.add((name, item["version"]))
    return sorted(inventory), sorted(unmapped)


def main() -> int:
    """Verify asset integrity and fail if the browser inventory has advisories."""
    config = asset_config()
    version = config["SUPPORTED_SWAGGER_UI_VERSION"]
    base = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{version}"
    bundle = b""
    for filename, pin in (
        ("swagger-ui.css", "_SWAGGER_UI_CSS_INTEGRITY"),
        ("swagger-ui-bundle.js", "_SWAGGER_UI_JS_INTEGRITY"),
    ):
        data = fetch(f"{base}/{filename}")
        integrity = "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode()
        if integrity != config[pin]:
            raise ValueError(f"SRI does not match {filename}")
        if filename.endswith(".js"):
            bundle = data
    source_map = json.loads(fetch(f"{base}/swagger-ui-bundle.js.map"))
    lock = json.loads(
        fetch(
            f"https://raw.githubusercontent.com/swagger-api/swagger-ui/v{version}/package-lock.json",
        )
    )
    inventory, unmapped = browser_inventory(source_map, lock)
    purify = re.search(rb'DOMPurify\.version="([0-9.]+)"', bundle)
    if purify is None:
        raise ValueError("Bundled DOMPurify version could not be verified")
    inventory = [package for package in inventory if package[0] != "dompurify"]
    inventory.extend([("dompurify", purify[1].decode()), ("swagger-ui-dist", version)])
    vulnerabilities = []
    for offset in range(0, len(inventory), 100):
        batch = inventory[offset : offset + 100]
        result = json.loads(
            fetch(
                "https://api.osv.dev/v1/querybatch",
                {
                    "queries": [
                        {
                            "package": {"name": name, "ecosystem": "npm"},
                            "version": release,
                        }
                        for name, release in batch
                    ],
                },
            )
        )
        if len(result["results"]) != len(batch):
            raise ValueError("Advisory service returned an incomplete result")
        for package, item in zip(batch, result["results"]):
            for advisory in item.get("vulns", []):
                vulnerabilities.append(
                    {
                        "package": package[0],
                        "version": package[1],
                        "id": advisory["id"],
                    }
                )
    report = {
        "swagger_version": version,
        "sri_verified": True,
        "inventory_source": "published source map and upstream release lockfile",
        "inventory_complete": not unmapped,
        "unmapped_modules": unmapped,
        "version_confidence": "upstream lock inference; DOMPurify verified in bundle",
        "packages": inventory,
        "advisories": vulnerabilities,
    }
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Swagger {version}: SRI verified; {len(inventory)} package versions inspected"
    )
    for item in vulnerabilities:
        print(f"{item['package']} {item['version']}: {item['id']}")
    for module in unmapped:
        print(f"INCOMPLETE inventory: {module}")
    return 1 if vulnerabilities or unmapped else 0


if __name__ == "__main__":
    raise SystemExit(main())
