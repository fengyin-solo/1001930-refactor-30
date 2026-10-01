"""振动监测业务规则：超标判断、状态流转、字段校验与统计口径都收在这里。

页面与后端只认这一份判断，不再各算各的：
- 台账（登记振动超标、发起复测时人工确认的结论）优先，临时的阈值比对不能推翻台账；
- 台账没有明确结论（待采集 / 开始采集后自动判读）时，才用振动速度与报警阈值比对；
- 统计卡片直接对采集列表逐条套用同一份判断算出来，不单独维护口径。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "vibration"
REQUIRED_FIELDS = ["监测编号", "监测部位", "所属机组"]
STATUS_ORDER = ["待采集", "数据正常", "振动超标", "已复测"]
# 人工确认结论：一旦登记，阈值比对不得再改写（台账优先）。
MANUAL_STATUSES = {"振动超标", "已复测"}
ACTION_RULES = {"开始采集": "数据正常", "登记振动超标": "振动超标", "发起复测": "已复测"}

# 统计卡片固定从列表推导，标签也只有这一份，页面直接展示。
STAT_LABELS = ["待采集记录", "振动超标项数", "本月复测数"]


def _as_number(value: Any) -> float | None:
    """把振动速度 / 报警阈值读成数值；读不出来（占位文字、空值）就当作未采集。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def judge_status(entry: dict[str, Any]) -> str:
    """振动监测唯一的结论口径：台账优先，台账无结论时按阈值比对。

    - 振动超标 / 已复测：人工登记的台账结论，原样保留，页面上的临时判断作废；
    - 待采集：尚未采到振动速度，保持待采集；
    - 数据正常（开始采集后的自动判读）：振动速度达到或超过报警阈值即为振动超标，
      阈值或速度缺一项无法判读时维持数据正常。
    """
    ledger = str(entry.get("status") or STATUS_ORDER[0]).strip()
    if ledger in MANUAL_STATUSES or ledger == STATUS_ORDER[0]:
        return ledger
    speed = _as_number(entry.get("振动速度"))
    threshold = _as_number(entry.get("报警阈值"))
    if speed is None or threshold is None:
        return ledger
    return "振动超标" if speed >= threshold else "数据正常"


def present(entry: dict[str, Any]) -> dict[str, Any]:
    """给页面的同一份结果：监测状态列直接取统一判断，台账标记同步到同一口径。"""
    status = judge_status(entry)
    entry["status"] = status
    entry["pending"] = status != "已复测"
    entry["abnormal"] = status == "振动超标"
    entry["监测状态"] = status
    return entry


# 启动时把种子台账的 pending/abnormal 标记校正到统一口径，
# 看板（store.overview）与采集列表因此始终一致，不依赖谁先被调用。
for _seed_row in store.rows(MODULE):
    present(_seed_row)
del _seed_row


class VibrationService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        part: str | None = None,
        turbine: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [present(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("监测编号", ""))]
        if part:
            rows = [row for row in rows if part in str(row.get("监测部位", ""))]
        if turbine:
            rows = [row for row in rows if turbine in str(row.get("所属机组", ""))]
        if status:
            rows = [row for row in rows if row["监测状态"] == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 登记时一并收下已采集到的速度、阈值等数据；没有就是待采集。
        entry.update({
            field: values.get(field)
            for field in ["振动速度", "报警阈值", "采集时间", "频谱特征"]
            if field in values
        })
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"振动监测记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于振动监测可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        # 开始采集给出的是待判读结论，最终监测状态仍走同一份阈值/台账判断；
        # 登记振动超标与发起复测属于人工台账，写进去就锁定，不再被阈值比对改写。
        return present(entry), f"振动监测记录已{action}"

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片由采集列表逐条套用统一判断算出，页面与列表结论天然一致。"""
        rows = [present(row) for row in store.rows(MODULE)]
        month_prefix = date.today().strftime("%Y-%m")
        values = [
            sum(1 for row in rows if row["监测状态"] == "待采集"),
            sum(1 for row in rows if row["监测状态"] == "振动超标"),
            sum(
                1
                for row in rows
                if row["监测状态"] == "已复测"
                and str(row.get("采集时间") or "").startswith(month_prefix)
            ),
        ]
        return [{"label": label, "value": value} for label, value in zip(STAT_LABELS, values)]
