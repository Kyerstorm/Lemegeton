"""Optional local search index for shaido987/novel-dataset.

The upstream data is intentionally not vendored. Set NOVELUPDATES_DATASET_PATH or
place the upstream CSV/JSON in data/novelupdates/ after reviewing its usage terms.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit

log = logging.getLogger("Lemegeton.NovelUpdatesDataset")

UPSTREAM_REPOSITORY = "https://github.com/shaido987/novel-dataset"
DATASET_VERSION = "0.1.5"
DATASET_UPDATED_AT = "2025-08-21"
DATASET_MAX_BYTES = 128 * 1024 * 1024
DEFAULT_DATASET_FILES = (
    Path(__file__).resolve().parents[1] / "data" / "novelupdates" / "novels_0.1.5.json",
    Path(__file__).resolve().parents[1] / "data" / "novelupdates" / "novels_0.1.5.csv",
)
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[int, int, list[dict[str, Any]], dict[str, dict[str, Any]]]] = {}


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def get_novelupdates_dataset_path() -> str | None:
    """Return the configured dataset path, or a conventional local path if present."""
    configured = os.getenv("NOVELUPDATES_DATASET_PATH", "").strip()
    if configured:
        return str(Path(configured).expanduser())
    for candidate in DEFAULT_DATASET_FILES:
        if candidate.is_file():
            return str(candidate)
    return None


def novelupdates_dataset_enabled() -> bool:
    """Whether a dataset path has been configured or a conventional local file exists."""
    return get_novelupdates_dataset_path() is not None


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            raw_values = list(parsed)
        else:
            raw_values = re.split(r"\s*(?:\||;|,\s*)\s*", text)
    output: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        if isinstance(item, (dict, list, tuple, set)) or item is None:
            continue
        clean = " ".join(str(item).split()).strip()
        normalized = clean.casefold()
        if clean and normalized not in seen:
            output.append(clean)
            seen.add(normalized)
    return output


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().casefold()
    if text in {"true", "yes", "y", "1", "complete", "completed", "licensed", "licenced"}:
        return True
    if text in {"false", "no", "n", "0", "incomplete", "ongoing", "unlicensed", "unlicenced"}:
        return False
    return None


def _first(row: dict[str, Any], *aliases: str) -> Any:
    for alias in aliases:
        value = row.get(_key(alias))
        if value is not None and str(value).strip() != "":
            return value
    return None


def _safe_cover(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return url


def _series_url(row: dict[str, Any], title: str) -> str:
    supplied = _first(row, "series url", "series_url", "novel url", "novel_url", "url", "link")
    if supplied:
        parsed = urlsplit(str(supplied).strip())
        host = (parsed.hostname or "").casefold().rstrip(".")
        if (
            parsed.scheme == "https"
            and (host == "novelupdates.com" or host.endswith(".novelupdates.com"))
            and parsed.path.startswith("/series/")
        ):
            return str(supplied).strip()
    # The public dataset schema does not promise a per-series permalink.
    # Link to a Novel Updates search instead of guessing a record URL from an ID.
    return f"https://www.novelupdates.com/series-finder/?sf=1&sh={quote_plus(title)}"


def _normalize_record(source: dict[str, Any]) -> dict[str, Any] | None:
    row = {_key(key): value for key, value in source.items()}
    title = " ".join(str(_first(row, "name", "title", "novel title") or "").split()).strip()
    if not title:
        return None

    associated_names = _values(_first(row, "associated names", "associated_names", "alternative titles", "alternate titles"))
    authors = _values(_first(row, "author authors", "authors", "author"))
    genres = _values(_first(row, "genres", "genre"))
    tags = _values(_first(row, "tags", "tag"))
    original_complete = _boolean(_first(
        row, "completed original language", "completed original", "original completed", "completed_original",
    ))
    translation_complete = _boolean(_first(
        row, "completed translation", "translation completed", "completed_translation", "translation complete",
    ))
    licensed = _boolean(_first(row, "licensed", "is licensed", "licensed in english"))
    original_chapters = _first(
        row, "number of chapters original language", "original language chapters",
        "original chapters", "chapters original", "chapters_original",
    )
    translated_chapters = _first(
        row, "number of chapters translation", "translation chapters",
        "translated chapters", "chapters translated", "chapters_translated",
    )
    series_id = _first(row, "novel id", "novel_id", "series id", "series_id", "id")
    series_id = str(series_id).strip() if series_id is not None else None
    related_ids = _values(_first(row, "related series ids", "related_series_ids", "related series"))
    recommended_ids = _values(_first(row, "recommended series ids", "recommended_series_ids", "recommended series"))
    rating = _first(row, "rating", "average rating")
    rating_votes = _first(row, "rating votes", "rating_votes", "votes")
    reading_lists = _first(row, "on number of reading lists", "number of reading lists", "reading list count")
    frequency = _first(row, "release frequency", "release_frequency")
    weekly_rank = _first(row, "activity weekly rank", "weekly activity rank")
    monthly_rank = _first(row, "activity monthly rank", "monthly activity rank")
    all_time_rank = _first(row, "activity all time rank", "activity all-time rank", "all-time activity rank")
    reading_monthly_rank = _first(row, "reading list monthly rank", "reading_list_monthly_rank")
    reading_all_time_rank = _first(row, "reading list all time rank", "reading list all-time rank", "reading_list_all_time_rank")

    status = "Completed (translation)" if translation_complete is True else (
        "Translation ongoing" if translation_complete is False else None
    )
    result = {
        "title": title[:256],
        "url": _series_url(row, title),
        "description": str(_first(row, "description", "synopsis", "summary") or "").strip() or None,
        "image": _safe_cover(_first(row, "cover image url", "cover_image_url", "cover image", "image url", "cover")),
        "rating": str(rating).strip() if rating not in (None, "") else None,
        "rating_votes": rating_votes,
        "author": ", ".join(authors) or None,
        "authors": authors,
        "status": status,
        "platform": str(_first(row, "english publisher", "english_publisher", "original publisher", "original_publisher") or "").strip() or None,
        "genres": genres,
        "tags": tags,
        "novel_type": str(_first(row, "novel type", "novel_type", "type") or "").strip() or None,
        "associated_names": associated_names,
        "original_language": str(_first(row, "original language", "original langauge", "original_language", "language") or "").strip() or None,
        "start_year": _first(row, "start year", "start_year", "year"),
        "licensed": licensed,
        "original_publisher": str(_first(row, "original publisher", "original_publisher") or "").strip() or None,
        "english_publisher": str(_first(row, "english publisher", "english_publisher") or "").strip() or None,
        "original_chapters": original_chapters,
        "translated_chapters": translated_chapters,
        "original_completed": original_complete,
        "translation_completed": translation_complete,
        "release_frequency": str(frequency).strip() if frequency not in (None, "") else None,
        "activity_weekly_rank": weekly_rank,
        "activity_monthly_rank": monthly_rank,
        "activity_all_time_rank": all_time_rank,
        "reading_lists": reading_lists,
        "reading_list_monthly_rank": reading_monthly_rank,
        "reading_list_all_time_rank": reading_all_time_rank,
        "dataset_id": series_id,
        "related_series_ids": related_ids,
        "recommended_series_ids": recommended_ids,
        "recommendation_list_ids": _values(_first(row, "recommendation list ids", "recommendation_list_ids")),
        "metadata_source": "novel-dataset",
        "metadata_as_of": DATASET_UPDATED_AT,
        "_title_norm": _key(title),
        "_search_names": [_key(title), *[_key(name) for name in associated_names if _key(name)]],
        "_search_authors": _key(" ".join(authors)),
    }
    return result


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for name in ("novels", "data", "items", "records", "results"):
        value = next((v for k, v in payload.items() if _key(k) == name), None)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = [item for item in value.values() if isinstance(item, dict)]
            if nested:
                return nested
    if any(_key(key) in {"name", "title", "novel_id", "novelid"} for key in payload):
        return [payload]
    nested = [item for item in payload.values() if isinstance(item, dict)]
    return nested


def _read_dataset(path: Path) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > DATASET_MAX_BYTES:
            log.warning("Novel Updates dataset file exceeds the %s-byte safety limit: %s", DATASET_MAX_BYTES, path)
            return []
        if path.suffix.casefold() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                source_rows = list(csv.DictReader(handle))
        elif path.suffix.casefold() in {".json", ".jsonl"}:
            with path.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            source_rows = _extract_rows(payload)
        else:
            log.warning("Unsupported Novel Updates dataset extension: %s", path.suffix)
            return []
    except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, ValueError):
        log.warning("Could not read Novel Updates dataset at %s", path, exc_info=True)
        return []

    records = []
    for source in source_rows:
        try:
            record = _normalize_record(source)
        except (TypeError, ValueError):
            log.debug("Skipped an invalid Novel Updates dataset row", exc_info=True)
            continue
        if record:
            records.append(record)

    by_id = {
        record["dataset_id"]: record
        for record in records
        if record.get("dataset_id")
    }
    for record in records:
        for field, id_field in (
            ("related_series", "related_series_ids"),
            ("recommended_series", "recommended_series_ids"),
        ):
            linked = []
            for series_id in record.get(id_field) or []:
                target = by_id.get(str(series_id).strip())
                if target and target is not record:
                    linked.append({
                        "title": target["title"],
                        "url": target["url"],
                        "dataset_id": target.get("dataset_id"),
                    })
                if len(linked) >= 8:
                    break
            record[field] = linked
    return records


def _load_index(path_text: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    path = Path(path_text).expanduser()
    try:
        stat = path.stat()
    except OSError:
        return [], {}
    if not path.is_file():
        return [], {}

    with _CACHE_LOCK:
        cached = _CACHE.get(str(path.resolve()))
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2], cached[3]

    records = _read_dataset(path)
    by_id = {record["dataset_id"]: record for record in records if record.get("dataset_id")}
    with _CACHE_LOCK:
        _CACHE[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size, records, by_id)
    log.info("Loaded %s Novel Updates dataset records from %s", len(records), path)
    return records, by_id


def search_novelupdates_dataset(
    query: str,
    *,
    path: str | None = None,
    limit: int = 10,
    require_genres: bool = False,
) -> list[dict[str, Any]]:
    """Search a locally stored upstream dataset and return provider-shaped records."""
    normalized = _key(query)
    if not normalized:
        return []
    dataset_path = path or get_novelupdates_dataset_path()
    if not dataset_path:
        return []
    records, _ = _load_index(dataset_path)
    if not records:
        return []

    query_tokens = set(normalized.split("_"))
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for record in records:
        if require_genres and not record.get("genres"):
            continue
        names = record.get("_search_names") or []
        score = 0
        if normalized in names:
            score = 200
        else:
            for name in names:
                if name.startswith(normalized):
                    score = max(score, 160)
                elif normalized in name:
                    score = max(score, 135)
                else:
                    name_tokens = set(name.split("_"))
                    overlap = len(query_tokens & name_tokens)
                    if overlap:
                        coverage = overlap / max(1, len(query_tokens))
                        precision = overlap / max(1, len(name_tokens))
                        score = max(score, int(90 * coverage + 25 * precision))
            author_text = record.get("_search_authors") or ""
            if author_text and normalized in author_text:
                score = max(score, 55)

        if score < 35:
            continue
        try:
            all_time_rank = int(record.get("activity_all_time_rank"))
        except (TypeError, ValueError):
            all_time_rank = 1_000_000
        scored.append((score, -max(0, all_time_rank), record))

    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    maximum = max(1, min(int(limit), 25))
    results = []
    for _, _, record in scored[:maximum]:
        clean = {key: value for key, value in record.items() if not key.startswith("_")}
        results.append(clean)
    return results


def novelupdates_dataset_status() -> dict[str, Any]:
    """Return a small status record suitable for diagnostics and help output."""
    path = get_novelupdates_dataset_path()
    if not path:
        return {
            "enabled": False,
            "path": None,
            "version": DATASET_VERSION,
            "upstream": UPSTREAM_REPOSITORY,
        }
    try:
        stat = Path(path).expanduser().stat()
        records, _ = _load_index(path)
        return {
            "enabled": bool(records),
            "path": path,
            "records": len(records),
            "size_bytes": stat.st_size,
            "version": DATASET_VERSION,
            "updated_at": DATASET_UPDATED_AT,
            "upstream": UPSTREAM_REPOSITORY,
        }
    except OSError:
        return {
            "enabled": False,
            "path": path,
            "version": DATASET_VERSION,
            "upstream": UPSTREAM_REPOSITORY,
        }
