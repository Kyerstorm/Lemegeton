"""Generated per-file integrity checks for the repository source and configuration files.

These are deliberately lightweight checks for files without isolated business logic. The
command/helper suites cover behavior; these tests catch malformed syntax, structured data,
broken SVG/HTML documents, and unreadable or accidentally binary text files across the repo.
"""
import ast
import html.parser
import hashlib
import json
import shutil
import subprocess
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def _repo_files() -> list[Path]:
    """Enumerate committed files so generated caches/logs cannot become accidental test targets."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            timeout=10,
        )
        paths = [
            ROOT / item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        ]
    except (OSError, subprocess.SubprocessError):
        paths = [path for path in ROOT.rglob("*") if path.is_file()]

    return sorted(
        path for path in paths
        if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
    )

def _validate_file(path: Path) -> None:
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"{relative} is not UTF-8 text; add an explicit binary asset test") from exc

    if suffix == ".py":
        ast.parse(source, filename=relative)
    elif suffix == ".json":
        json.loads(source)
    elif suffix == ".toml":
        try:
            import tomllib
        except ImportError:
            return  # Python <3.11 can still validate the file as readable text.
        tomllib.loads(source)
    elif suffix in {".yaml", ".yml"}:
        yaml.safe_load(source)
    elif suffix == ".svg":
        ET.fromstring(source)
    elif suffix in {".html", ".htm"}:
        parser = html.parser.HTMLParser(convert_charrefs=True)
        parser.feed(source)
        parser.close()
    elif suffix == ".js" and shutil.which("node"):
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if result.returncode:
            raise AssertionError(f"{relative} failed node --check:\\n{result.stderr}")

    if "\x00" in source:
        raise AssertionError(f"{relative} contains a NUL byte")


class RepositoryFileIntegrityTests(unittest.TestCase):
    """Test every repository file through the validator appropriate for its format."""


def _test_for_path(path: Path):
    relative = path.relative_to(ROOT).as_posix()

    def test(self):
        with self.subTest(path=relative):
            _validate_file(path)

    slug = "".join(char if char.isalnum() else "_" for char in relative)
    suffix = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:8]
    test.__name__ = f"test_file_{slug}_{suffix}"
    test.__doc__ = f"Validate {relative}"
    return test


for _path in _repo_files():
    _test = _test_for_path(_path)
    setattr(RepositoryFileIntegrityTests, _test.__name__, _test)

