#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


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
            return ConfigPaths(Path(botbot_home).expanduser() / "botbot-gcal.json")
        return ConfigPaths(Path.home() / ".botbot" / "botbot-gcal.json")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CliError(f"config not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON config: {path}: {exc}") from exc


def _parse_user_timestamp(text: str, is_end: bool) -> datetime:
    raw = text.strip()
    normalized = raw.replace(" ", "T")
    has_time = "T" in normalized
    try:
        if has_time:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        d = date.fromisoformat(normalized)
        if is_end:
            return datetime.combine(d, time.max)
        return datetime.combine(d, time.min)
    except ValueError as exc:
        raise CliError(
            f"invalid timestamp: {text}. Use ISO-8601 date or datetime, e.g. 2026-02-22 or 2026-02-22T09:00:00Z"
        ) from exc


def _parse_timezone_offset(raw: Any) -> timezone:
    if raw is None:
        return timezone(timedelta(hours=8))
    text = str(raw).strip()
    if not text:
        return timezone(timedelta(hours=8))
    if text.upper() in {"Z", "UTC", "+00", "+0", "+00:00"}:
        return UTC

    sign = 1
    if text.startswith("+"):
        body = text[1:]
    elif text.startswith("-"):
        sign = -1
        body = text[1:]
    else:
        body = text

    if ":" in body:
        hh_str, mm_str = body.split(":", 1)
    else:
        hh_str, mm_str = body, "0"

    try:
        hours = int(hh_str)
        minutes = int(mm_str)
    except ValueError as exc:
        raise CliError("invalid default_timezone; expected numeric offset like +8 or +08:00") from exc

    if hours > 23 or minutes < 0 or minutes > 59:
        raise CliError("invalid default_timezone; hour must be 0-23 and minute 0-59")
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _to_api_datetime(dt: datetime, tz: timezone) -> str:
    return dt.astimezone(tz).isoformat()


def _keep_ascii(text: str) -> str:
    return ("".join(c for c in text if ord(c) < 128)).lower().strip()


def _parse_iso_utc(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_list_event_line(event: dict[str, str], default_tz: timezone) -> str:
    start = _parse_iso_utc(event["start"]).astimezone(default_tz)
    end = _parse_iso_utc(event["end"]).astimezone(default_tz)
    day = f"{start.isoweekday():02d}"
    span_days = (end.date() - start.date()).days
    days_str = f"({span_days}D) " if span_days > 1 else ""
    title = _keep_ascii(event.get("title", "")) or "(untitled)"
    return f"- {day} {start:%Y-%m-%d} {start:%H:%M}_{end:%H:%M} {days_str}{title}"


def _event_time(event_part: dict[str, Any], is_end: bool) -> datetime:
    dt = event_part.get("dateTime")
    if isinstance(dt, str):
        parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    d = event_part.get("date")
    if not isinstance(d, str):
        raise CliError("unexpected event time payload from Google Calendar")
    parsed_date = date.fromisoformat(d)
    if is_end:
        return datetime.combine(parsed_date, time.min, tzinfo=UTC) - timedelta(microseconds=1)
    return datetime.combine(parsed_date, time.min, tzinfo=UTC)


class GoogleCalendarClient:
    def __init__(self, cfg_path: Path):
        self.cfg = _read_json(cfg_path)
        gog_cfg = self.cfg.get("gog") if isinstance(self.cfg.get("gog"), dict) else {}
        self.account = str((gog_cfg or {}).get("account") or self.cfg.get("account") or "").strip()
        self.client = str((gog_cfg or {}).get("client") or self.cfg.get("client") or "").strip()
        self.default_timezone = _parse_timezone_offset(self.cfg.get("default_timezone"))
        self.default_calendars = self.cfg.get("default_calendars")
        if self.default_calendars is None:
            self.default_calendars = ["primary"]
        if not isinstance(self.default_calendars, list) or not all(
            isinstance(x, str) and x.strip() for x in self.default_calendars
        ):
            raise CliError("config field default_calendars must be a non-empty string list")

    def _run_gog_json(self, *args: str) -> Any:
        cmd = ["gog", "--json", "--results-only", "--no-input"]
        if self.account:
            cmd.extend(["--account", self.account])
        if self.client:
            cmd.extend(["--client", self.client])
        cmd.extend(args)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip() or f"gog failed: {' '.join(cmd)}"
            raise CliError(msg)
        payload = proc.stdout.strip()
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid JSON from gog: {exc}") from exc

    def _calendar_list(self) -> list[dict[str, str]]:
        data = self._run_gog_json("calendar", "calendars")
        if not isinstance(data, list):
            return []
        out: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            out.append({"id": str(item.get("id", "")), "summary": str(item.get("summary", ""))})
        return out

    def _resolve_default_calendars(self) -> list[dict[str, str]]:
        all_cals = self._calendar_list()
        by_id = {x["id"]: x for x in all_cals}
        by_summary_lc = {x["summary"].lower(): x for x in all_cals if x["summary"]}

        resolved: list[dict[str, str]] = []
        seen: set[str] = set()
        missing: list[str] = []
        for raw in self.default_calendars:
            key = raw.strip()
            found = by_id.get(key)
            if not found:
                found = by_summary_lc.get(key.lower())
            if not found and key.lower() == "primary":
                found = {"id": "primary", "summary": "primary"}
            if not found:
                missing.append(raw)
                continue
            cid = found["id"]
            if cid in seen:
                continue
            seen.add(cid)
            resolved.append(found)

        if missing:
            raise CliError(f"default_calendars not found in account: {', '.join(missing)}")
        if not resolved:
            raise CliError("no calendars resolved from default_calendars")
        return resolved

    def list_events(self, tstamp_start: str, tstamp_end: str) -> list[dict[str, str]]:
        start = _parse_user_timestamp(tstamp_start, is_end=False)
        end = _parse_user_timestamp(tstamp_end, is_end=True)
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.default_timezone)
        else:
            start = start.astimezone(self.default_timezone)
        if end.tzinfo is None:
            end = end.replace(tzinfo=self.default_timezone)
        else:
            end = end.astimezone(self.default_timezone)
        if "T" not in tstamp_start and " " not in tstamp_start:
            start = datetime.combine(start.date(), time.min, tzinfo=self.default_timezone)
        if "T" not in tstamp_end and " " not in tstamp_end:
            end = datetime.combine(end.date(), time.max, tzinfo=self.default_timezone)
        if end < start:
            raise CliError("end timestamp must be on/after start timestamp")

        resolved = self._resolve_default_calendars()
        out: list[dict[str, str]] = []
        start_arg = _to_api_datetime(start, self.default_timezone)
        end_arg = _to_api_datetime(end + timedelta(microseconds=1), self.default_timezone)
        for cal in resolved:
            data = self._run_gog_json(
                "calendar",
                "events",
                cal["id"],
                "--from",
                start_arg,
                "--to",
                end_arg,
                "--all-pages",
                "--max",
                "2500",
            )
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    event_start = _event_time(item.get("start") or {}, is_end=False)
                    event_end = _event_time(item.get("end") or {}, is_end=True)
                except (CliError, ValueError):
                    continue
                if event_end < start or event_start > end:
                    continue
                out.append(
                    {
                        "calendar_id": cal["id"],
                        "calendar": cal["summary"],
                        "id": str(item.get("id", "")),
                        "title": str(item.get("summary", "")),
                        "description": str(item.get("description", "")),
                        "start": _to_api_datetime(event_start, self.default_timezone),
                        "end": _to_api_datetime(event_end, self.default_timezone),
                        "html_link": str(item.get("htmlLink", "")),
                    }
                )
        out.sort(key=lambda x: (x["start"], x["end"], x["calendar_id"], x["id"]))
        return out

    def add_event(self, tstamp_start: str, tstamp_end: str, title: str) -> dict[str, str]:
        start = _parse_user_timestamp(tstamp_start, is_end=False)
        end = _parse_user_timestamp(tstamp_end, is_end=True)
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.default_timezone)
        else:
            start = start.astimezone(self.default_timezone)
        if end.tzinfo is None:
            end = end.replace(tzinfo=self.default_timezone)
        else:
            end = end.astimezone(self.default_timezone)
        if "T" not in tstamp_start and " " not in tstamp_start:
            start = datetime.combine(start.date(), time.min, tzinfo=self.default_timezone)
        if "T" not in tstamp_end and " " not in tstamp_end:
            end = datetime.combine(end.date(), time.max, tzinfo=self.default_timezone)
        if end < start:
            raise CliError("end timestamp must be on/after start timestamp")

        data = self._run_gog_json(
            "calendar",
            "create",
            "primary",
            "--summary",
            title,
            "--from",
            _to_api_datetime(start, self.default_timezone),
            "--to",
            _to_api_datetime(end, self.default_timezone),
        )
        if not isinstance(data, dict):
            raise CliError("unexpected response from gog calendar create")
        return {
            "calendar_id": "primary",
            "id": str(data.get("id", "")),
            "title": str(data.get("summary", "")),
            "start": str((data.get("start") or {}).get("dateTime", "")),
            "end": str((data.get("end") or {}).get("dateTime", "")),
            "html_link": str(data.get("htmlLink", "")),
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botbot-gcal", description="Tiny Google Calendar CLI")
    parser.add_argument("--config", help="Path to botbot-gcal.json config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("ls", help="List events from configured calendars between 2 timestamps (inclusive)")
    p_ls.add_argument("tstamp_start", help="Start timestamp (ISO date or datetime)")
    p_ls.add_argument("tstamp_end", help="End timestamp (ISO date or datetime)")

    p_add = sub.add_parser("add", help="Add event to primary calendar")
    p_add.add_argument("tstamp_start", help="Start timestamp (ISO date or datetime)")
    p_add.add_argument("tstamp_end", help="End timestamp (ISO date or datetime)")
    p_add.add_argument("title", help="Event title")

    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = ConfigPaths.resolve(args.config)
    try:
        client = GoogleCalendarClient(cfg.path)
        if args.cmd == "ls":
            events = client.list_events(args.tstamp_start, args.tstamp_end)
            today = datetime.now(client.default_timezone).date().isoformat()
            offset = datetime.now(client.default_timezone).isoformat()[-6:]
            header = f"today= {today} {offset} | query= {args.tstamp_start} to {args.tstamp_end}"
            if not events:
                print(f"{header}\n(no events)")
            else:
                body = "\n".join(_format_list_event_line(e, client.default_timezone) for e in events)
                print(f"{header}\n{body}")
            return 0
        if args.cmd == "add":
            print(json.dumps(client.add_event(args.tstamp_start, args.tstamp_end, args.title), indent=2))
            return 0
        raise CliError(f"unknown command: {args.cmd}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
