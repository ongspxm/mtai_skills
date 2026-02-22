#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, unquote
from urllib.request import Request, urlopen

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
RESULT_LIMIT = 20
ANCHOR_RE = re.compile(
    r"<a(?P<attrs>[^>]*class=['\"]result-link['\"][^>]*)>(?P<title>.*?)</a>",
    flags=re.S,
)
HREF_RE = re.compile(r"href=['\"]([^'\"]+)['\"]", flags=re.S)
SNIPPET_RE = re.compile(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", flags=re.S)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text))).strip()


def to_result_url(href: str) -> str:
    raw = html.unescape(href).strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    uddg = parse_qs(urlparse(raw).query).get("uddg")
    return unquote(uddg[0]) if uddg and uddg[0] else raw


def fetch_page(query: str, market: str) -> str:
    url = f"{DDG_LITE_URL}?{urlencode({'q': query, 'kl': market.lower()})}"
    req = Request(url=url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*;q=0.8"})
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"network error for {url}: {exc}") from exc


def parse_results(page: str) -> list[dict[str, str]]:
    if "Unfortunately, bots use DuckDuckGo too" in page or "anomaly-modal" in page:
        raise RuntimeError("DuckDuckGo anti-bot challenge encountered; retry later")

    anchors = list(ANCHOR_RE.finditer(page))
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for i, match in enumerate(anchors):
        row_start = page.rfind("<tr", 0, match.start())
        if row_start != -1 and "result-sponsored" in page[row_start : match.start()]:
            continue

        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue

        link = to_result_url(href_match.group(1))
        title = clean(match.group("title"))
        if not title or not link or link in seen:
            continue

        next_start = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        snippet_match = SNIPPET_RE.search(page[match.end() : next_start])
        seen.add(link)
        results.append(
            {
                "title": title,
                "link": link,
                "description": clean(snippet_match.group(1)) if snippet_match else "",
            }
        )
        if len(results) >= RESULT_LIMIT:
            break

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search online facts and return link/title/description")
    parser.add_argument("query", help="search query")
    parser.add_argument("--market", default="en-US", help="language/market hint (default: en-US)")

    args = parser.parse_args(argv)
    query = args.query.strip()
    market = args.market.strip() or "en-US"
    if not query:
        print("error: query must not be empty", file=sys.stderr)
        return 2

    try:
        results = parse_results(fetch_page(query, market))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
