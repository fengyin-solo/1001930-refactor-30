"""振动监测业务规则：振动超标判断、状态流转、字段校验、筛选口径与统计口径都收在这里。

页面不再自己拿振动速度和报警阈值比较一遍：列表里的监测状态、异常标记与统计卡片全部
由本模块的同一份判断产出。两边说法冲突时，一律以服务端台账（status）为准，页面上的
临时判断作废；台账状态是什么，采集列表和统计卡片就算出什么。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "vibration"
REQUIRED_FIELDS = ["监测编号", "监测部位", "所属机组"]
OPTIONAL_FIELDS = ["振动速度", "报警阈值", "采集时间", "频谱特征"]
STATUS_ORDER = ["待采集", "数据正常", "振动超标", "已复测"]
PENDING_STATUS = STATUS_ORDER[0]
NORMAL_STATUS = "数据正常"
OVER_LIMIT_STATUS = "振动超标"
RETESTED_STATUS = "已复测"
# 手动登记类动作直接写入台账状态；台账结论优先于任何临时比对
ACTION_TARGETS = {"登记振动超标": OVER_LIMIT_STATUS, "发起复测": RETESTED_STATUS}
# 历史台账缺报警阈值时按缺省报警档补数（mm/s），只补缺失项，不动已有数值
DEFAULT_ALARM_THRESHOLD = 7.1

SPEED_FIELD = "振动速度"
THRESHOLD_FIELD = "报警阈值"
COLLECTED_AT_FIELD = "采集时间"
DISPLAY_STATUS_FIELD = "监测状态"

STAT_PENDING_LABEL = "待采集记录"
STAT_OVER_LIMIT_LABEL = "振动超标项数"
STAT_RETEST_LABEL = "本月复测数"


def to_number(value: Any) -> float | None:
    """把台账里的振动速度/报警阈值解析成数值；空值或非数值一律视为缺失，不做猜测。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_over_limit(entry: dict[str, Any]) -> bool:
    """唯一的振动超标判断口径：振动速度与报警阈值都可解析，且速度严格大于阈值。

    采集列表的状态结论、开始采集时的自动判定都走这一份实现，页面不再另算。
    """
    speed = to_number(entry.get(SPEED_FIELD))
    threshold = to_number(entry.get(THRESHOLD_FIELD))
    if speed is None or threshold is None:
        return False
    return speed > threshold


def missing_threshold(value: Any) -> bool:
    """判断报警阈值是不是"没填"：只有 None/空串才算缺失，需要补数。

    历史台账里填过的内容（哪怕是早期非数值占位文字）一律保持原样，不当缺失覆盖。
    """
    return value is None or not str(value).strip()


class VibrationService:
    def __init__(self) -> None:
        self._ready = False

    def _ensure_ready(self) -> None:
        """首次使用时给历史台账做一次补数与对账，之后不再重复处理。"""
        if self._ready:
            return
        for row in store.rows(MODULE):
            # 之前攒下的阈值记录缺了报警阈值的（没填/空着），按缺省档补上；已有内容保持原样
            if missing_threshold(row.get(THRESHOLD_FIELD)):
                row[THRESHOLD_FIELD] = DEFAULT_ALARM_THRESHOLD
            self._sync_row(row)
        self._ready = True

    def _sync_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """以服务端台账状态为准重算派生结论：页面展示状态、异常标记、待办标记。

        页面上的临时判断在这里全部作废，台账状态与派生标记重新算一遍，保证一致。
        """
        status = str(row.get("status") or PENDING_STATUS)
        if status not in STATUS_ORDER:
            status = PENDING_STATUS
        row["status"] = status
        row[DISPLAY_STATUS_FIELD] = status
        row["abnormal"] = status == OVER_LIMIT_STATUS
        row["pending"] = status != RETESTED_STATUS
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        part: str | None = None,
        turbine: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self._ensure_ready()
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("监测编号", ""))]
        if part:
            rows = [row for row in rows if part in str(row.get("监测部位", ""))]
        if turbine:
            rows = [row for row in rows if turbine in str(row.get("所属机组", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self._ensure_ready()
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        self._ensure_ready()
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = value
        # 新登记记录没给报警阈值时同样补缺省档，保证后续判断口径可用
        if missing_threshold(entry.get(THRESHOLD_FIELD)):
            entry[THRESHOLD_FIELD] = DEFAULT_ALARM_THRESHOLD
        entry["status"] = PENDING_STATUS
        rows.append(entry)
        return self._sync_row(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        self._ensure_ready()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"振动监测记录 {entry_id} 不存在或已归档"
        values = values or {}

        if action == "开始采集":
            # 采集可带回实测振动速度/报警阈值；结论由同一份阈值判断给出，页面不另算
            speed = values.get(SPEED_FIELD)
            if speed is not None and str(speed).strip():
                entry[SPEED_FIELD] = speed
            threshold = values.get(THRESHOLD_FIELD)
            if threshold is not None and str(threshold).strip():
                entry[THRESHOLD_FIELD] = threshold
            elif missing_threshold(entry.get(THRESHOLD_FIELD)):
                entry[THRESHOLD_FIELD] = DEFAULT_ALARM_THRESHOLD
            if not str(entry.get(COLLECTED_AT_FIELD) or "").strip():
                entry[COLLECTED_AT_FIELD] = date.today().isoformat()
            target = OVER_LIMIT_STATUS if is_over_limit(entry) else NORMAL_STATUS
        elif action in ACTION_TARGETS:
            # 登记振动超标、发起复测是人工写台账，台账结论即为最终结论
            target = ACTION_TARGETS[action]
        else:
            return None, f"动作「{action}」不属于振动监测可执行范围"

        entry["status"] = target
        self._sync_row(entry)
        return entry, f"振动监测记录已{action}"

    def stat_cards(self) -> list[dict[str, Any]]:
        """统计卡片全部由采集列表台账算出来，不再在任何地方写死。"""
        self._ensure_ready()
        rows = store.rows(MODULE)
        month_prefix = date.today().strftime("%Y-%m")
        pending_count = sum(1 for row in rows if row.get("status") == PENDING_STATUS)
        over_limit_count = sum(1 for row in rows if row.get("abnormal"))
        retested_month = sum(
            1
            for row in rows
            if row.get("status") == RETESTED_STATUS
            and str(row.get(COLLECTED_AT_FIELD, "")).startswith(month_prefix)
        )
        return [
            {"label": STAT_PENDING_LABEL, "value": pending_count},
            {"label": STAT_OVER_LIMIT_LABEL, "value": over_limit_count},
            {"label": STAT_RETEST_LABEL, "value": retested_month},
        ]
