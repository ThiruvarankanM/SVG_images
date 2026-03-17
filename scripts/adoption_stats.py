"""Jac adoption stats collector.

Fetches PyPI download stats and GitHub code search results to track Jac adoption.
Outputs a markdown report to stdout (captured as GitHub Step Summary or file).

Usage:
    python scripts/adoption_stats.py
    python scripts/adoption_stats.py --output report.md

Requires:
    GITHUB_TOKEN env var for GitHub API (higher rate limits, required for code search)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

# PyPI package names — sourced from release_utils.py PACKAGES registry
PYPI_PACKAGES = [
    "jaclang",
    "byllm",
    "jac-client",
    "jac-scale",
    "jac-super",
    "jac-mcp",
    "jaseci",
]

# GitHub code/repo searches to find Jac usage in the wild
GITHUB_SEARCHES = [
    {
        "label": "Public `.jac` files",
        "type": "code",
        "query": "extension:jac language:Jac",
    },
    {
        "label": "Repos importing `jaclang`",
        "type": "code",
        "query": "import jaclang",
    },
    {
        "label": "Repos with `jac-lang` topic",
        "type": "repositories",
        "query": "topic:jac-lang",
    },
    {
        "label": "Repos with `jaseci` topic",
        "type": "repositories",
        "query": "topic:jaseci",
    },
]


def _get(url: str, token: str | None = None) -> dict:
    """GET a JSON endpoint, return parsed body or error dict."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "jaseci-adoption-stats/1.0")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": str(e)}


def fetch_pypi_recent(package: str) -> dict:
    """Fetch last-day/last-week/last-month downloads from pypistats.org."""
    return _get(f"https://pypistats.org/api/packages/{package}/recent")


def fetch_pypi_overall(package: str) -> dict:
    """Fetch total (with and without mirrors) downloads from pypistats.org."""
    return _get(f"https://pypistats.org/api/packages/{package}/overall")


def fetch_github_search(search: dict, token: str | None) -> int | None:
    """Return total_count for a GitHub code or repo search. None on error."""
    search_type = search["type"]
    query = urllib.parse.quote(search["query"])
    url = f"https://api.github.com/search/{search_type}?q={query}&per_page=1"
    data = _get(url, token)
    if "_error" in data:
        return None
    return data.get("total_count")


def fetch_public_repos_using_jac(token: str | None, max_pages: int = 5) -> list[dict]:
    """Fetch public repos that import jaclang or contain .jac files.

    Paginates through GitHub code search results and deduplicates by repo.
    Returns list of dicts with repo name, url, description, and stars.
    """
    seen: set[str] = set()
    repos: list[dict] = []

    queries = [
        "import jaclang",
        "extension:jac language:Jac",
    ]

    for query in queries:
        encoded = urllib.parse.quote(query)
        for page in range(1, max_pages + 1):
            url = (
                f"https://api.github.com/search/code"
                f"?q={encoded}&per_page=100&page={page}"
            )
            data = _get(url, token)
            if "_error" in data or not data.get("items"):
                break
            for item in data["items"]:
                repo = item.get("repository", {})
                full_name = repo.get("full_name", "")
                if full_name and full_name not in seen:
                    seen.add(full_name)
                    repos.append(
                        {
                            "full_name": full_name,
                            "url": repo.get("html_url", ""),
                            "description": repo.get("description") or "",
                            "stars": repo.get("stargazers_count", 0),
                        }
                    )
            # GitHub code search caps at 1000 results total
            if len(data.get("items", [])) < 100:
                break

    # Sort by stars descending
    repos.sort(key=lambda r: r["stars"], reverse=True)
    return repos


def build_pypi_table(results: list[dict]) -> str:
    """Render PyPI stats as a markdown table."""
    rows = []
    for r in results:
        pkg = r["package"]
        if "error" in r:
            rows.append(f"| `{pkg}` | — | — | — | _{r['error']}_ |")
            continue
        last_day = r.get("last_day", "—")
        last_week = r.get("last_week", "—")
        last_month = r.get("last_month", "—")
        total = r.get("total", "—")
        rows.append(
            f"| `{pkg}` "
            f"| {last_day:,} "
            f"| {last_week:,} "
            f"| {last_month:,} "
            f"| {total:,} |"
            if isinstance(last_day, int)
            else f"| `{pkg}` | {last_day} | {last_week} | {last_month} | {total} |"
        )
    header = (
        "| Package | Last Day | Last Week | Last Month | All-time Total |\n"
        "|---------|----------|-----------|------------|----------------|"
    )
    return header + "\n" + "\n".join(rows)


def build_repos_table(repos: list[dict]) -> str:
    """Render public repo list as a markdown table."""
    if not repos:
        return "_No public repositories found._"
    header = (
        "| Repository | Stars | Description |\n"
        "|------------|-------|-------------|"
    )
    rows = []
    for r in repos:
        name = r["full_name"]
        url = r["url"]
        stars = r["stars"]
        desc = r["description"][:80] + "…" if len(r["description"]) > 80 else r["description"]
        rows.append(f"| [{name}]({url}) | {stars:,} | {desc} |")
    return header + "\n" + "\n".join(rows)


def build_github_table(results: list[dict]) -> str:
    """Render GitHub search results as a markdown table."""
    rows = []
    for r in results:
        count = r["count"]
        label = r["label"]
        query = r["query"]
        encoded = urllib.parse.quote(r["query"])
        search_type = r["type"]
        url = f"https://github.com/search?q={encoded}&type={search_type}"
        if count is None:
            rows.append(f"| {label} | `{query}` | _(rate limited or error)_ |")
        else:
            rows.append(f"| {label} | `{query}` | [{count:,}]({url}) |")
    header = (
        "| Signal | Search Query | Count |\n"
        "|--------|-------------|-------|"
    )
    return header + "\n" + "\n".join(rows)


def generate_report(token: str | None) -> str:
    """Collect all stats and return a full markdown report."""
    today = date.today().isoformat()

    # --- PyPI stats ---
    pypi_results = []
    for pkg in PYPI_PACKAGES:
        recent = fetch_pypi_recent(pkg)
        overall = fetch_pypi_overall(pkg)
        if "_error" in recent:
            pypi_results.append({"package": pkg, "error": recent["_error"]})
            continue
        recent_data = {d["category"]: d["downloads"] for d in recent.get("data", [])}
        without_mirrors = next(
            (
                d["downloads"]
                for d in overall.get("data", [])
                if not d.get("with_mirrors")
            ),
            None,
        )
        pypi_results.append(
            {
                "package": pkg,
                "last_day": recent_data.get("last_day", "—"),
                "last_week": recent_data.get("last_week", "—"),
                "last_month": recent_data.get("last_month", "—"),
                "total": without_mirrors or "—",
            }
        )

    # --- GitHub searches (counts) ---
    github_results = []
    for search in GITHUB_SEARCHES:
        count = fetch_github_search(search, token)
        github_results.append({**search, "count": count})

    # --- Public repos using Jac ---
    public_repos = fetch_public_repos_using_jac(token)

    # --- Assemble report ---
    lines = [
        f"# Jac Adoption Stats — {today}",
        "",
        "## PyPI Downloads",
        "",
        "> Source: [pypistats.org](https://pypistats.org) — excludes mirrors for total.",
        "",
        build_pypi_table(pypi_results),
        "",
        "## GitHub Presence",
        "",
        "> Source: GitHub Search API — public repos/files only.",
        "> Private repos and local projects are not captured here.",
        "",
        build_github_table(github_results),
        "",
        "## Public Repositories Using Jac",
        "",
        f"> Found **{len(public_repos)}** unique public repos containing `.jac` files or `import jaclang`.",
        "",
        build_repos_table(public_repos),
        "",
        "## Notes",
        "",
        "- **PyPI downloads** are the most reliable adoption signal — every `pip install` is counted.",
        "- **GitHub repo list** shows only public repos; private/local projects are invisible.",
        "- For qualitative data (who is building what), run a community survey.",
        "",
        f"_Report generated on {today} by [adoption_stats.py](../scripts/adoption_stats.py)_",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Jac adoption stats report")
    parser.add_argument(
        "--output",
        default="-",
        help="Output file path (default: stdout)",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "Warning: GITHUB_TOKEN not set — GitHub searches may be rate-limited.",
            file=sys.stderr,
        )

    report = generate_report(token)

    if args.output == "-":
        print(report)
    else:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
