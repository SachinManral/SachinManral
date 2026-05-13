#!/usr/bin/env python3
"""Generate self-hosted GitHub profile stats cards as SVG files."""

from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


USERNAME = os.environ.get("GH_USERNAME", "SachinManral")
TOKEN = os.environ.get("GITHUB_TOKEN")
API_ROOT = "https://api.github.com"
MAX_ATTEMPTS = 4
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}

BG = "#0d1117"
GREEN = "#22c55e"
TEXT = "#ffffff"
MUTED = "#88d498"
SUBTLE = "#8b949e"
BORDER = "#22c55e"


class GitHubAPIError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


def github_get(path: str) -> object:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SachinManral-profile-stats",
        },
    )
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            retryable = exc.code in RETRYABLE_HTTP_STATUS
            if retryable and attempt < MAX_ATTEMPTS:
                time.sleep(attempt * 3)
                continue
            raise GitHubAPIError(
                f"GitHub API request failed: {path} ({exc.code}) {detail}",
                retryable=retryable,
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt * 3)
                continue
            raise GitHubAPIError(
                f"GitHub API request failed: {path} ({exc.reason})",
                retryable=True,
            ) from exc

    raise GitHubAPIError(f"GitHub API request failed: {path}", retryable=True)


def get_all_repos() -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        data = github_get(
            f"/users/{USERNAME}/repos?per_page=100&page={page}&sort=updated&type=owner"
        )
        if not isinstance(data, list):
            raise RuntimeError("Unexpected GitHub API response while reading repositories")
        repos.extend(data)
        if len(data) < 100:
            return repos
        page += 1


def get_languages(repos: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        path = languages_url.replace(API_ROOT, "")
        languages = github_get(path)
        if not isinstance(languages, dict):
            continue
        for language, bytes_count in languages.items():
            totals[language] = totals.get(language, 0) + int(bytes_count)
    return totals


def write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def existing_cards_are_available() -> bool:
    return Path("profile/stats.svg").is_file() and Path("profile/top-langs.svg").is_file()


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt(number: int | None) -> str:
    if number is None:
        return "0"
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(number)


def stat_row(label: str, value: object, y: int) -> str:
    return (
        f'<text x="32" y="{y}" fill="{MUTED}" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="15">{esc(label)}</text>'
        f'<text x="438" y="{y}" fill="{TEXT}" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="15" font-weight="700" text-anchor="end">{esc(value)}</text>'
    )


def generate_stats_card(user: dict, repos: list[dict]) -> str:
    owned_repos = [repo for repo in repos if not repo.get("fork")]
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in owned_repos)
    forks = sum(int(repo.get("forks_count") or 0) for repo in owned_repos)
    watchers = sum(int(repo.get("watchers_count") or 0) for repo in owned_repos)

    rows = [
        ("Public repositories", fmt(user.get("public_repos"))),
        ("Total stars earned", fmt(stars)),
        ("Repository forks", fmt(forks)),
        ("Followers", fmt(user.get("followers"))),
        ("Profile watchers", fmt(watchers)),
    ]

    row_markup = "\n  ".join(stat_row(label, value, 90 + index * 23) for index, (label, value) in enumerate(rows))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-labelledby="title desc">
  <title id="title">GitHub Stats</title>
  <desc id="desc">Self-hosted GitHub profile statistics for {esc(USERNAME)}.</desc>
  <rect width="495" height="195" rx="8" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="494" height="194" rx="8" fill="none" stroke="{BORDER}" stroke-opacity="0.25"/>
  <text x="32" y="44" fill="{GREEN}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">{esc(USERNAME)}'s GitHub Stats</text>
  <text x="32" y="66" fill="{SUBTLE}" font-family="Segoe UI, Arial, sans-serif" font-size="13">Generated daily with GitHub Actions</text>
  {row_markup}
</svg>
"""


def language_bar(language: str, percent: float, y: int, color: str) -> str:
    width = max(2, int(204 * percent / 100))
    return f"""<text x="24" y="{y}" fill="{TEXT}" font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="600">{esc(language)}</text>
  <text x="276" y="{y}" fill="{SUBTLE}" font-family="Segoe UI, Arial, sans-serif" font-size="12" text-anchor="end">{percent:.1f}%</text>
  <rect x="24" y="{y + 7}" width="252" height="7" rx="3.5" fill="#161b22"/>
  <rect x="24" y="{y + 7}" width="{width}" height="7" rx="3.5" fill="{color}"/>"""


def generate_languages_card(languages: dict[str, int]) -> str:
    colors = ["#22c55e", "#38bdf8", "#f97316", "#a78bfa", "#facc15", "#fb7185", "#14b8a6", "#e879f9"]
    total = sum(languages.values()) or 1
    top_languages = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:5]
    if not top_languages:
        top_languages = [("No language data", 1)]

    bars = "\n  ".join(
        language_bar(language, bytes_count * 100 / total, 72 + index * 24, colors[index % len(colors)])
        for index, (language, bytes_count) in enumerate(top_languages)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="195" viewBox="0 0 300 195" role="img" aria-labelledby="title desc">
  <title id="title">Top Languages</title>
  <desc id="desc">Top repository languages for {esc(USERNAME)}.</desc>
  <rect width="300" height="195" rx="8" fill="{BG}"/>
  <rect x="0.5" y="0.5" width="299" height="194" rx="8" fill="none" stroke="{BORDER}" stroke-opacity="0.25"/>
  <text x="24" y="42" fill="{GREEN}" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700">Top Languages</text>
  <text x="24" y="61" fill="{SUBTLE}" font-family="Segoe UI, Arial, sans-serif" font-size="12">Generated from public repositories</text>
  {bars}
</svg>
"""


def main() -> int:
    try:
        user = github_get(f"/users/{USERNAME}")
        if not isinstance(user, dict):
            raise RuntimeError("Unexpected GitHub API response while reading user")

        repos = get_all_repos()
        languages = get_languages(repos)

        write("profile/stats.svg", generate_stats_card(user, repos))
        write("profile/top-langs.svg", generate_languages_card(languages))
        print(f"Generated stats cards for {USERNAME}")
        return 0
    except GitHubAPIError as error:
        if error.retryable and existing_cards_are_available():
            print(f"::warning::{error}")
            print("Keeping existing stats cards because GitHub returned a temporary error.")
            return 0
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
