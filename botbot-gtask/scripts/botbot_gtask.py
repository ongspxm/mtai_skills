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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_API_BASE = "https://tasks.googleapis.com/tasks/v1"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TASKS_SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/tasks.readonly",
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
            return ConfigPaths(Path(botbot_home).expanduser() / "botbot-gtask.json")
        return ConfigPaths(Path.home() / ".botbot" / "botbot-gtask.json")


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


class GoogleTasksClient:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.cfg = _read_json(cfg_path)
        self.api = self.cfg.get("api") or {}
        self.tokens = self.cfg.get("tokens") or {}

        self.base_url = self.api.get("base_url") or DEFAULT_API_BASE
        self.token_url = self.api.get("token_url") or DEFAULT_TOKEN_URL
        self.auth_url = self.api.get("auth_url") or DEFAULT_AUTH_URL
        self.edit_whitelist = self.cfg.get("edit_whitelist") or []
        if not isinstance(self.edit_whitelist, list):
            raise CliError("config field edit_whitelist must be a list")

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

    def _has_required_tasks_scopes(self, access_token: str) -> bool | None:
        scopes = self._token_scopes(access_token)
        if scopes is None:
            return None
        return all(scope in scopes for scope in TASKS_SCOPES)

    def _interactive_auth_for_tasks_scope(self) -> dict[str, str]:
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
            "scope": " ".join(TASKS_SCOPES),
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
        has_scopes = self._has_required_tasks_scopes(access_token)
        if has_scopes is False:
            raise CliError("received token is missing required Google Tasks scopes")
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); continuing")
        return {
            "token_type": self.tokens["token_type"],
            "expiry": expiry,
            "scopes": TASKS_SCOPES,
        }

    def _save_tokens(self) -> None:
        self.cfg["tokens"] = self.tokens
        _write_json(self.cfg_path, self.cfg)

    def _access_token(self) -> str:
        token = self.tokens.get("access_token")
        expires_at = _parse_ts(self.tokens.get("expiry"))
        if token and expires_at and expires_at > datetime.now(UTC) + timedelta(seconds=30):
            return token
        if token and not expires_at:
            return token
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

        self.tokens["access_token"] = access_token
        ttl = int(result.get("expires_in", 3600))
        self.tokens["expiry"] = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
        self.tokens["token_type"] = result.get("token_type", "Bearer")
        self._save_tokens()
        return access_token

    def refresh_access_token(self) -> dict[str, str]:
        refresh_token = self.tokens.get("refresh_token")
        client_id = self.tokens.get("client_id")
        client_secret = self.tokens.get("client_secret")
        if not (refresh_token and client_id and client_secret):
            raise CliError("missing tokens: refresh_token + client_id + client_secret required")

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
        expiry = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
        self.tokens["access_token"] = access_token
        self.tokens["expiry"] = expiry
        self.tokens["token_type"] = result.get("token_type", "Bearer")
        scopes = self._token_scopes(access_token)
        if scopes:
            self.tokens["scopes"] = sorted(scopes)
        self._save_tokens()
        has_scopes = self._has_required_tasks_scopes(access_token)
        if has_scopes is False:
            print("Current token lacks required Google Tasks scopes. Starting OAuth re-consent...")
            return self._interactive_auth_for_tasks_scope()
        if has_scopes is None:
            print("warning: unable to verify token scopes (tokeninfo unreachable); skipping scope check")
        return {
            "token_type": self.tokens["token_type"],
            "expiry": expiry,
            "scopes": TASKS_SCOPES,
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

    def list_tasklists(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        page_token = ""
        while True:
            params = {"maxResults": "100"}
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", "/users/@me/lists", params=params)
            for item in data.get("items", []):
                out.append({"id": item.get("id", ""), "title": item.get("title", "")})
            page_token = data.get("nextPageToken", "")
            if not page_token:
                return out

    def first_tasklist(self) -> dict[str, str]:
        lists = self.list_tasklists()
        if not lists:
            raise CliError("no task lists found in Google Tasks")
        return lists[0]

    def resolve_list(self, list_name_or_id: str) -> dict[str, str]:
        all_lists = self.list_tasklists()
        for item in all_lists:
            if item["id"] == list_name_or_id:
                return item
        needle = list_name_or_id.lower()
        for item in all_lists:
            if item["title"].lower() == needle:
                return item
        raise CliError(f"task list not found: {list_name_or_id}")

    def list_tasks(self, list_name_or_id: str) -> list[dict[str, str]]:
        lst = self.resolve_list(list_name_or_id)
        out: list[dict[str, str]] = []
        page_token = ""
        while True:
            params = {
                "maxResults": "100",
                "showCompleted": "true",
                "showHidden": "true",
                "showDeleted": "false",
            }
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", f"/lists/{lst['id']}/tasks", params=params)
            for item in data.get("items", []):
                out.append(
                    {
                        "id": item.get("id", ""),
                        "title": item.get("title", ""),
                        "notes": item.get("notes", ""),
                        "status": item.get("status", ""),
                    }
                )
            page_token = data.get("nextPageToken", "")
            if not page_token:
                return out

    def add_task(self, list_name_or_id: str, title: str, description: str) -> dict[str, str]:
        lst = self.first_tasklist() if not list_name_or_id else self.resolve_list(list_name_or_id)
        allowed = {str(x).lower() for x in self.edit_whitelist}
        if lst["id"].lower() not in allowed and lst["title"].lower() not in allowed:
            raise CliError(
                f"list is not in edit_whitelist: {lst['title']} ({lst['id']})"
            )
        data = self._request(
            "POST",
            f"/lists/{lst['id']}/tasks",
            body={"title": title, "notes": description},
        )
        return {
            "id": data.get("id", ""),
            "title": data.get("title", ""),
            "notes": data.get("notes", ""),
            "status": data.get("status", ""),
            "list_id": lst["id"],
            "list_title": lst["title"],
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botbot-gtask", description="Tiny Google Tasks CLI")
    parser.add_argument("--config", help="Path to botbot-gtask.json config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ls", help="List all Google task lists")
    sub.add_parser("refresh", help="Refresh access token and persist to config")

    p_list = sub.add_parser("tasks", help="List tasks in a task list")
    p_list.add_argument("--list", required=True, dest="list_name", help="Task list title or id")

    p_add = sub.add_parser("add", help="Add a task to a task list")
    p_add.add_argument("--list", dest="list_name", help="Task list title or id (defaults to first list)")
    p_add.add_argument("--title", required=True, help="Task title")
    p_add.add_argument("--notes", default="", help="Task notes")

    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = ConfigPaths.resolve(args.config)
    try:
        client = GoogleTasksClient(cfg.path)
        if args.cmd == "ls":
            print(json.dumps(client.list_tasklists(), indent=2))
            return 0
        if args.cmd == "refresh":
            print(json.dumps(client.refresh_access_token(), indent=2))
            return 0
        if args.cmd == "tasks":
            print(json.dumps(client.list_tasks(args.list_name), indent=2))
            return 0
        if args.cmd == "add":
            print(json.dumps(client.add_task(args.list_name, args.title, args.notes), indent=2))
            return 0
        raise CliError(f"unknown command: {args.cmd}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
