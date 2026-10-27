"""Repository-wide source and text statistics for README and the /help overview."""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- REPO-STATS:START -->"
END_MARKER = "<!-- REPO-STATS:END -->"

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", "node_modules", "target", "dist",
    "build", ".next", ".netlify", "runtime-home", "logs", "data",
    "data_upload", "test_images", "coverage",
}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json",
    ".jsonc", ".md", ".mdx", ".rst", ".txt", ".toml", ".yaml", ".yml",
    ".ini", ".cfg", ".conf", ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".rs", ".css", ".scss", ".sass", ".html", ".htm", ".sql", ".xml",
    ".svg", ".lock", ".go", ".java", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".kt", ".swift", ".php", ".rb", ".lua", ".vue", ".svelte",
}
TEXT_NAMES = {
    ".gitignore", ".dockerignore", ".env.example", "Dockerfile", "Containerfile",
    "Procfile", "Makefile", "LICENSE", "NOTICE", "COPYING", "Gemfile",
}
SOURCE_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".rs",
    ".css", ".scss", ".sass", ".html", ".htm", ".svg", ".sql", ".sh",
    ".bash", ".ps1", ".bat", ".cmd", ".go", ".java", ".c", ".h", ".cc",
    ".cpp", ".hpp", ".kt", ".swift", ".php", ".rb", ".lua", ".vue", ".svelte",
}
LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript / TypeScript", ".jsx": "JavaScript / TypeScript",
    ".mjs": "JavaScript / TypeScript", ".cjs": "JavaScript / TypeScript",
    ".ts": "JavaScript / TypeScript", ".tsx": "JavaScript / TypeScript",
    ".rs": "Rust", ".css": "CSS / Sass", ".scss": "CSS / Sass",
    ".sass": "CSS / Sass", ".html": "HTML / SVG", ".htm": "HTML / SVG",
    ".svg": "HTML / SVG", ".sql": "SQL", ".sh": "Shell",
    ".bash": "Shell", ".ps1": "Shell", ".bat": "Shell", ".cmd": "Shell",
}


def _is_excluded(relative_path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative_path.parts)


def _repository_files(root: Path) -> list[Path]:
    """Use Git's tracked-file list where possible; otherwise scan the source tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
        tracked = [
            root / Path(raw.decode("utf-8"))
            for raw in result.stdout.split(b"\0")
            if raw
        ]
        tracked = [
            path for path in tracked
            if not _is_excluded(path.relative_to(root)) and path.is_file()
        ]
        if tracked:
            return sorted(set(tracked))
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeDecodeError):
        pass

    found: list[Path] = []
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names if name not in EXCLUDED_DIRS
        )
        current_path = Path(current)
        for name in file_names:
            path = current_path / name
            relative_path = path.relative_to(root)
            if not _is_excluded(relative_path):
                found.append(path)
    return sorted(found)


def _is_text_candidate(path: Path) -> bool:
    return path.name in TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def collect_repository_stats(
    root: Path | str | None = None,
    *,
    readme_content: str | None = None,
) -> dict:
    """Collect reproducible repository metrics without third-party packages."""
    repository_root = Path(root or ROOT).resolve()
    files = _repository_files(repository_root)

    text_files = 0
    text_lines = 0
    text_characters = 0
    text_bytes = 0
    source_files = 0
    source_lines = 0
    nonblank_source_lines = 0
    language_lines: dict[str, int] = {}

    for path in files:
        relative_path = path.relative_to(repository_root)
        if not _is_text_candidate(path):
            continue

        try:
            if readme_content is not None and relative_path == Path("README.md"):
                content = readme_content
            else:
                content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if "\0" in content:
            continue

        text_files += 1
        lines = content.splitlines()
        text_lines += len(lines)
        text_characters += len(content.replace("\r", "").replace("\n", ""))
        try:
            text_bytes += path.stat().st_size
        except OSError:
            text_bytes += len(content.encode("utf-8"))

        suffix = path.suffix.lower()
        if suffix not in SOURCE_SUFFIXES:
            continue

        source_files += 1
        source_lines += len(lines)
        nonblank_source_lines += sum(1 for line in lines if line.strip())
        language = LANGUAGE_BY_SUFFIX.get(suffix, "Other")
        language_lines[language] = language_lines.get(language, 0) + len(lines)

    return {
        "tracked_files": len(files),
        "text_files": text_files,
        "text_lines": text_lines,
        "text_characters": text_characters,
        "text_bytes": text_bytes,
        "source_files": source_files,
        "source_lines": source_lines,
        "nonblank_source_lines": nonblank_source_lines,
        "language_lines": language_lines,
    }


def format_bytes(size: int) -> str:
    """Return a compact, human-readable byte count."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


def _render_readme_table(stats: dict, refreshed_at: str) -> str:
    language_breakdown = "; ".join(
        f"{name}: {count:,} lines"
        for name, count in sorted(
            stats["language_lines"].items(),
            key=lambda item: (-item[1], item[0]),
        )
    ) or "No source files detected"

    rows = [
        "| Metric | Current total |",
        "|:--|--:|",
        f'| Tracked files | {stats["tracked_files"]:,} |',
        f'| Text files scanned | {stats["text_files"]:,} |',
        f'| Source code files | {stats["source_files"]:,} |',
        f'| Source lines (including blank lines) | {stats["source_lines"]:,} |',
        f'| Non-blank source lines | {stats["nonblank_source_lines"]:,} |',
        f'| Text lines (code, docs, and configuration) | {stats["text_lines"]:,} |',
        f'| Characters (excluding line breaks) | {stats["text_characters"]:,} |',
        f'| Text file size | {format_bytes(stats["text_bytes"])} |',
        f"| Source line breakdown | {language_breakdown} |",
        f"| Last refreshed (UTC) | {refreshed_at} |",
    ]
    return "\n".join(rows)


def update_readme(root: Path | str | None = None) -> bool:
    """Update the README's generated statistics block; return whether it changed."""
    repository_root = Path(root or ROOT).resolve()
    readme_path = repository_root / "README.md"
    current = readme_path.read_text(encoding="utf-8")

    if current.count(START_MARKER) != 1 or current.count(END_MARKER) != 1:
        raise ValueError(
            f"README.md must contain exactly one {START_MARKER} and {END_MARKER} marker."
        )

    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    updated = current

    # Iterate so the generated numbers include the final README block itself.
    for _ in range(10):
        stats = collect_repository_stats(repository_root, readme_content=updated)
        table = _render_readme_table(stats, refreshed_at)
        start = updated.index(START_MARKER) + len(START_MARKER)
        end = updated.index(END_MARKER, start)
        next_content = updated[:start] + "\n" + table + "\n" + updated[end:]
        if next_content == updated:
            break
        updated = next_content

    if updated != current:
        readme_path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate or refresh Lemegeton repository statistics.")
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="refresh the generated statistics table in README.md",
    )
    args = parser.parse_args()

    if args.update_readme:
        changed = update_readme()
        print("README statistics refreshed." if changed else "README statistics already current.")

    stats = collect_repository_stats()
    print(f"Tracked files: {stats['tracked_files']:,}")
    print(f"Source files: {stats['source_files']:,}")
    print(f"Source lines: {stats['source_lines']:,} ({stats['nonblank_source_lines']:,} non-blank)")
    print(f"Text characters (excluding line breaks): {stats['text_characters']:,}")
    print(f"Text size: {format_bytes(stats['text_bytes'])}")


if __name__ == "__main__":
    main()
