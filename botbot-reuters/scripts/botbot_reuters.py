#!/usr/bin/env python3
import argparse
import email.utils
import json
import os
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.etree import ElementTree as ET


DEFAULT_FEED_URL = "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"
DEFAULT_TIMEOUT_SECONDS = 20


class CliError(RuntimeError):
    pass


@dataclass
class ConfigPaths:
    path: Path

    @staticmethod
    def resolve(explicit_path: str | None) -> "ConfigPaths":
        if explicit_path:
            return ConfigPaths(Path(explicit_path).expanduser())
        botbot_home = os.getenv("BOTBOT_HOME")
        if botbot_home:
            return ConfigPaths(Path(botbot_home).expanduser() / "botbot-reuters.json")
        return ConfigPaths(Path.home() / ".botbot" / "botbot-reuters.json")


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON config: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CliError(f"invalid config type in {path}: expected JSON object")
    return raw


def _strip_html(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    squashed = re.sub(r"\s+", " ", no_tags).strip()
    return unescape(squashed)


def _child_text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _format_date(value: str) -> str:
    raw = value.strip()
    if not raw:
        return "unknown-date, ???"
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return f"{dt:%Y-%m-%d}, {dt:%a}"
    except (TypeError, ValueError):
        return f"{raw}, ???"


def _atom_child_text(node: ET.Element, tag: str) -> str:
    ns = "{http://www.w3.org/2005/Atom}"
    child = node.find(f"{ns}{tag}")
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_entries(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    items: list[dict[str, str]] = []

    if root.tag == "rss" or root.tag.endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return items
        for node in channel.findall("item"):
            items.append(
                {
                    "title": _child_text(node, "title"),
                    "link": _child_text(node, "link"),
                    "published": _child_text(node, "pubDate"),
                    "summary": _strip_html(_child_text(node, "description")),
                }
            )
        return items

    ns = "{http://www.w3.org/2005/Atom}"
    if root.tag == f"{ns}feed":
        for node in root.findall(f"{ns}entry"):
            link = ""
            link_node = node.find(f"{ns}link")
            if link_node is not None:
                link = str(link_node.attrib.get("href", "")).strip()
            items.append(
                {
                    "title": _atom_child_text(node, "title"),
                    "link": link,
                    "published": _atom_child_text(node, "updated") or _atom_child_text(node, "published"),
                    "summary": _strip_html(_atom_child_text(node, "summary")),
                }
            )
        return items

    raise CliError("unsupported feed format")


def _fetch_feed(url: str, timeout_seconds: int) -> bytes:
    try:
        with urlopen(url, timeout=timeout_seconds) as resp:
            return resp.read()
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code} for {url}: {details}") from exc
    except URLError as exc:
        raise CliError(f"network error for {url}: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botbot-reuters", description="Print Reuters headlines from RSS")
    parser.add_argument("--config", help="Path to botbot-reuters.json config")
    parser.add_argument("--limit", type=int, help="Max items to print (default: all available)")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg_path = ConfigPaths.resolve(args.config).path
    try:
        cfg = _read_json_if_exists(cfg_path)
        feed_url = str(cfg.get("feed_url") or DEFAULT_FEED_URL).strip()
        timeout_seconds = int(cfg.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        limit_val = args.limit if args.limit is not None else cfg.get("limit")
        limit = None if limit_val is None else int(limit_val)
        if limit is not None and limit < 1:
            raise CliError("limit must be >= 1")
        if timeout_seconds < 1:
            raise CliError("timeout_seconds must be >= 1")

        entries = _parse_entries(_fetch_feed(feed_url, timeout_seconds))
        if not entries:
            print("No Reuters news items found.")
            return 0

        to_print = entries if limit is None else entries[:limit]
        for item in to_print:
            published = _format_date(item["published"])
            summary = item["summary"] or item["title"] or "(no summary)"
            print(f"{published}, {summary}")
        return 0
    except (CliError, ET.ParseError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
