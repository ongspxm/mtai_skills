#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TLDR_SENDER = "@tldrnewsletter.com"
TARGET_CHARS = 140
PENDING_PATH = Path("/tmp/meagent_tldr_newsletter_threads.json")
WS_RE = re.compile(r"\s+")


class CliError(RuntimeError):
    pass


def _gmail_cmd() -> list[str]:
    script = Path(__file__).resolve().parents[2] / "botbot-gmail" / "scripts" / "botbot_gmail.py"
    if not script.is_file():
        raise CliError("required dependency not installed: botbot-gmail")
    return ["uv", "run", str(script)]


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode:
        raise CliError(proc.stderr.strip() or proc.stdout.strip() or f"subprocess failed: {' '.join(cmd)}")
    return proc.stdout


def _clean_link(link: str) -> str:
    if link.startswith("https://links.tldrnewsletter.com"):
        try:
            with urlopen(Request(link, method="GET"), timeout=20) as resp:
                link = resp.geturl()
        except (HTTPError, URLError):
            pass
    for sep in ("?utm_", "&utm_"):
        if sep in link:
            return link.split(sep, 1)[0]
    return link


def _parse_items(body: str) -> dict[str, str]:
    main, _, rest = body.partition("\nLinks:")
    main = "".join(c if ord(c) < 128 else "_" for c in main)
    blocks = [b.replace("\n", " ").strip() for b in main.split("\n\n")]
    lines = [b for b in blocks if b]

    links: dict[int, str] = {}
    for ln in rest.splitlines():
        if "http" not in ln:
            continue
        parts = ln.strip().split(" ")
        if len(parts) < 2 or not parts[0].startswith("[") or not parts[0].endswith("]"):
            continue
        idx = parts[0][1:-1]
        if idx.isdigit():
            links[int(idx)] = _clean_link(parts[1].strip())

    out: dict[str, str] = {}
    cur_idx: int | None = None
    cur_header = ""
    for ln in lines:
        token = ln.split(" ")[-1]
        is_title = ln == ln.upper() and token.startswith("[") and token.endswith("]") and token[1:-1].isdigit()
        if is_title:
            cur_idx = int(token[1:-1])
            hdr = "=== " + ln
            if cur_idx in links:
                hdr = hdr.replace(f"[{cur_idx}]", f"[{cur_idx}]({links[cur_idx]})", 1)
            cur_header = hdr
            continue
        if cur_idx is None:
            continue
        desc = WS_RE.sub(" ", ln.strip())
        if len(desc) > TARGET_CHARS:
            desc = desc[: TARGET_CHARS - 3].rstrip() + "..."
        item = f"{cur_header}\n{desc}"
        key = cur_header
        if "https://" in cur_header:
            key = "https://" + cur_header.split("https://", 1)[1].split(")", 1)[0].split(" ", 1)[0]
        out[key] = item
        cur_idx = None
    return out


def _collect() -> tuple[list[str], dict[str, str]]:
    gmail = _gmail_cmd()
    rows = []
    for ln in _run(gmail + ["ls", "in:INBOX"]).splitlines():
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        if isinstance(row, dict):
            rows.append(row)
    rows.sort(key=lambda r: int(r.get("tstamp") or 0), reverse=True)

    tids: list[str] = []
    items: dict[str, str] = {}
    for row in rows:
        frm = str(row.get("from") or "").lower()
        tid = str(row.get("threadid") or "").strip()
        if TLDR_SENDER not in frm or not tid:
            continue
        if tid not in tids:
            tids.append(tid)
        body = "\n".join(x.strip() for x in _run(gmail + ["read", tid]).splitlines())
        items.update(_parse_items(body))
    return tids, items


def cmd_read(_: argparse.Namespace) -> int:
    tids, items = _collect()
    PENDING_PATH.write_text(json.dumps({"thread_ids": tids}, separators=(",", ":")), encoding="utf-8")
    print("\n\n".join(items.values()) if items else "no newsletter found")
    return 0


def cmd_trash(_: argparse.Namespace) -> int:
    if not PENDING_PATH.exists():
        raise CliError("no confirmed newsletter batch found; run read first, show raw output, wait for 'ok'")
    try:
        payload = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid pending batch file: {PENDING_PATH}") from exc
    raw_ids = payload.get("thread_ids") if isinstance(payload, dict) else None
    if not isinstance(raw_ids, list):
        raise CliError(f"invalid pending batch schema: {PENDING_PATH}")
    tids, seen = [], set()
    for raw in raw_ids:
        tid = str(raw).strip()
        if tid and tid not in seen:
            seen.add(tid)
            tids.append(tid)
    if not tids:
        raise CliError("pending newsletter batch is empty; run read again")

    gmail = _gmail_cmd()
    for tid in tids:
        _run(gmail + ["del", tid])
    PENDING_PATH.unlink(missing_ok=True)
    print(json.dumps({"status": "newsletter read and trashed", "count": len(tids)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read TLDR newsletters and trash confirmed batch")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("read").set_defaults(func=cmd_read)
    sub.add_parser("trash").set_defaults(func=cmd_trash)
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except CliError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
