import subprocess
import time
from pathlib import Path

from app.config import settings


def _start_process(file_path: str, arguments: list[str]) -> None:
    subprocess.Popen([file_path, *arguments])


def launch_tradingview_if_configured(starter=_start_process, sleeper=time.sleep) -> dict:
    if not settings.tv_launch_on_startup:
        return {"launched": False, "reason": "TV_LAUNCH_ON_STARTUP disabled"}

    if not settings.tv_exe_path:
        return {"launched": False, "reason": "TV_EXE_PATH not configured"}

    exe_path = Path(settings.tv_exe_path)
    if not exe_path.exists():
        return {"launched": False, "reason": f"TV_EXE_PATH not found: {exe_path}"}

    arguments = [f"--remote-debugging-port={settings.tv_debug_port}"]
    starter(file_path=str(exe_path), arguments=arguments)
    sleeper(5)
    return {"launched": True, "path": str(exe_path), "port": settings.tv_debug_port}
