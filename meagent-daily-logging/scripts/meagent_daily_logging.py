#!/usr/bin/env python3
import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class CliError(RuntimeError):
    pass


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def load_config(path: Path) -> dict:
    if not path.exists():
        raise CliError(f"missing config: {path}")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON config: {path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise CliError("config must be a JSON object")
    return cfg


def parse_chats(cfg: dict) -> list[tuple[int, str]]:
    chats = cfg.get("chats")
    if not isinstance(chats, dict) or not chats:
        raise CliError("missing required config key: chats (non-empty object mapping tag->chat_id)")
    out: list[tuple[int, str]] = []
    for raw_tag, raw_chat in chats.items():
        tag = str(raw_tag or "").strip()
        if not tag:
            raise CliError("chats contains an empty tag key")
        try:
            out.append((int(raw_chat), tag))
        except (TypeError, ValueError) as exc:
            raise CliError(f"chats[{tag!r}] chat_id must be an integer") from exc
    return out


async def collect_entries(
    cfg: dict, chats: list[tuple[int, str]], session_path: Path, start_local: datetime, end_local: datetime
) -> list[tuple[datetime, str, str]]:
    try:
        from telethon import TelegramClient
    except ModuleNotFoundError as exc:
        raise CliError("missing dependency: telethon (run with `uv run --with=telethon ...`)") from exc

    try:
        api_id = int(cfg.get("api_id"))
    except (TypeError, ValueError) as exc:
        raise CliError("invalid config key: api_id must be an integer") from exc
    api_hash = str(cfg.get("api_hash") or "").strip()
    if not api_hash:
        raise CliError("missing required config key: api_hash")

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    try:
        for retry in range(2):
            client = TelegramClient(str(session_path), api_id, api_hash)
            await client.connect()
            try:
                await client.start(
                    phone=(lambda: input("Please enter your phone: ")),
                    password=(lambda: getpass.getpass("Please enter your password: ")),
                )
                me = await client.get_me()
                if not me or getattr(me, "bot", False):
                    if retry:
                        raise CliError(
                            "failed to authenticate user account; session resolved to a bot account"
                        )
                    try:
                        await client.log_out()
                    except Exception:
                        pass
                    for extra in ("", "-journal", "-shm", "-wal"):
                        try:
                            (session_path.parent / f"{session_path.name}{extra}").unlink()
                        except FileNotFoundError:
                            pass
                    continue

                try:
                    os.chmod(session_path, 0o600)
                except OSError:
                    pass

                out: list[tuple[datetime, str, str]] = []
                for chat_id, tag in chats:
                    try:
                        entity = await client.get_entity(chat_id)
                    except Exception as exc:
                        raise CliError(f"failed to resolve chat target {chat_id!r}: {exc}") from exc
                    async for msg in client.iter_messages(entity, offset_date=end_utc):
                        if msg.date is None:
                            continue
                        m_utc = msg.date.astimezone(timezone.utc)
                        if m_utc >= end_utc:
                            continue
                        if m_utc < start_utc:
                            break
                        txt = (msg.message or "").strip()
                        text = "\n".join([l for l in txt.split("\n") if l.strip()])
                        if text:
                            out.append((m_utc.astimezone(start_local.tzinfo), tag, text))
                out.sort(key=lambda x: x[0])
                return out
            finally:
                await client.disconnect()
        raise CliError("failed to establish a user-authenticated Telegram session")
    except CliError:
        raise
    except Exception as exc:
        raise CliError(f"telegram auth/fetch failed: {exc}") from exc


def upsert_day(month_file: Path, day_header: str, log_lines: list[str]) -> None:
    existing = month_file.read_text(encoding="utf-8").splitlines() if month_file.exists() else []
    start = -1
    end = len(existing)
    for i, line in enumerate(existing):
        if line.strip() != f"# {day_header}":
            continue
        start = i
        for j in range(i + 1, len(existing)):
            if existing[j].startswith("# "):
                end = j
                break
        break
    block = [f"# {day_header}", *log_lines]
    merged = existing + ([""] if existing else []) + block if start < 0 else existing[:start] + block + existing[end:]
    month_file.parent.mkdir(parents=True, exist_ok=True)
    month_file.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")


async def run() -> int:
    parser = argparse.ArgumentParser(prog="meagent_daily_logging.py")
    subparsers = parser.add_subparsers(dest="subcmd", required=True)
    run_parser = subparsers.add_parser("run", help="fetch Telegram messages and update daily log")
    run_parser.add_argument("--date", type=parse_date, help="target local day (YYYY-MM-DD) to backfill")
    run_parser.add_argument(
        "--config",
        type=Path,
        help="config path (default: ~/.botbot/meagent-daily-logging.json)",
    )
    args = parser.parse_args(sys.argv[1:])

    cfg_path = args.config.expanduser() if args.config else Path.home() / ".botbot" / "meagent-daily-logging.json"
    cfg = load_config(cfg_path)

    tz_name = str(cfg.get("timezone") or "Asia/Singapore").strip()
    try:
        tz = ZoneInfo(tz_name)
    except Exception as exc:
        raise CliError(f"invalid timezone: {tz_name}") from exc
    run_day = args.date
    if run_day is None:
        run_day = datetime.now(tz).astimezone(tz).date() - timedelta(days=1)

    raw_log_folder = cfg.get("log_folder")
    if raw_log_folder is None:
        log_folder = Path.home() / "docs/autolog"
    else:
        folder_text = str(raw_log_folder).strip()
        if not folder_text:
            raise CliError("invalid config key: log_folder cannot be blank")
        log_folder = Path(folder_text).expanduser()
    if not str(log_folder).strip():
        raise CliError("invalid config key: log_folder cannot be blank")

    start_local = datetime.combine(run_day, time(2, 0), tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    botbot_home = Path.home() / ".botbot"
    botbot_home.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(botbot_home, 0o700)
    except OSError:
        pass
    session_path = botbot_home / "meagent-daily-logging.session"

    entries = await collect_entries(cfg, parse_chats(cfg), session_path, start_local, end_local)

    month_file = log_folder / f"{start_local:%Y-%m}.md"
    log_lines: list[str] = []
    for i, (_, tag, text) in enumerate(entries):
        log_lines.append(f"({tag}) {text}")
        if i < len(entries) - 1:
            log_lines.append("")
    day_header = f"{start_local:%Y-%m-%d}"
    upsert_day(month_file, day_header, log_lines)

    for line in log_lines:
        print(line)
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
