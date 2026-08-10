#!/usr/bin/env python3
"""Generate light and dark GitHub activity dashboard SVGs."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

GRAPHQL_URL = "https://api.github.com/graphql"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            date
            weekday
            contributionCount
            contributionLevel
          }
        }
      }
    }
  }
}
"""

THEMES = {
    "light": {
        "background": "#F6F8FA",
        "card": "#FFFFFF",
        "border": "#D0D7DE",
        "text": "#1F2328",
        "muted": "#656D76",
        "accent": "#6B5CA5",
        "levels": ["#EBEDF0", "#D9D4E7", "#B8ACCF", "#9084B8", "#6B5CA5"],
    },
    "dark": {
        "background": "#0D1117",
        "card": "#161B22",
        "border": "#30363D",
        "text": "#F0F6FC",
        "muted": "#8B949E",
        "accent": "#B7A8E3",
        "levels": ["#21262D", "#3A3154", "#5A4B7A", "#806DB0", "#B7A8E3"],
    },
}

LEVEL_INDEX = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}


def github_graphql(token: str, login: str) -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=364)
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": login,
                "from": start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "to": now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat(),
            },
        }
    ).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-activity-dashboard",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub GraphQL request failed ({exc.code}): {message}") from exc

    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {result['errors']}")
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {login}")
    return user["contributionsCollection"]


def streaks(days: list[dict]) -> tuple[int, int]:
    counts = {date.fromisoformat(day["date"]): day["contributionCount"] for day in days}
    active_dates = sorted(day for day, count in counts.items() if count > 0)
    if not active_dates:
        return 0, 0

    longest = 1
    run = 1
    for previous, current in zip(active_dates, active_dates[1:]):
        if current == previous + timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    today = datetime.now(timezone.utc).date()
    latest = active_dates[-1]
    current = 0
    if latest >= today - timedelta(days=1):
        cursor = latest
        while counts.get(cursor, 0) > 0:
            current += 1
            cursor -= timedelta(days=1)
    return current, longest


def month_labels(weeks: list[dict]) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    previous_month: int | None = None
    for index, week in enumerate(weeks):
        week_dates = [date.fromisoformat(day["date"]) for day in week["contributionDays"]]
        if not week_dates:
            continue
        candidate = next((day for day in week_dates if day.day <= 7), None)
        if candidate and candidate.month != previous_month:
            labels.append((index, f"{candidate.month}월"))
            previous_month = candidate.month
    return labels


def svg_text(x: int, y: int, text: str, css_class: str, anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" class="{css_class}" text-anchor="{anchor}">{escape(text)}</text>'


def render_dashboard(collection: dict, username: str, theme_name: str) -> str:
    theme = THEMES[theme_name]
    calendar = collection["contributionCalendar"]
    weeks = calendar["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    active_days = sum(day["contributionCount"] > 0 for day in days)
    current_streak, longest_streak = streaks(days)

    metrics = [
        ("총 기여", f'{calendar["totalContributions"]:,}'),
        ("활동일", f"{active_days:,}일"),
        ("커밋", f'{collection["totalCommitContributions"]:,}'),
        ("Pull Request", f'{collection["totalPullRequestContributions"]:,}'),
    ]

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(username)} GitHub 활동 대시보드</title>',
        '<desc id="desc">최근 12개월의 기여, 활동일, 커밋, Pull Request, 연속 활동과 기여 히트맵</desc>',
        "<style>",
        "text { font-family: Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
        ".title { font-size: 24px; font-weight: 700; }",
        ".subtitle { font-size: 13px; font-weight: 500; }",
        ".metric-value { font-size: 28px; font-weight: 750; }",
        ".metric-label { font-size: 13px; font-weight: 600; }",
        ".section { font-size: 15px; font-weight: 700; }",
        ".small { font-size: 12px; font-weight: 500; }",
        ".status-dot { animation: pulse 2.8s ease-in-out infinite; transform-box: fill-box; transform-origin: center; }",
        "@keyframes pulse { 0%, 100% { opacity: .45; transform: scale(.8); } 50% { opacity: 1; transform: scale(1); } }",
        "@media (prefers-reduced-motion: reduce) { .status-dot { animation: none; } }",
        f'.title, .metric-value, .section {{ fill: {theme["text"]}; }}',
        f'.subtitle, .metric-label, .small {{ fill: {theme["muted"]}; }}',
        "</style>",
        f'<rect x="1" y="1" width="1198" height="428" rx="24" fill="{theme["background"]}" stroke="{theme["border"]}"/>',
        f'<circle class="status-dot" cx="42" cy="42" r="6" fill="{theme["accent"]}"/>',
        svg_text(58, 49, "GitHub 활동", "title"),
        svg_text(1160, 47, f"최근 12개월 · {datetime.now(timezone.utc).strftime('%Y.%m.%d')} 갱신", "subtitle", "end"),
    ]

    card_x = [40, 325, 610, 895]
    for x, (label, value) in zip(card_x, metrics):
        parts.extend(
            [
                f'<rect x="{x}" y="72" width="265" height="92" rx="16" fill="{theme["card"]}" stroke="{theme["border"]}"/>',
                svg_text(x + 20, 117, value, "metric-value"),
                svg_text(x + 20, 143, label, "metric-label"),
            ]
        )

    parts.extend(
        [
            f'<rect x="40" y="188" width="1120" height="202" rx="16" fill="{theme["card"]}" stroke="{theme["border"]}"/>',
            svg_text(64, 222, "기여 히트맵", "section"),
            svg_text(1136, 222, f"현재 연속 {current_streak}일  ·  최장 연속 {longest_streak}일", "subtitle", "end"),
        ]
    )

    grid_x, grid_y, cell, gap = 175, 258, 12, 3
    for week_index, label in month_labels(weeks):
        x = grid_x + week_index * (cell + gap)
        parts.append(svg_text(x, 248, label, "small"))

    weekday_labels = {1: "월", 3: "수", 5: "금"}
    for weekday, label in weekday_labels.items():
        y = grid_y + weekday * (cell + gap) + 10
        parts.append(svg_text(grid_x - 18, y, label, "small", "end"))

    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = grid_x + week_index * (cell + gap)
            y = grid_y + day["weekday"] * (cell + gap)
            color = theme["levels"][LEVEL_INDEX.get(day["contributionLevel"], 0)]
            tooltip = f'{day["date"]}: {day["contributionCount"]} contributions'
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{color}"><title>{escape(tooltip)}</title></rect>'
            )

    legend_y = 375
    parts.append(svg_text(946, legend_y + 9, "적음", "small", "end"))
    for index, color in enumerate(theme["levels"]):
        parts.append(
            f'<rect x="{958 + index * 18}" y="{legend_y}" width="12" height="12" rx="3" fill="{color}"/>'
        )
    parts.append(svg_text(1058, legend_y + 9, "많음", "small"))

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--output-dir", default="dist")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN or GH_TOKEN is required")
    if not args.username:
        raise SystemExit("--username or GITHUB_REPOSITORY_OWNER is required")

    collection = github_graphql(token, args.username)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for theme_name in THEMES:
        suffix = "" if theme_name == "light" else "-dark"
        output_path = output_dir / f"github-activity-dashboard{suffix}.svg"
        output_path.write_text(render_dashboard(collection, args.username, theme_name), encoding="utf-8")
        print(f"generated {output_path}")


if __name__ == "__main__":
    main()
