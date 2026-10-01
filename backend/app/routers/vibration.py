"""振动监测接口：维护振动监测记录，覆盖开始采集、登记振动超标、发起复测等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.vibration import VibrationService

router = APIRouter(prefix="/api/vibration", tags=["振动监测"])

service = VibrationService()

LIST_FIELDS = ["监测编号", "监测部位", "所属机组", "振动速度", "报警阈值", "采集时间", "频谱特征", "监测状态"]
STATUSES = ["待采集", "数据正常", "振动超标", "已复测"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按监测编号检索"),
    part: str | None = Query(default=None, description="按监测部位检索"),
    turbine: str | None = Query(default=None, description="按所属机组检索"),
    status: str | None = Query(default=None, description="待采集、数据正常、振动超标、已复测"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按监测编号、部位、机组与状态过滤振动监测列表；没有数据时返回空页，不报错。

    列表里每条记录的监测状态与卡片统计都由服务层同一份判断给出，页面不再自行判读。
    """
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, part=part, turbine=turbine, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size, stats=service.stats())


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条振动监测记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"振动监测记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条振动监测记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="振动监测记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条振动监测记录执行开始采集、登记振动超标、发起复测；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出振动监测清单：返回当前过滤条件下的全量数据，状态口径与列表保持一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "vibration", "total": total, "items": items, "stats": service.stats()}
