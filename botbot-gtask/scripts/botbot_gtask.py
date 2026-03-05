#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
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
            return ConfigPaths(Path(botbot_home).expanduser() / "botbot-gtask.json")
        return ConfigPaths(Path.home() / ".botbot" / "botbot-gtask.json")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CliError(f"config not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON config: {path}: {exc}") from exc


class GoogleTasksClient:
    def __init__(self, cfg_path: Path):
        self.cfg = _read_json(cfg_path)
        gog_cfg = self.cfg.get("gog") if isinstance(self.cfg.get("gog"), dict) else {}
        self.account = str((gog_cfg or {}).get("account") or self.cfg.get("account") or "").strip()
        self.client = str((gog_cfg or {}).get("client") or self.cfg.get("client") or "").strip()
        self.edit_whitelist = self.cfg.get("edit_whitelist") or []
        if not isinstance(self.edit_whitelist, list):
            raise CliError("config field edit_whitelist must be a list")

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

    def list_tasklists(self) -> list[dict[str, str]]:
        data = self._run_gog_json("tasks", "lists", "list", "--all", "--max", "1000")
        if not isinstance(data, list):
            return []
        out: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            out.append({"id": str(item.get("id", "")), "title": str(item.get("title", ""))})
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
        data = self._run_gog_json(
            "tasks",
            "list",
            lst["id"],
            "--all",
            "--max",
            "100",
            "--show-completed",
            "--show-hidden",
        )
        if not isinstance(data, list):
            return []
        out: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "id": str(item.get("id", "")),
                    "title": str(item.get("title", "")),
                    "notes": str(item.get("notes", "")),
                    "status": str(item.get("status", "")),
                }
            )
        return out

    def add_task(self, list_name_or_id: str, title: str, description: str) -> dict[str, str]:
        lst = self.first_tasklist() if not list_name_or_id else self.resolve_list(list_name_or_id)
        allowed = {str(x).lower() for x in self.edit_whitelist}
        if lst["id"].lower() not in allowed and lst["title"].lower() not in allowed:
            raise CliError(f"list is not in edit_whitelist: {lst['title']} ({lst['id']})")
        data = self._run_gog_json("tasks", "add", lst["id"], "--title", title, "--notes", description)
        if not isinstance(data, dict):
            raise CliError("unexpected response from gog tasks add")
        return {
            "id": str(data.get("id", "")),
            "title": str(data.get("title", "")),
            "notes": str(data.get("notes", "")),
            "status": str(data.get("status", "")),
            "list_id": lst["id"],
            "list_title": lst["title"],
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="botbot-gtask", description="Tiny Google Tasks CLI")
    parser.add_argument("--config", help="Path to botbot-gtask.json config")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ls", help="List all Google task lists")
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
