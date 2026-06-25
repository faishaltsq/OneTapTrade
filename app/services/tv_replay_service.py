from datetime import datetime, timezone
from typing import Any, Optional

from app.logger import logger


class TVReplaySession:
    def __init__(self):
        self._active: bool = False
        self._start_date: str = ""
        self._steps: int = 0
        self._trades: list[dict] = []

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self, date_iso: str) -> bool:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return False

        try:
            ok = await tools.replay_start(date_iso)
            if ok:
                self._active = True
                self._start_date = date_iso
                self._steps = 0
                self._trades = []
                logger.info(f"TV replay started at {date_iso}")
            return ok
        except Exception as e:
            logger.warning(f"TV replay start failed: {e}")
            return False

    async def step(self) -> Optional[dict]:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None or not self._active:
            return None

        try:
            status = await tools.replay_step()
            if status:
                self._steps += 1
                return status.model_dump()
            return None
        except Exception as e:
            logger.debug(f"TV replay step failed: {e}")
            return None

    async def stop(self) -> dict:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is not None:
            try:
                await tools.replay_stop()
            except Exception:
                pass

        self._active = False
        result = {
            "start_date": self._start_date,
            "steps": self._steps,
            "trades": len(self._trades),
        }
        logger.info(f"TV replay stopped: {result}")
        return result

    async def status(self) -> Optional[dict]:
        from app.tv_connector import get_tv_tools

        tools = get_tv_tools()
        if tools is None:
            return None

        try:
            s = await tools.replay_status()
            return s.model_dump() if s else None
        except Exception:
            return None


_replay_session: Optional[TVReplaySession] = None


def get_replay_session() -> TVReplaySession:
    global _replay_session
    if _replay_session is None:
        _replay_session = TVReplaySession()
    return _replay_session
