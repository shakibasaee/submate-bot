"""Start the local bot without exposing configuration or creating a second poller."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from app.core.config import get_settings
from app.core.polling_lock import polling_lock

ROOT = Path(__file__).resolve().parents[1]


def is_running(token: str) -> bool:
    try:
        with polling_lock(token):
            return False
    except RuntimeError:
        return True


def local_health(host: str, port: int) -> bool:
    # Never send this local status request through a configured internet proxy.
    host = "::1" if host == "::" else "127.0.0.1" if host == "0.0.0.0" else host
    address = f"[{host}]" if ":" in host else host
    try:
        with build_opener(ProxyHandler({})).open(
            f"http://{address}:{port}/health/live", timeout=2
        ) as response:
            return json.load(response) == {"status": "ok"}
    except (OSError, URLError, ValueError):
        return False


def start_detached() -> subprocess.Popen[bytes]:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    environment = {**os.environ, "LOG_LEVEL": "WARNING", "PYTHONUNBUFFERED": "1"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (logs / "submate-local.log").open("ab") as output:
        return subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            cwd=ROOT,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Start SubMate locally or check its status.")
    parser.add_argument("action", choices=("start", "status"), nargs="?", default="start")
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        settings = get_settings()
        token = settings.telegram_bot_token.get_secret_value()
        running = is_running(token)
        if running:
            healthy = local_health(settings.health_host, settings.health_port)
            print(
                "SubMate is already running locally."
                if healthy
                else "A SubMate process is running, but its local health check did not respond."
            )
            print("If Telegram is silent, check your internet/VPN and run the live check.")
            return 0 if healthy else 1
        if args.action == "status":
            print("SubMate is stopped. Double-click Start SubMate.cmd to start it.")
            return 1
        process = start_detached()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print("SubMate could not start. Check local configuration and the ignored logs.")
                return 1
            if is_running(token) and local_health(settings.health_host, settings.health_port):
                print("SubMate started locally. You can close this launcher window.")
                print("Keep the computer awake and online. This is not permanent hosting.")
                print("Local health does not prove Telegram or provider connectivity.")
                return 0
            time.sleep(0.5)
        print("Startup is taking longer than expected. Check status before trying again.")
        return 1
    except Exception as error:
        print(f"Local startup/status failed ({type(error).__name__}). Check the local .env.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
