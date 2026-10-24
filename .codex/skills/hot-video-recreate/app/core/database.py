"""独立包 stub：无真实数据库。"""
from __future__ import annotations

from typing import Any, List, Optional


class DbStub:
    async def execute(self, sql: str, *args: Any) -> List[dict]:
        return []

    async def execute_one(self, sql: str, *args: Any) -> Optional[dict]:
        return {"credits": 0}

    async def execute_insert(self, sql: str, *args: Any) -> None:
        return None

    async def execute_update(self, sql: str, *args: Any) -> int:
        return 0


db = DbStub()
