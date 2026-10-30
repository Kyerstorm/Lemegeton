#!/usr/bin/env python3
"""Repository quality checks and an automatically detected technology stack.

Languages come from GitHub Linguist's repository languages endpoint. Frameworks
and tooling are reported only when supported by tracked manifests or source
imports; README roadmap text is deliberately not treated as implementation.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
IGNORED_PARTS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "target", "dist",
    "build", "coverage", "__pycache__", ".next", ".svelte-kit", "out",
}
NON_CODE_LANGUAGES = {
    "Markdown", "JSON", "JSON with Comments", "YAML", "TOML", "XML", "CSV",
    "SVG", "Text", "Plain Text", "Diff", "Ignore List", "Git Attributes",
}
EXTENSION_LANGUAGES = {
    ".py": "Python", ".pyi": "Python", ".rs": "Rust", ".go": "Go",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS", ".html": "HTML",
    ".htm": "HTML", ".rb": "Ruby", ".kt": "Kotlin", ".kts": "Kotlin",
    ".java": "Java", ".cs": "C#", ".cpp": "C++", ".cc": "C++",
    ".c": "C", ".h": "C", ".hpp": "C++", ".swift": "Swift",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
    ".bat": "Batchfile", ".r": "R", ".lua": "Lua", ".php": "PHP",
    ".dart": "Dart", ".vue": "Vue", ".svelte": "Svelte",
}
FRAMEWORK_RULES = {
    "@azure-rest/ai-inference": "Azure AI Inference SDK",
    "androidx.compose": "Jetpack Compose",
    "axum": "Axum",
    "beautifulsoup4": "Beautiful Soup",
    "boto3": "AWS SDK for Python (Boto3)",
    "cassandra-driver": "DataStax Cassandra Driver",
    "discord.py": "discord.py",
    "discord.js": "discord.js",
    "django": "Django",
    "duckdb": "DuckDB",
    "express": "Express",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "framer-motion": "Framer Motion",
    "gin-gonic/gin": "Gin",
    "go-chi/chi": "Chi",
    "gorm.io/gorm": "GORM",
    "hypothesis": "Hypothesis",
    "ktor": "Ktor",
    "next": "Next.js",
    "polars": "Polars",
    "pillow": "Pillow",
    "pydantic": "Pydantic",
    "pytest": "pytest",
    "react": "React",
    "react-dom": "React DOM",
    "reqwest": "Reqwest",
    "ruff": "Ruff",
    "scrapy": "Scrapy",
    "sinatra": "Sinatra",
    "sqlalchemy": "SQLAlchemy",
    "svelte": "Svelte",
    "tailwindcss": "Tailwind CSS",
    "three": "Three.js",
    "tokio": "Tokio",
    "typescript": "TypeScript",
    "vite": "Vite",
    "vue": "Vue",
    "yaml": "PyYAML",
}


def tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        )
        paths = [ROOT / item for item in result.stdout.split("\0") if item]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in ROOT.rglob("*") if p.is_file()]
    return sorted(
        p for p in paths
        if p.is_file() and not any(part in IGNORED_PARTS for part in p.relative_to(ROOT).parts)
    )


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def run_check(label: str, command: list[str], failures: list[str], cwd: Path = ROOT) -> None:
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    except OSError as exc:
        print(f"::warning::{label} skipped: {exc}")
        return
    if completed.returncode:
        detail = (completed.stdout + "\n" + completed.stderr).strip()
        print(f"::error::{label} failed\n{detail[-6000:]}")
        failures.append(label)
    else:
        print(f"::notice::{label} passed")


def check_css(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8-sig")
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    state = "code"
    quote = ""
    line = 1
    i = 0
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if char == "\n":
            line += 1
        if state == "comment":
            if char == "*" and nxt == "/":
                state = "code"
                i += 2
                continue
        elif state == "string":
            if char == "\\":
                i += 2
                continue
            if char == quote:
                state = "code"
        else:
            if char == "/" and nxt == "*":
                state = "comment"
                i += 2
                continue
            if char in ("'", '"'):
                state, quote = "string", char
            elif char in "({[":
                stack.append((char, line))
            elif char in ")}]":
                if not stack or stack[-1][0] != pairs[char]:
                    return f"unexpected {char!r} on line {line}"
                stack.pop()
        i += 1
    if state == "comment":
        return "unterminated block comment"
    if state == "string":
        return f"unterminated {quote} string"
    if stack:
        char, start_line = stack[-1]
        return f"unclosed {char!r} opened on line {start_line}"
    return None


def check_quality() -> int:
    files = tracked_files()
    failures: list[str] = []
    print(f"Checking {len(files)} tracked files in {ROOT}.")

    python_files = [p for p in files if p.suffix in {".py", ".pyi"}]
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            failures.append(f"Python syntax: {relative(path)}")
            print(f"::error file={relative(path)},line={getattr(exc, 'lineno', 1)}::{exc}")
    if python_files:
        print(f"::notice::Python syntax checked: {len(python_files)} files")

    json_files = [p for p in files if p.suffix.lower() == ".json"]
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            failures.append(f"JSON: {relative(path)}")
            print(f"::error file={relative(path)}::{exc}")
    if json_files:
        print(f"::notice::JSON parsed: {len(json_files)} files")

    toml_files = [p for p in files if p.suffix.lower() == ".toml"]
    for path in toml_files:
        try:
            tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            failures.append(f"TOML: {relative(path)}")
            print(f"::error file={relative(path)}::{exc}")
    if toml_files:
        print(f"::notice::TOML parsed: {len(toml_files)} files")

    js_files = [p for p in files if p.suffix.lower() in {".js", ".mjs", ".cjs"}]
    if js_files and shutil.which("node"):
        for path in js_files:
            run_check(f"JavaScript syntax: {relative(path)}", ["node", "--check", str(path)], failures)
    elif js_files:
        print("::warning::Node.js unavailable; JavaScript syntax checks skipped")

    ruby_files = [p for p in files if p.suffix.lower() == ".rb"]
    if ruby_files and shutil.which("ruby"):
        for path in ruby_files:
            run_check(f"Ruby syntax: {relative(path)}", ["ruby", "-c", str(path)], failures)

    shell_files = [p for p in files if p.suffix.lower() in {".sh", ".bash"}]
    if shell_files and shutil.which("bash"):
        for path in shell_files:
            run_check(f"Shell syntax: {relative(path)}", ["bash", "-n", str(path)], failures)

    css_files = [p for p in files if p.suffix.lower() in {".css", ".scss", ".sass"}]
    for path in css_files:
        try:
            issue = check_css(path)
        except UnicodeDecodeError as exc:
            issue = str(exc)
        if issue:
            failures.append(f"Stylesheet structure: {relative(path)}")
            print(f"::error file={relative(path)}::{issue}")
    if css_files:
        print(f"::notice::Stylesheet delimiter/string checks: {len(css_files)} files")

    if python_files and shutil.which("ruff"):
        # Restrict the baseline gate to serious correctness/syntax diagnostics.
        run_check("Ruff critical-error checks", ["ruff", "check", "--output-format=github", "--select", "E9,F63,F7", "."], failures)

    # Run a Python project's declared test extra when it is explicit and complete.
    pyproject = ROOT / "pyproject.toml"
    tests_dir = ROOT / "tests"
    if pyproject.is_file() and tests_dir.is_dir():
        try:
            config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            extras = config.get("project", {}).get("optional-dependencies", {})
            test_extra = extras.get("test", [])
            if any("pytest" in str(dep).lower() for dep in test_extra):
                install = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-e", ".[test]"],
                    cwd=ROOT, text=True,
                )
                if install.returncode:
                    failures.append("Install declared Python test dependencies")
                else:
                    run_check("Python test suite", [sys.executable, "-m", "pytest", "-q"], failures)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(f"::warning::Could not inspect Python test configuration: {exc}")

    if failures:
        print("\nRepository quality checks failed:")
        for item in failures:
            print(f" - {item}")
        return 1
    print("\nRepository quality checks passed.")
    return 0


def github_languages(repo: str) -> tuple[dict[str, int], str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo:
        return {}, "GitHub repository context was not available"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "repository-health-stack-detector",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/languages", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict):
            return {str(k): int(v) for k, v in payload.items() if isinstance(v, int)}, "GitHub Linguist"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        print(f"::warning::GitHub language API unavailable; using tracked-file fallback: {exc}")
    return {}, "tracked-file extension fallback"


def collect_manifest_text(files: list[Path]) -> tuple[str, set[str], list[str]]:
    texts: list[str] = []
    tooling: set[str] = set()
    runtime_notes: list[str] = []
    for path in files:
        rel = path.as_posix().lower()
        name = path.name.lower()
        if name == "package.json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            texts.append(json.dumps(data.get("dependencies", {})) + json.dumps(data.get("devDependencies", {})) + json.dumps(data.get("peerDependencies", {})))
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                texts.append(json.dumps(scripts))
            engines = data.get("engines", {})
            if isinstance(engines, dict) and engines.get("node"):
                runtime_notes.append(f"Node.js {engines['node']}")
        elif name == "pyproject.toml":
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                texts.append(str(data.get("project", {}).get("dependencies", [])))
                texts.append(str(data.get("project", {}).get("optional-dependencies", {})))
                if data.get("project", {}).get("requires-python"):
                    runtime_notes.append(f"Python {data['project']['requires-python']}")
            except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
                pass
        elif name.startswith("requirements") and name.endswith(".txt"):
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
        elif name == "cargo.toml":
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                texts.append(str(data.get("dependencies", {})))
                texts.append(str(data.get("dev-dependencies", {})))
                texts.append(str(data.get("workspace", {})))
            except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
                pass
        elif name == "go.mod":
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
        elif name in {"gemfile", "gemspec"}:
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
        elif name.startswith("build.gradle") or name == "pom.xml" or name.endswith(".csproj"):
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
        if rel.startswith(".github/workflows/"):
            tooling.add("GitHub Actions")
        if name == "dockerfile" or name in {"docker-compose.yml", "compose.yml", "compose.yaml"}:
            tooling.add("Docker")
        if name == "cargo.toml":
            tooling.add("Cargo")
        if name == "go.mod":
            tooling.add("Go Modules")
        if name == "pyproject.toml":
            tooling.add("Python project metadata")
        if name.startswith("requirements") and name.endswith(".txt"):
            tooling.add("pip requirements")
        if name == "package-lock.json" or name == "npm-shrinkwrap.json":
            tooling.add("npm")
        if name in {"bun.lock", "bun.lockb"}:
            tooling.add("Bun")
        if name == "pnpm-lock.yaml":
            tooling.add("pnpm")
        if name == "yarn.lock":
            tooling.add("Yarn")
        if name.startswith("build.gradle"):
            tooling.add("Gradle")
        if name == "pom.xml":
            tooling.add("Maven")
        if name == "gemfile":
            tooling.add("Bundler")
        if name in {"justfile", "makefile"}:
            tooling.add("Make / task automation")
    return "\n".join(texts), tooling, runtime_notes


def detect_stack() -> str:
    files = tracked_files()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    language_bytes, language_source = github_languages(repo)
    language_bytes = {k: v for k, v in language_bytes.items() if k not in NON_CODE_LANGUAGES and v > 0}

    if not language_bytes:
        counts: Counter[str] = Counter()
        for path in files:
            lang = EXTENSION_LANGUAGES.get(path.suffix.lower())
            if lang:
                try:
                    counts[lang] += path.stat().st_size
                except OSError:
                    pass
        language_bytes = dict(counts)
        language_source = "tracked-file extension fallback"

    manifest_text, tooling, runtime_notes = collect_manifest_text(files)
    source_extensions = {
        ".py", ".rs", ".go", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
        ".rb", ".kt", ".kts", ".java", ".cs", ".cpp", ".cc", ".c", ".swift",
        ".php", ".dart", ".vue", ".svelte",
    }
    for path in files:
        if path.suffix.lower() in source_extensions and path.stat().st_size < 500_000:
            try:
                manifest_text += "\n" + path.read_text(encoding="utf-8", errors="ignore")[:500_000]
            except OSError:
                pass

    lowered = manifest_text.lower()
    frameworks: set[str] = set()
    for key, label in FRAMEWORK_RULES.items():
        if re.search(r"(?<![a-z0-9_-])" + re.escape(key.lower()) + r"(?![a-z0-9_-])", lowered):
            frameworks.add(label)
    if re.search(r"com\.android\.(application|library)", lowered):
        frameworks.add("Android Gradle Plugin")
    if "org.jetbrains.kotlin.plugin.compose" in lowered or "androidx.compose" in lowered:
        frameworks.add("Jetpack Compose")
    if "org.springframework.boot" in lowered or "spring-boot" in lowered:
        frameworks.add("Spring Boot")
    if "org.jetbrains.kotlin" in lowered:
        frameworks.add("Kotlin")
    if "sqlite3" in lowered or "sqlite" in lowered:
        frameworks.add("SQLite")
    if "asyncpg" in lowered or "psycopg" in lowered:
        frameworks.add("PostgreSQL client")
    if "postgresql" in lowered or "postgres" in lowered:
        frameworks.add("PostgreSQL")

    total = sum(language_bytes.values())
    rows = [
        "# Automated technology stack",
        "",
        "> Generated from this repository's tracked files and dependency manifests. Do not edit by hand.",
        "",
        "## Language composition",
        "",
    ]
    if total:
        rows.extend(["| Language | Bytes | Share |", "| --- | ---: | ---: |"])
        for language, size in sorted(language_bytes.items(), key=lambda item: item[1], reverse=True):
            rows.append(f"| {language} | {size:,} | {size / total * 100:.1f}% |")
        rows.append("")
        rows.append(f"_Language source: {language_source}. Percentages describe repository composition, not individual authorship._")
    else:
        rows.append("No implementation language is currently detected. This repository may contain documentation, research notes, configuration, or an early project specification; planned technologies are not reported as implemented.")

    rows.extend(["", "## Frameworks and libraries", ""])
    if frameworks:
        rows.extend(f"- {item}" for item in sorted(frameworks))
    else:
        rows.append("No framework or library was inferred from a dependency manifest or source import.")

    rows.extend(["", "## Build and repository tooling", ""])
    if tooling:
        rows.extend(f"- {item}" for item in sorted(tooling))
    else:
        rows.append("No build or automation tool was detected from repository files.")

    if runtime_notes:
        rows.extend(["", "## Declared runtimes", ""])
        rows.extend(f"- {item}" for item in sorted(set(runtime_notes)))

    rows.extend([
        "",
        "## Detection policy",
        "",
        "- Language composition comes from GitHub Linguist when its repository API is available; otherwise tracked source-file extensions are used.",
        "- Frameworks are listed only when found in committed manifests, build files, or source imports.",
        "- Names mentioned only in README plans or roadmaps are not treated as installed dependencies.",
        "- This report describes the repository as a whole and does not estimate any contributor's personal code share.",
        "",
    ])
    return "\n".join(rows)


def write_stack() -> int:
    content = detect_stack()
    destination = ROOT / "TECH_STACK.md"
    destination.write_text(content, encoding="utf-8", newline="\n")
    print(f"Updated {destination}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quality", action="store_true", help="run portable source and manifest checks")
    group.add_argument("--stack", action="store_true", help="generate TECH_STACK.md")
    args = parser.parse_args()
    return check_quality() if args.quality else write_stack()


if __name__ == "__main__":
    raise SystemExit(main())
