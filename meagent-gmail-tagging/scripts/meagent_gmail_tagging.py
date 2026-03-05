#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


QUEUE_PATH = Path("/tmp/tag_gmail.ndjson")
DEFAULT_FETCH_QUERY = 'in:INBOX AND NOT label:6.auto'
DEFAULT_RULES_LIST = "email_gps"
STATUS_BATCH_SIZE = 20

VALID_TAGS = {"action", "reading", "junk"}
GMAIL_LABELS = {
    "action": "0.action",
    "reading": "3.reading",
    "junk": "4.junk",
}
TAG_PRIORITY = ["action", "reading", "junk"]


class CliError(RuntimeError):
    pass


def _find_skill_script(skill_name: str, script_file: str) -> Path:
    # Current file is <skills-dir>/<this-skill>/scripts/meagent_gmail_tagging.py.
    # So ../../ is the main skills directory.
    path = Path(__file__).resolve().parents[2] / skill_name / "scripts" / script_file
    if path.exists() and path.is_file():
        return path
    raise CliError(
        f"required dependency not installed: {skill_name} ({script_file} not found in main skills dir)"
    )


def _run_stdout(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise CliError(f"subprocess failed ({' '.join(cmd)}): {detail}")
    return proc.stdout


def _gmail_base_cmd() -> list[str]:
    script = _find_skill_script("botbot-gmail", "botbot_gmail.py")
    return ["uv", "run", str(script)]


def _load_queue() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        raise CliError(f"queue not found: {QUEUE_PATH}; run fetch first")
    rows: list[dict[str, Any]] = []
    with QUEUE_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CliError(f"invalid NDJSON row in {QUEUE_PATH}") from exc
            rows.append(obj)
    return rows


def _save_queue(rows: list[dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_PATH.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def _print_rows(rows: list[dict[str, Any]], include_tag: bool = True) -> None:
    for row in rows:
        out = {
            "idx": row.get("idx"),
            "from": row.get("from", ""),
            "subject": row.get("subject", ""),
            "snippet": row.get("snippet", ""),
        }
        if include_tag:
            out["tag"] = row.get("tag", "")
        print(json.dumps(out, separators=(",", ":")))


def _ascii_only(text: str) -> str:
    return text.encode("ascii", errors="ignore").decode("ascii")


def _to_snippet(text: str, max_len: int = 240) -> str:
    clean = _ascii_only(text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_len]


def _clean_text(text: str) -> str:
    clean = _ascii_only(text)
    return re.sub(r"\s+", " ", clean).strip()


def _parse_tstamp_ms(value: Any) -> int:
    raw = str(value).strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    cmd = _gmail_base_cmd()
    cmd.extend(["ls", DEFAULT_FETCH_QUERY])
    lines = [ln for ln in _run_stdout(cmd).splitlines() if ln.strip()]

    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        tid = str(item.get("threadid", "")).strip()
        if not tid:
            continue
        labels = item.get("labels")
        normalized_labels = {str(x).strip().lower() for x in labels} if isinstance(labels, list) else set()
        if any(GMAIL_LABELS[tag].lower() in normalized_labels for tag in TAG_PRIORITY):
            continue
        rows.append(
            {
                "idx": len(rows),
                "subject": _clean_text(str(item.get("subject", ""))),
                "from": _ascii_only(str(item.get("from", ""))),
                "snippet": _to_snippet(str(item.get("snippet", ""))),
                "tstamp": _parse_tstamp_ms(item.get("tstamp")),
                "threadid": tid,
                "tag": "",
            }
        )

    # Enrich snippet only for rows that still need tagging.
    gmail_cmd = _gmail_base_cmd()
    targets = [
        row
        for row in rows
        if not str(row.get("tag", "")).strip()
        and not str(row.get("snippet", "")).strip()
        and str(row.get("threadid", "")).strip()
    ]
    if targets:
        workers = min(8, len(targets))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_row = {
                pool.submit(_run_stdout, gmail_cmd + ["read", str(row.get("threadid", "")).strip()]): row
                for row in targets
            }
            for fut in concurrent.futures.as_completed(future_to_row):
                row = future_to_row[fut]
                try:
                    body = fut.result().strip()
                except Exception:
                    body = ""
                row["snippet"] = _to_snippet(body)

    _save_queue(rows)
    if not rows:
        print("(no emails to tag)")
        return 0
    _print_rows(rows, include_tag=False)
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    base_rules = [
        "action: needs action from me (reply, confirm, submit, approve, follow-up)",
        "reading: newsletters/articles/updates to read later",
        "junk: promotions/spam/deals/low-value notifications",
    ]
    for line in base_rules:
        print(f"- {line}")

    cmd = ["uv", "run", str(_find_skill_script("botbot-gtask", "botbot_gtask.py"))]
    cmd.extend(["tasks", "--list", DEFAULT_RULES_LIST])
    raw = _run_stdout(cmd).strip()
    tasks: Any = []
    if raw:
        try:
            tasks = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid JSON from subprocess: {' '.join(cmd)}") from exc
    if isinstance(tasks, list):
        for t in tasks:
            title = str((t or {}).get("title", "")).strip()
            notes = str((t or {}).get("notes", "")).strip()
            if title and notes:
                print(f"- {title} = {notes}")
            elif title:
                print(f"- {title}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    idx = args.idx
    tag = args.tag.strip().lower()
    if tag not in VALID_TAGS:
        raise CliError(f"invalid tag '{args.tag}'; expected one of: action, reading, junk")
    rows = _load_queue()

    updated_row: dict[str, Any] | None = None
    for row in rows:
        if int(row.get("idx", -1)) == idx:
            row["tag"] = tag
            updated_row = row
            break

    if updated_row is None:
        raise CliError(f"idx not found in queue: {idx}")

    _save_queue(rows)
    _print_rows([updated_row], include_tag=True)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    rows = _load_queue()

    changed = False
    missing: list[int] = []
    for row in rows:
        idx = int(row.get("idx", -1))
        tag = str(row.get("tag", "")).strip().lower()
        if tag and tag not in VALID_TAGS:
            row["tag"] = ""
            changed = True
            tag = ""
        if not tag:
            missing.append(idx)

    if changed:
        _save_queue(rows)

    missing_set = set(missing)
    if missing_set:
        gmail_cmd = _gmail_base_cmd()
        enriched = False
        for row in rows:
            if int(row.get("idx", -1)) not in missing_set:
                continue
            if str(row.get("snippet", "")).strip():
                continue
            thread_id = str(row.get("threadid", "")).strip()
            if not thread_id:
                continue
            body = _run_stdout(gmail_cmd + ["read", thread_id]).strip()
            row["snippet"] = _to_snippet(body)
            enriched = True
        if enriched:
            _save_queue(rows)
        sample = [row for row in rows if int(row.get("idx", -1)) in missing_set]
        sample = sorted(sample, key=lambda r: int(r.get("idx", -1)))[:STATUS_BATCH_SIZE]
        print(f"{len(missing)} emails untagged, here is {len(sample)} of them.")
        _print_rows(sample, include_tag=False)
        print(
            f"this is {len(sample)}/{len(missing)} untagged email. "
            "pick the best tag for each and autotag them, call status with raw_output=false to get more after thats done"
        )
        return 0

    print("everything is tagged, review these tags")
    print("when all tagged run status with raw_output=True")

    grouped: dict[str, list[dict[str, Any]]] = {tag: [] for tag in TAG_PRIORITY}
    for row in rows:
        tag = str(row.get("tag", "")).strip().lower()
        if tag in grouped:
            grouped[tag].append(row)

    now_ms = int(time.time() * 1000)
    for tag in TAG_PRIORITY:
        items = sorted(grouped[tag], key=lambda r: int(r.get("idx", -1)))
        print(f"=== {tag} ({len(items)}) ===\n")
        for row in items:
            ts = _parse_tstamp_ms(row.get("tstamp"))
            if ts <= 0:
                age = "0D"
            else:
                age_days = max(0, (now_ms - ts) // 86_400_000)
                age = f"{max(1, age_days // 7)}W" if age_days > 9 else f"{age_days}D"
            print(f"{row.get('idx')}. {age}. {row.get('subject', '')} ({row.get('from', '')})")
        print("")
    return 0


def cmd_print(args: argparse.Namespace) -> int:
    gmail_cmd = _gmail_base_cmd()

    untagged_query = "in:INBOX AND NOT label:6.auto AND NOT (label:0.action OR label:3.reading OR label:4.junk)"
    untagged_lines = [ln for ln in _run_stdout(gmail_cmd + ["ls", untagged_query]).splitlines() if ln.strip()]
    untagged_rows: list[dict[str, Any]] = []
    for line in untagged_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        untagged_rows.append(
            {
                "idx": len(untagged_rows),
                "subject": _clean_text(str(item.get("subject", ""))),
                "from": _clean_text(str(item.get("from", ""))),
                "tstamp": _parse_tstamp_ms(item.get("tstamp")),
            }
        )

    print(f"=== untagged ({len(untagged_rows)}) ===")
    now_ms = int(time.time() * 1000)
    for row in sorted(untagged_rows, key=lambda r: int(r.get("idx", -1))):
        ts = _parse_tstamp_ms(row.get("tstamp"))
        if ts <= 0:
            age = "0D"
        else:
            age_days = max(0, (now_ms - ts) // 86_400_000)
            age = f"{max(1, age_days // 7)}W" if age_days > 9 else f"{age_days}D"
        print(f"{row.get('idx')}. {age}. {row.get('subject', '')} ({row.get('from', '')})")
    print("")

    tagged_query = "in:INBOX (label:0.action OR label:3.reading OR label:4.junk)"
    tagged_lines = [ln for ln in _run_stdout(gmail_cmd + ["ls", tagged_query]).splitlines() if ln.strip()]
    tagged_rows: list[dict[str, Any]] = []
    for line in tagged_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        labels = item.get("labels")
        normalized_labels = {str(x).strip().lower() for x in labels} if isinstance(labels, list) else set()
        tag = ""
        for candidate in TAG_PRIORITY:
            if GMAIL_LABELS[candidate].lower() in normalized_labels:
                tag = candidate
                break
        if not tag:
            continue
        tagged_rows.append(
            {
                "idx": len(tagged_rows),
                "subject": _clean_text(str(item.get("subject", ""))),
                "from": _clean_text(str(item.get("from", ""))),
                "tag": tag,
                "tstamp": _parse_tstamp_ms(item.get("tstamp")),
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = {tag: [] for tag in TAG_PRIORITY}
    for row in tagged_rows:
        grouped[str(row.get("tag", ""))].append(row)

    for tag in TAG_PRIORITY:
        items = sorted(grouped[tag], key=lambda r: int(r.get("idx", -1)))
        print(f"=== {tag} ({len(items)}) ===")
        for row in items:
            ts = _parse_tstamp_ms(row.get("tstamp"))
            if ts <= 0:
                age = "0D"
            else:
                age_days = max(0, (now_ms - ts) // 86_400_000)
                age = f"{max(1, age_days // 7)}W" if age_days > 9 else f"{age_days}D"
            print(f"{row.get('idx')}. {age}. {row.get('subject', '')} ({row.get('from', '')})")
        print("")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    rows = _load_queue()

    missing = [int(row.get("idx", -1)) for row in rows if str(row.get("tag", "")).strip().lower() not in VALID_TAGS]
    if missing:
        raise CliError("cannot push: missing tags for idx " + ", ".join(str(x) for x in missing))

    gmail_cmd = _gmail_base_cmd()
    labelled_count = 0
    removed_count = 0
    labels_removed_count = 0
    for row in rows:
        idx = int(row.get("idx", -1))
        tag = str(row.get("tag", "")).strip().lower()
        thread_id = str(row.get("threadid", "")).strip()

        if not thread_id:
            raise CliError(f"idx {idx} has no threadid in queue")

        if tag == "junk":
            _run_stdout(gmail_cmd + ["del", thread_id])
            removed_count += 1
            continue

        label_name = GMAIL_LABELS[tag]
        _run_stdout(gmail_cmd + ["tag", thread_id, label_name])
        labelled_count += 1

    # Cleanup: delete everything currently marked junk.
    junk_lines = [ln for ln in _run_stdout(gmail_cmd + ["ls", "label:4.junk"]).splitlines() if ln.strip()]
    for line in junk_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        thread_id = str(item.get("threadid", "")).strip()
        if thread_id:
            _run_stdout(gmail_cmd + ["del", thread_id])
            removed_count += 1

    # Cleanup: if action/reading emails are no longer in INBOX, remove those labels.
    tagged_lines = [
        ln
        for ln in _run_stdout(gmail_cmd + ["ls", "(label:0.action OR label:3.reading)"]).splitlines()
        if ln.strip()
    ]
    for line in tagged_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("botbot-gmail ls returned non-NDJSON output") from exc
        thread_id = str(item.get("threadid", "")).strip()
        labels = item.get("labels")
        normalized_labels = {str(x).strip().lower() for x in labels} if isinstance(labels, list) else set()
        if not thread_id or "inbox" in normalized_labels:
            continue
        for label_name in [GMAIL_LABELS["action"], GMAIL_LABELS["reading"]]:
            _run_stdout(gmail_cmd + ["untag", thread_id, label_name])
            labels_removed_count += 1

    if QUEUE_PATH.exists():
        QUEUE_PATH.unlink()
    print(
        json.dumps(
            {
                "labelled": labelled_count,
                "removed": removed_count,
                "labels_removed": labels_removed_count,
                "next": "auto run print fn with raw_output=true",
            },
            separators=(",", ":"),
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="meagent-gmail-tagging", description="Staged Gmail triage helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Fetch inbox emails into local NDJSON queue")
    sub.add_parser("rules", help="Print tagging rules")

    p_tag = sub.add_parser("tag", help="Set tag for one queue id")
    p_tag.add_argument("idx", type=int, help="Queue idx from fetch output")
    p_tag.add_argument("tag", help="One of: action, reading, junk")

    sub.add_parser("status", help="Check if queue is fully tagged")
    sub.add_parser("push", help="Apply tags and trash junk")
    sub.add_parser("print", help="Print untagged header and grouped tagged emails")

    args = parser.parse_args()
    handlers = {
        "fetch": cmd_fetch,
        "rules": cmd_rules,
        "tag": cmd_tag,
        "status": cmd_status,
        "push": cmd_push,
        "print": cmd_print,
    }
    try:
        return handlers[args.cmd](args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
