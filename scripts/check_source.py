#!/usr/bin/env python3
"""Check the distributable source tree without reading user runtime data."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "__pycache__", "dist", "build", "state", "artifacts"}
REQUIRED = (
    "VERSION", "README.md", "CHANGELOG.md", "backend/config.example.json",
    "backend/mission_version.py", "backend/rules.py", "native/App.swift",
    "windows/MissionManager.cs", "windows/Installer.cs", "windows/build.ps1",
    "packaging/python-runtime.lock.json", "windows/python-runtime.lock.json",
    "docs/USER_GUIDE.md", "docs/BUILDING.md", "docs/RELEASE_PROCESS.md",
    ".github/workflows/release.yml",
)


def main():
    errors = ["Missing required source: " + name for name in REQUIRED if not (ROOT / name).is_file()]
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("VERSION must contain a semantic release version")
    if not (ROOT / "docs/releases" / (version + ".md")).is_file():
        errors.append("Missing release notes for VERSION")
    for name in ("backend/config.json", "backend/web"):
        if (ROOT / name).exists():
            errors.append("Runtime or retired content must stay outside source: " + name)
    checked = 0
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if set(relative.parts) & EXCLUDED or not path.is_file() or path.name == "github-upload-status.json":
            continue
        if path.suffix in (".pyc", ".sqlite3", ".log", ".p12", ".p8", ".pem", ".key", ".pfx"):
            errors.append("Private/generated file in source: " + str(relative))
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            except (SyntaxError, UnicodeError) as error:
                errors.append(str(error))
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError) as error:
                errors.append(str(relative) + ": " + str(error))
        if path.suffix in (".py", ".swift", ".cs", ".json", ".md", ".ps1", ".yml", ".plist", ".strings", ".js", ".cjs", ".html", ".svg"):
            source = path.read_text(encoding="utf-8")
            checks = (
                r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
                r"\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b",
                r"/Users/(?!Shared(?:/|\b)|example(?:/|\b)|username(?:/|\b)|<)[A-Za-z0-9_.-]+/",
            )
            if any(re.search(pattern, source) for pattern in checks):
                errors.append("Review potential private content: " + str(relative))
            checked += 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps({"version": version, "source_files_checked": checked,
                      "known_private_patterns_found": 0, "runtime_config_in_source": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
