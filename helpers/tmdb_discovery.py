"""Pure query construction for TMDB movie and TV discovery."""
from __future__ import annotations

import re
from typing import Dict, Optional

TMDB_MOVIE_GENRES = {
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
    "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
    "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
    "mystery": 9648, "romance": 10749, "science fiction": 878,
    "sci fi": 878, "thriller": 53, "war": 10752, "western": 37,
    "tv movie": 10770,
}
TMDB_TV_GENRES = {
    "action": 10759, "action and adventure": 10759, "adventure": 10759,
    "animation": 16, "comedy": 35, "crime": 80, "documentary": 99,
    "drama": 18, "family": 10751, "kids": 10762, "mystery": 9648,
    "news": 10763, "reality": 10764, "science fiction and fantasy": 10765,
    "sci fi and fantasy": 10765, "soap": 10766, "talk": 10767,
    "war and politics": 10768, "western": 37,
}
TMDB_SORT_OPTIONS = {
    "popularity": "popularity.desc",
    "rating": "vote_average.desc",
    "votes": "vote_count.desc",
}
TMDB_TV_STATUS_IDS = {
    "returning": 0, "returning series": 0, "ongoing": 0, "in progress": 0,
    "planned": 1, "upcoming": 1, "in production": 2,
    "ended": 3, "completed": 3, "complete": 3,
    "cancelled": 4, "canceled": 4, "pilot": 5,
}


def build_tmdb_discover_params(
    media_type: str,
    *,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    status: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    runtime_min: Optional[int] = None,
    runtime_max: Optional[int] = None,
    minimum_rating: Optional[float] = None,
    sort_by: str = "popularity",
    include_adult: bool = False,
    region: str = "IE",
    keyword_id: Optional[int] = None,
    director_id: Optional[int] = None,
    cast_id: Optional[int] = None,
) -> Dict:
    """Build a validated TMDB discover query for the /browse title-free flow."""
    category = (media_type or "").strip().upper()
    if category not in {"MOVIE", "TV"}:
        raise ValueError("Title-free discovery supports Movies and TV Shows only.")
    sort_key = (sort_by or "popularity").strip().casefold()
    if sort_key not in {*TMDB_SORT_OPTIONS, "newest"}:
        raise ValueError("Choose a sort order: popularity, rating, votes, or newest.")

    params: Dict = {
        "language": "en-US",
        "page": 1,
        "include_adult": str(bool(include_adult)).lower(),
        "sort_by": (
            "primary_release_date.desc" if category == "MOVIE" else "first_air_date.desc"
        ) if sort_key == "newest" else TMDB_SORT_OPTIONS[sort_key],
    }
    if genre and genre.strip():
        normalized_genre = re.sub(
            r"[\s-]+", " ", genre.strip().casefold().replace("&", " and ")
        ).strip()
        genres = TMDB_MOVIE_GENRES if category == "MOVIE" else TMDB_TV_GENRES
        genre_id = genres.get(normalized_genre)
        if genre_id is None:
            raise ValueError(f"TMDB does not expose {genre!r} as a supported {category.lower()} genre.")
        params["with_genres"] = genre_id
    if keyword_id is not None:
        params["with_keywords"] = int(keyword_id)
    if director_id is not None:
        params["with_crew"] = int(director_id)
    if cast_id is not None:
        params["with_cast"] = int(cast_id)
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("The earliest year cannot be later than the latest year.")
    date_key = "primary_release_date" if category == "MOVIE" else "first_air_date"
    if year_from is not None:
        params[f"{date_key}.gte"] = f"{int(year_from):04d}-01-01"
    if year_to is not None:
        params[f"{date_key}.lte"] = f"{int(year_to):04d}-12-31"
    if language and language.strip():
        language_code = language.strip().casefold()
        if not re.fullmatch(r"[a-z]{2}", language_code):
            raise ValueError("Original language must be a two-letter code, such as en, ja, ko, or fr.")
        params["with_original_language"] = language_code
    if runtime_min is not None:
        params["with_runtime.gte"] = int(runtime_min)
    if runtime_max is not None:
        params["with_runtime.lte"] = int(runtime_max)
    if runtime_min is not None and runtime_max is not None and runtime_min > runtime_max:
        raise ValueError("The minimum runtime cannot exceed the maximum runtime.")
    if minimum_rating is not None:
        rating = float(minimum_rating)
        if not 0 <= rating <= 10:
            raise ValueError("Minimum rating must be between 0 and 10.")
        params["vote_average.gte"] = rating
    if sort_key == "rating":
        params["vote_count.gte"] = 50
    if status:
        if category == "MOVIE":
            raise ValueError("TMDB movie discovery does not expose a direct status filter. Use the release-year filters instead.")
        status_key = re.sub(r"[\s-]+", " ", status.strip().casefold())
        status_id = TMDB_TV_STATUS_IDS.get(status_key)
        if status_id is None:
            raise ValueError("Unsupported TV status. Use returning, planned, in production, ended, cancelled, or pilot.")
        params["with_status"] = status_id
    country = (region or "IE").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("Region must be a two-letter country code, such as IE, GB, or US.")
    if category == "MOVIE":
        params["region"] = country
    return params
