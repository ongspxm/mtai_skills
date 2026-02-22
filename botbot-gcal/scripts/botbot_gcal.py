#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import webbrowser
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "https://www.googleapis.com/calendar/v3"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _http_json(method: str, url: str, headers: dict[str, str], body: bytes | None = None) -> dict[str, Any]:
    req = Request(url=url, method=method, headers=headers, data=body)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"HTTP {exc.code} for {url}: {details}") from exc
    except URLError as exc:
        raise CliError(f"network error for {url}: {exc}") from exc


def _parse_config_expiry(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _parse_user_timestamp(text: str, is_end: bool) -> datetime:
    raw = text.strip()
    normalized = raw.replace(" ", "T")
    has_time = "T" in normalized
    try:
        if has_time:
            dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            return dt
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
        parts = body.split(":", 1)
        if len(parts) != 2:
            raise CliError("invalid default_timezone; expected formats like +8 or +08:00")
        hh_str, mm_str = parts
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


def _to_api_datetime(dt: datetime, tz: timezone = UTC) -> str:
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
    day = start.strftime("%A")[:3].lower()
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
        # Google all-day event end date is exclusive.
        return datetime.combine(parsed_date, time.min, tzinfo=UTC) - timedelta(microseconds=1)
    return datetime.combine(parsed_date, time.min, tzinfo=UTC)


class GoogleCalendarClient:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.cfg = _read_json(cfg_path)
        self.api = self.cfg.get("api") or {}
        self.tokens = self.cfg.get("tokens") or {}

        self.base_url = self.api.get("base_url") or DEFAULT_API_BASE
        self.token_url = self.api.get("token_url") or DEFAULT_TOKEN_URL
        self.auth_url = self.api.get("auth_url") or DEFAULT_AUTH_URL
        self.default_timezone = _parse_timezone_offset(self.cfg.get("default_timezone"))
        self.default_calendars = self.cfg.get("default_calendars")
        if self.default_calendars is None:
            self.default_calendars = ["primary"]
        if not isinstance(self.default_calendars, list) or not all(
            isinstance(x, str) and x.strip() for x in self.default_calendars
        ):
            raise CliError("config field default_calendars must be a non-empty string list")

    def _save_tokens(self) -> None:
        self.cfg["tokens"] = self.tokens
        _write_json(self.cfg_path, self.cfg)

    def _token_scopes(self, access_token: str) -> set[str] | None:
        try:
            data = _http_json(
                "GET",
                f"https://www.googleapis.com/oauth2/v3/tokeninfo?access_token={access_token}",
                {},
            )
        except CliError:
            return None
        raw = str(data.get("scope", "")).strip()
        if not raw:
            return set()
        return {x for x in raw.split(" ") if x}

    def _has_required_calendar_scopes(self, access_token: str) -> bool | None:
        scopes = self._token_scopes(access_token)
        if scopes is None:
            return None
        return all(scope in scopes for scope in CALENDAR_SCOPES)

    def _interactive_auth_for_calendar_scope(self) -> dict[str, str]:
        client_id = self.tokens.get("client_id")
        client_secret = self.tokens.get("client_secret")
        if not client_id:
            raise CliError("missing tokens.client_id in config")

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode().rstrip("=")
        redirect_uri = "http://localhost"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(CALENDAR_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = self.auth_url + "?" + urlencode(params)
        print("Open this URL and authorize:")
        print(auth_url)
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass
        provided = input("Paste auth code or full redirect URL: ").strip()
        code = provided
        if "code=" in provided:
            code = provided.split("code=", 1)[1].split("&", 1)[0]
        if not code:
            raise CliError("no authorization code provided")

        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        if client_secret:
            form["client_secret"] = client_secret
        result = _http_json(
            "POST",
            self.token_url,
            {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode(form).encode("utf-8"),
        )
        access_token = result.get("access_token")
        if not access_token:
            raise CliError("oauth exchange failed: no access_token")
        refresh_token = result.get("refresh_token")
        if not refresh_token and not self.tokens.get("refresh_token"):
            raise CliError("oauth exchange failed: no refresh_token")

        ttl = int(result.get("expires_in", 3600))
        expiry = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
        self.tokens["access_token"] = access_token
        self.tokens["expiry"] = expiry
        self.tokens["token_type"] = result.get("token_type", "Bearer")
        if refresh_token:
            self.tokens["refresh_token"] = refresh_token
        scopes = self._token_scopes(access_token)
        if scopes:
            self.tokens["scopes"] = sorted(scopes)
        self._save_tokens()
        has_scopes = self._has_required_calendar_scopes(access_token)
        if has_scopes is False:
            raise CliError("received token is missing required Google Calendar scopes")
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); continuing")
        return {
            "token_type": self.tokens["token_type"],
            "expiry": expiry,
            "scopes": CALENDAR_SCOPES,
        }

    def _access_token(self) -> str:
        token = self.tokens.get("access_token")
        expires_at = _parse_config_expiry(self.tokens.get("expiry"))
        if token and expires_at and expires_at > datetime.now(UTC) + timedelta(seconds=30):
            return token
        if token and not expires_at:
            return token

        return self._refresh_access_token_internal()

    def _refresh_access_token_internal(self) -> str:

        refresh_token = self.tokens.get("refresh_token")
        client_id = self.tokens.get("client_id")
        client_secret = self.tokens.get("client_secret")
        if not (refresh_token and client_id and client_secret):
            raise CliError("missing tokens: provide access_token or refresh_token + client_id + client_secret")

        payload = urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode("utf-8")
        result = _http_json(
            "POST",
            self.token_url,
            {"Content-Type": "application/x-www-form-urlencoded"},
            payload,
        )
        access_token = result.get("access_token")
        if not access_token:
            raise CliError("failed to refresh token: no access_token returned")

        ttl = int(result.get("expires_in", 3600))
        self.tokens["access_token"] = access_token
        self.tokens["expiry"] = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
        self.tokens["token_type"] = result.get("token_type", "Bearer")
        self._save_tokens()
        return access_token

    def refresh_access_token(self) -> dict[str, str]:
        access_token = self._refresh_access_token_internal()
        scopes = self._token_scopes(access_token)
        if scopes:
            self.tokens["scopes"] = sorted(scopes)
            self._save_tokens()
        has_scopes = self._has_required_calendar_scopes(access_token)
        if has_scopes is False:
            print("Current token lacks required Google Calendar scopes. Starting OAuth re-consent...")
            return self._interactive_auth_for_calendar_scope()
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); skipping scope check")
        return {
            "token_type": str(self.tokens.get("token_type", "Bearer")),
            "expiry": str(self.tokens.get("expiry", "")),
            "scopes": CALENDAR_SCOPES,
        }

    def _request(self, method: str, path: str, params: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self._access_token()
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        if params:
            url += "?" + urlencode(params)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        return _http_json(method, url, headers, payload)

    def _calendar_list(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        page_token = ""
        while True:
            params = {"maxResults": "250"}
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", "/users/me/calendarList", params=params)
            for item in data.get("items", []):
                out.append(
                    {
                        "id": str(item.get("id", "")),
                        "summary": str(item.get("summary", "")),
                    }
                )
            page_token = str(data.get("nextPageToken", ""))
            if not page_token:
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
        for cal in resolved:
            page_token = ""
            while True:
                params = {
                    "timeMin": _to_api_datetime(start, self.default_timezone),
                    "timeMax": _to_api_datetime(end + timedelta(microseconds=1), self.default_timezone),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": "2500",
                }
                if page_token:
                    params["pageToken"] = page_token
                data = self._request("GET", f"/calendars/{cal['id']}/events", params=params)
                for item in data.get("items", []):
                    start_obj = item.get("start") or {}
                    end_obj = item.get("end") or {}
                    try:
                        event_start = _event_time(start_obj, is_end=False)
                        event_end = _event_time(end_obj, is_end=True)
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
                page_token = str(data.get("nextPageToken", ""))
                if not page_token:
                    break

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
        body = {
            "summary": title,
            "start": {"dateTime": _to_api_datetime(start, self.default_timezone)},
            "end": {"dateTime": _to_api_datetime(end, self.default_timezone)},
        }
        data = self._request("POST", "/calendars/primary/events", body=body)
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

    sub.add_parser("refresh", help="Refresh access token and persist to config")

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
        if args.cmd == "refresh":
            print(json.dumps(client.refresh_access_token(), indent=2))
            return 0
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
