#!/usr/bin/env python3
import argparse
import base64
import concurrent.futures
import hashlib
import html
import json
import os
import secrets
import sys
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "https://gmail.googleapis.com/gmail/v1"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
ME = "/users/me"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
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
            return ConfigPaths(Path(botbot_home).expanduser() / "botbot-gmail.json")
        return ConfigPaths(Path.home() / ".botbot" / "botbot-gmail.json")


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


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


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


class _TagStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


class GmailClient:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.cfg = _read_json(cfg_path)
        self.api = self.cfg.get("api") or {}
        self.tokens = self.cfg.get("tokens") or {}

        self.base_url = self.api.get("base_url") or DEFAULT_API_BASE
        self.token_url = self.api.get("token_url") or DEFAULT_TOKEN_URL
        self.auth_url = self.api.get("auth_url") or DEFAULT_AUTH_URL

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

    def _has_required_gmail_scopes(self, access_token: str) -> bool | None:
        scopes = self._token_scopes(access_token)
        if scopes is None:
            return None
        return all(scope in scopes for scope in GMAIL_SCOPES)

    def _oauth_refresh_exchange(self) -> str:
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
        access_token = str(result.get("access_token", "")).strip()
        if not access_token:
            raise CliError("failed to refresh token: no access_token returned")
        ttl = int(result.get("expires_in", 3600))
        self.tokens["access_token"] = access_token
        self.tokens["expiry"] = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
        self.tokens["token_type"] = result.get("token_type", "Bearer")
        self._save_tokens()
        return access_token

    def _auth_exchange(self, code: str, verifier: str, redirect_uri: str) -> dict[str, str]:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.tokens.get("client_id", ""),
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        client_secret = self.tokens.get("client_secret")
        if client_secret:
            form["client_secret"] = client_secret
        result = _http_json(
            "POST",
            self.token_url,
            {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode(form).encode("utf-8"),
        )
        access_token = str(result.get("access_token", "")).strip()
        if not access_token:
            raise CliError("oauth exchange failed: no access_token")
        refresh_token = str(result.get("refresh_token", "")).strip()
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
        return {
            "token_type": str(self.tokens.get("token_type", "Bearer")),
            "expiry": str(self.tokens.get("expiry", "")),
            "scopes": GMAIL_SCOPES,
        }

    def _interactive_auth_for_gmail_scope(self) -> dict[str, str]:
        client_id = self.tokens.get("client_id")
        if not client_id:
            raise CliError("missing tokens.client_id in config")

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode().rstrip("=")
        redirect_uri = "http://localhost"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
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

        out = self._auth_exchange(code=code, verifier=verifier, redirect_uri=redirect_uri)
        has_scopes = self._has_required_gmail_scopes(self.tokens["access_token"])
        if has_scopes is False:
            raise CliError("received token is missing required Gmail scopes")
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); continuing")
        return out

    def _refresh_access_token_internal(self) -> str:
        return self._oauth_refresh_exchange()

    def _access_token(self) -> str:
        token = self.tokens.get("access_token")
        expires_at = _parse_ts(self.tokens.get("expiry"))
        if token and expires_at and expires_at > datetime.now(UTC) + timedelta(seconds=30):
            return token
        if token and not expires_at:
            return token
        return self._refresh_access_token_internal()

    def refresh_access_token(self) -> dict[str, str]:
        access_token = self._oauth_refresh_exchange()
        scopes = self._token_scopes(access_token)
        if scopes:
            self.tokens["scopes"] = sorted(scopes)
            self._save_tokens()
        has_scopes = self._has_required_gmail_scopes(access_token)
        if has_scopes is False:
            print("Current token lacks required Gmail scopes. Starting OAuth re-consent...")
            return self._interactive_auth_for_gmail_scope()
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); skipping scope check")
        return {
            "token_type": str(self.tokens.get("token_type", "Bearer")),
            "expiry": str(self.tokens.get("expiry", "")),
            "scopes": GMAIL_SCOPES,
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

    def _thread_details(self, thread_id: str) -> dict[str, Any]:
        return self._request("GET", f"{ME}/threads/{quote(thread_id, safe='')}", params={"format": "full"})

    def _thread_metadata(self, thread_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{ME}/threads/{quote(thread_id, safe='')}",
            params={"format": "metadata"},
        )

    def _labels_by_id(self) -> dict[str, str]:
        data = self._request("GET", f"{ME}/labels")
        out: dict[str, str] = {}
        for label in data.get("labels", []):
            lid = str(label.get("id", "")).strip()
            name = str(label.get("name", "")).strip()
            if lid:
                out[lid] = name or lid
        return out

    def _resolve_label_id(self, label: str) -> str:
        needle = label.strip()
        if not needle:
            raise CliError("label cannot be empty")
        labels = self._labels_by_id()
        if needle in labels:
            return needle
        needle_lc = needle.lower()
        for lid, name in labels.items():
            if name.lower() == needle_lc:
                return lid
        raise CliError(f"label not found: {label}")

    def _thread_header(self, thread_data: dict[str, Any], header_name: str) -> str:
        latest = self._latest_message(thread_data)
        if latest is None:
            return ""
        needle = header_name.lower()
        payload = latest.get("payload") or {}
        for header in payload.get("headers", []):
            if str(header.get("name", "")).lower() == needle:
                return str(header.get("value", ""))
        return ""

    def _thread_label_ids(self, thread_data: dict[str, Any]) -> list[str]:
        latest = self._latest_message(thread_data)
        if latest is None:
            return []
        return sorted(str(lid).strip() for lid in latest.get("labelIds", []) if str(lid).strip())

    def _thread_latest_internal_date_ms(self, thread_data: dict[str, Any]) -> int:
        latest = self._latest_message(thread_data)
        if latest is None:
            return 0
        raw = str(latest.get("internalDate", "")).strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    def _latest_message(self, thread_data: dict[str, Any]) -> dict[str, Any] | None:
        messages = thread_data.get("messages", [])
        if not isinstance(messages, list) or not messages:
            return None

        def internal_date(msg: dict[str, Any]) -> int:
            raw = str(msg.get("internalDate", "")).strip()
            try:
                return int(raw)
            except ValueError:
                return 0

        return max(messages, key=internal_date)

    def _decode_b64url(self, raw: str) -> str:
        data = raw.strip()
        if not data:
            return ""
        padding = "=" * ((4 - len(data) % 4) % 4)
        try:
            return base64.urlsafe_b64decode((data + padding).encode("utf-8")).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _extract_body_part(self, payload: dict[str, Any], mime: str) -> str:
        if payload.get("mimeType") == mime:
            return self._decode_b64url(str((payload.get("body") or {}).get("data", "")))
        for part in payload.get("parts", []):
            nested = self._extract_body_part(part, mime)
            if nested:
                return nested
        return ""

    def _strip_html(self, text: str) -> str:
        stripper = _TagStripper()
        stripper.feed(text)
        return stripper.text()

    def _message_plaintext(self, msg: dict[str, Any]) -> str:
        payload = msg.get("payload") or {}
        plain = self._extract_body_part(payload, "text/plain")
        if plain:
            return plain.replace("\r\n", "\n").replace("\r", "\n")
        html_part = self._extract_body_part(payload, "text/html")
        if html_part:
            return self._strip_html(html.unescape(html_part))
        return str(msg.get("snippet", ""))

    def list_threads(self, query: str) -> list[dict[str, Any]]:
        labels = self._labels_by_id()
        rows: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"q": query, "maxResults": "100"}
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", "/users/me/threads", params=params)
            thread_ids = [str(item.get("id", "")).strip() for item in data.get("threads", [])]
            thread_ids = [tid for tid in thread_ids if tid]
            if thread_ids:
                workers = min(8, len(thread_ids))
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                    fut_to_tid = {pool.submit(self._thread_metadata, tid): tid for tid in thread_ids}
                    for fut in concurrent.futures.as_completed(fut_to_tid):
                        tid = fut_to_tid[fut]
                        details = fut.result()
                        label_ids = self._thread_label_ids(details)
                        rows.append(
                            {
                                "threadid": tid,
                                "from": self._thread_header(details, "From"),
                                "subject": self._thread_header(details, "Subject"),
                                "tstamp": self._thread_latest_internal_date_ms(details),
                                "labels": [labels.get(lid, lid) for lid in label_ids],
                            }
                        )
            page_token = str(data.get("nextPageToken", ""))
            if not page_token:
                break
        return rows

    def delete_thread(self, thread_id: str) -> dict[str, str]:
        tid = thread_id.strip()
        if not tid:
            raise CliError("threadid cannot be empty")
        self._request("POST", f"{ME}/threads/{quote(tid, safe='')}/trash")
        return {"threadid": tid, "status": "trashed"}

    def read_latest_thread_body(self, thread_id: str) -> str:
        tid = thread_id.strip()
        if not tid:
            raise CliError("threadid cannot be empty")
        details = self._thread_details(tid)
        latest = self._latest_message(details)
        if latest is None:
            raise CliError(f"thread has no messages: {tid}")

        text = self._message_plaintext(latest).strip()
        fallback = str(latest.get("snippet", "")).strip()
        if text:
            return text
        if fallback:
            return fallback
        raise CliError("unable to extract body from latest message")

    def add_label_to_thread(self, thread_id: str, label: str) -> dict[str, Any]:
        tid = thread_id.strip()
        if not tid:
            raise CliError("threadid cannot be empty")
        label_id = self._resolve_label_id(label)
        data = self._request(
            "POST",
            f"{ME}/threads/{quote(tid, safe='')}/modify",
            body={"addLabelIds": [label_id]},
        )
        labels = self._labels_by_id()
        applied = [labels.get(x, x) for x in data.get("labelIds", [])]
        return {
            "threadid": tid,
            "added_label": labels.get(label_id, label_id),
            "labels": applied,
        }

    def remove_label_from_thread(self, thread_id: str, label: str) -> dict[str, Any]:
        tid = thread_id.strip()
        if not tid:
            raise CliError("threadid cannot be empty")
        label_id = self._resolve_label_id(label)
        data = self._request(
            "POST",
            f"{ME}/threads/{quote(tid, safe='')}/modify",
            body={"removeLabelIds": [label_id]},
        )
        labels = self._labels_by_id()
        applied = [labels.get(x, x) for x in data.get("labelIds", [])]
        return {
            "threadid": tid,
            "removed_label": labels.get(label_id, label_id),
            "labels": applied,
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botbot-gmail", description="Tiny Gmail CLI")
    parser.add_argument("--config", help="Path to botbot-gmail.json config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refresh", help="Refresh access token and persist to config")

    p_ls = sub.add_parser("ls", help='List threads matching query (default: "in:INBOX")')
    p_ls.add_argument("query", nargs="?", default="in:INBOX", help='Gmail search query (default: "in:INBOX")')

    p_del = sub.add_parser("del", help="Trash a thread by id")
    p_del.add_argument("threadid", help="Gmail thread id")

    p_tag = sub.add_parser("tag", help="Add label to a thread")
    p_tag.add_argument("threadid", help="Gmail thread id")
    p_tag.add_argument("label", help="Label name or label id")

    p_untag = sub.add_parser("untag", help="Remove label from a thread")
    p_untag.add_argument("threadid", help="Gmail thread id")
    p_untag.add_argument("label", help="Label name or label id")

    p_read = sub.add_parser("read", help="Read full plaintext body of latest message in a thread")
    p_read.add_argument("threadid", help="Gmail thread id")

    return parser


def _print_ndjson(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(json.dumps(row, separators=(",", ":")))


def main() -> int:
    args = _build_parser().parse_args()
    cfg = ConfigPaths.resolve(args.config)
    try:
        client = GmailClient(cfg.path)
        if args.cmd == "refresh":
            print(json.dumps(client.refresh_access_token(), indent=2))
            return 0
        if args.cmd == "ls":
            _print_ndjson(client.list_threads(args.query))
            return 0
        if args.cmd == "del":
            print(json.dumps(client.delete_thread(args.threadid), indent=2))
            return 0
        if args.cmd == "tag":
            print(json.dumps(client.add_label_to_thread(args.threadid, args.label), indent=2))
            return 0
        if args.cmd == "untag":
            print(json.dumps(client.remove_label_from_thread(args.threadid, args.label), indent=2))
            return 0
        if args.cmd == "read":
            print(client.read_latest_thread_body(args.threadid))
            return 0
        raise CliError(f"unknown command: {args.cmd}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
