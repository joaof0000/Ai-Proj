#!/usr/bin/env python3
"""Close Brave (or shut down the computer) if allowed sites are not opened in time.

How it works:
1. Start this script at login.
2. It waits until Brave is opened.
3. Once Brave opens, it starts a timer.
4. If you visit at least one allowed website before timeout, timer is cancelled.
5. If timeout is reached first, Brave is force-closed (or computer is shut down).
"""

from __future__ import annotations

import argparse
import atexit
import datetime as dt
import os
import platform
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ALLOWED_DOMAINS = [
    "docs.python.org",
    "github.com",
    "stackoverflow.com",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allowed-domain",
        action="append",
        dest="allowed_domains",
        help="Domain you are allowed to visit (can be passed multiple times)",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=10,
        help="Minutes before action is triggered if no allowed domain is visited",
    )
    parser.add_argument(
        "--check-interval-seconds",
        type=float,
        default=3,
        help="How often to check Brave + history DB",
    )
    parser.add_argument(
        "--shutdown-computer",
        action="store_true",
        help="Shutdown computer at timeout instead of only closing Brave",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed checks each loop (useful for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not close Brave or shutdown; only print what would happen",
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        help="Override Brave History DB path (advanced/testing)",
    )
    parser.add_argument(
        "--pid-file",
        type=Path,
        help="Write monitor PID to this file so you can stop it quickly",
    )
    return parser.parse_args()


def brave_process_names() -> tuple[str, ...]:
    system = platform.system().lower()
    if system == "windows":
        return ("brave.exe",)
    if system == "darwin":
        return ("Brave Browser",)
    return ("brave-browser", "brave")


def is_brave_running() -> bool:
    names = brave_process_names()
    system = platform.system().lower()

    if system == "windows":
        output = subprocess.run(
            ["tasklist"], capture_output=True, text=True, check=False
        ).stdout.lower()
        return any(name.lower() in output for name in names)

    for name in names:
        result = subprocess.run(["pgrep", "-f", name], capture_output=True, check=False)
        if result.returncode == 0:
            return True
    return False


def brave_history_db_path() -> Path:
    system = platform.system().lower()
    home = Path.home()

    if system == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError("LOCALAPPDATA is not set.")
        return Path(local_app_data) / "BraveSoftware/Brave-Browser/User Data/Default/History"

    if system == "darwin":
        return (
            home
            / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History"
        )

    # Linux
    return home / ".config/BraveSoftware/Brave-Browser/Default/History"


def chromium_time_to_datetime(value: int) -> dt.datetime:
    # Chromium timestamp: microseconds since 1601-01-01 UTC
    base = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)
    return base + dt.timedelta(microseconds=value)


def visited_allowed_domain_since(
    history_path: Path, allowed_domains: list[str], since_utc: dt.datetime
) -> bool:
    if not history_path.exists():
        return False

    allowed = [domain.lower() for domain in allowed_domains]

    # Open in read-only mode so Brave can keep writing.
    conn = sqlite3.connect(f"file:{history_path}?mode=ro", uri=True)
    try:
        cursor = conn.execute(
            "SELECT url, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 200"
        )
        for url, last_visit_time in cursor.fetchall():
            if not last_visit_time:
                continue

            visited_at = chromium_time_to_datetime(int(last_visit_time))
            if visited_at < since_utc:
                continue

            host = (urlparse(url).hostname or "").lower()
            for allowed_domain in allowed:
                if host == allowed_domain or host.endswith("." + allowed_domain):
                    return True
    finally:
        conn.close()

    return False


def close_brave() -> None:
    system = platform.system().lower()

    if system == "windows":
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe"], check=False)
        return

    for proc_name in brave_process_names():
        subprocess.run(["pkill", "-f", proc_name], check=False)


def shutdown_computer() -> None:
    system = platform.system().lower()
    if system == "windows":
        subprocess.run(["shutdown", "/s", "/t", "0"], check=False)
    elif system == "darwin":
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
    else:
        subprocess.run(["shutdown", "-h", "now"], check=False)


def run_monitor(
    allowed_domains: list[str],
    timeout_minutes: float,
    check_interval_seconds: float,
    should_shutdown_computer: bool,
    verbose: bool,
    dry_run: bool,
    history_path: Path,
) -> None:
    timeout_seconds = timeout_minutes * 60

    started_at: dt.datetime | None = None
    print("Waiting for Brave to open...")

    while True:
        running = is_brave_running()

        if running and started_at is None:
            started_at = dt.datetime.now(dt.timezone.utc)
            print(f"Brave detected. Timer started ({timeout_minutes} minutes).")

        if not running and started_at is not None:
            print("Brave closed. Timer reset.")
            started_at = None

        if running and started_at is not None:
            allowed_hit = visited_allowed_domain_since(
                history_path=history_path,
                allowed_domains=allowed_domains,
                since_utc=started_at,
            )
            elapsed = (dt.datetime.now(dt.timezone.utc) - started_at).total_seconds()
            if verbose:
                print(
                    "check:",
                    {
                        "elapsed_seconds": round(elapsed, 1),
                        "timeout_seconds": timeout_seconds,
                        "allowed_hit": allowed_hit,
                        "history_path": str(history_path),
                    },
                )
            if allowed_hit:
                print("Allowed site visited in time. Timer cancelled.")
                started_at = None
            elif elapsed >= timeout_seconds:
                print("Timeout reached without allowed website visit.")
                if dry_run:
                    print("[DRY RUN] Would close Brave now.")
                else:
                    close_brave()

                if should_shutdown_computer:
                    if dry_run:
                        print("[DRY RUN] Would shutdown computer now.")
                    else:
                        shutdown_computer()
                started_at = None

        time.sleep(check_interval_seconds)


def write_pid_file(pid_file: Path) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(f"{os.getpid()}\n")

    def _cleanup() -> None:
        if pid_file.exists():
            pid_file.unlink()

    atexit.register(_cleanup)


def main() -> None:
    args = parse_args()
    allowed = args.allowed_domains or DEFAULT_ALLOWED_DOMAINS
    history_path = args.history_path or brave_history_db_path()
    if args.pid_file:
        write_pid_file(args.pid_file)

    def handle_interrupt(_signal: int, _frame: object) -> None:
        print("\nExiting Brave Focus Guard.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    print(f"Allowed domains: {', '.join(allowed)}")
    print(f"History path: {history_path}")
    if args.dry_run:
        print("Dry run enabled: no close/shutdown commands will execute.")
    if args.pid_file:
        print(f"PID file: {args.pid_file}")

    run_monitor(
        allowed_domains=allowed,
        timeout_minutes=args.timeout_minutes,
        check_interval_seconds=args.check_interval_seconds,
        should_shutdown_computer=args.shutdown_computer,
        verbose=args.verbose,
        dry_run=args.dry_run,
        history_path=history_path,
    )


if __name__ == "__main__":
    main()
