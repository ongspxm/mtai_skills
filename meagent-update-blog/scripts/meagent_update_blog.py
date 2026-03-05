#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TERMINAL_STATUSES = {"success", "failed", "canceled", "skipped", "manual"}


class CliError(RuntimeError):
    pass


def _resolve_config_path() -> Path:
    botbot_home = os.getenv("BOTBOT_HOME")
    if botbot_home:
        return Path(botbot_home).expanduser() / "meagent-update-blog.json"
    return Path.home() / ".botbot" / "meagent-update-blog.json"


def _http_json(method: str, url: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> tuple[int, Any]:
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    try:
        with urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(text) if text else {}
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(text) if text else {"text": text}
        except json.JSONDecodeError:
            return exc.code, {"text": text}
    except URLError as exc:
        raise CliError(f"network error: {exc}") from exc


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CliError(f"config not found: {path}")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON config: {path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise CliError(f"invalid config: expected object in {path}")
    return cfg


def cmd_run() -> int:
    cfg = _load_config(_resolve_config_path())
    url = str(cfg.get("url") or "https://gitlab.com").rstrip("/")
    project_id = str(cfg.get("project_id") or "").strip()
    token = str(cfg.get("token") or "").strip()
    ref = str(cfg.get("ref") or "main").strip()
    poll_interval = float(cfg.get("poll_interval_seconds") or 5)
    timeout_seconds = float(cfg.get("timeout_seconds") or 600)
    if not project_id or not token:
        raise CliError("missing required config values: project_id and token")

    trigger_url = f"{url}/api/v4/projects/{project_id}/trigger/pipeline"
    status_code, info = _http_json(
        "POST",
        trigger_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urlencode({"token": token, "ref": ref}).encode("utf-8"),
    )
    if status_code >= 400 or not isinstance(info, dict):
        raise CliError(f"pipeline trigger failed: status={status_code} response={info}")

    pipeline_id = info.get("id")
    web_url = str(info.get("web_url") or "")
    status = str(info.get("status") or "triggered")
    if not pipeline_id:
        raise CliError(f"pipeline triggered but no id returned: {info}")

    auth_token = str(cfg.get("private_token") or cfg.get("access_token") or "").strip()
    status_url = f"{url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}"
    headers = {"PRIVATE-TOKEN": auth_token} if auth_token else {}
    start = time.monotonic()

    while status not in TERMINAL_STATUSES:
        if time.monotonic() - start >= timeout_seconds:
            print(
                json.dumps(
                    {
                        "status": "timeout",
                        "pipeline_id": pipeline_id,
                        "web_url": web_url,
                        "message": f"pipeline timeout after {int(timeout_seconds)}s",
                    }
                )
            )
            return 0
        time.sleep(poll_interval)
        code, polled = _http_json("GET", status_url, headers=headers)
        if code in {401, 403, 404} and not headers:
            print(
                json.dumps(
                    {
                        "status": "triggered",
                        "pipeline_id": pipeline_id,
                        "web_url": web_url,
                        "message": "pipeline triggered; add private_token or access_token for status polling",
                    }
                )
            )
            return 0
        if code >= 400 or not isinstance(polled, dict):
            raise CliError(f"pipeline status check failed: status={code} response={polled}")
        status = str(polled.get("status") or status)
        web_url = str(polled.get("web_url") or web_url)

    print(
        json.dumps(
            {
                "status": status,
                "pipeline_id": pipeline_id,
                "web_url": web_url,
                "message": f"pipeline {status}",
            }
        )
    )
    return 0


def main() -> int:
    try:
        return int(cmd_run())
    except CliError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
