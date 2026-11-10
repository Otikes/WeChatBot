"""群发分组配置（系统内自定义）。

分组由用户在控制台自行维护，**与微信自带的通讯录标签完全独立**：
不读取、不导入、不同步微信标签，两者互不影响。同一个分组里可以同时放
好友和群聊，用 ``type`` 区分：

.. code-block:: json

    {
      "version": 1,
      "groups": [
        {"name": "客户通知", "targets": [
          {"type": "friend", "id": "wxid_abc", "name": "张三"},
          {"type": "group",  "id": "12345@chatroom", "name": "客户群"}
        ]}
      ]
    }

``id`` 用稳定标识：好友存 wxid，群存 ``xxx@chatroom``；``name`` 只是展示用
快照，昵称改了也不影响发送。配置存在数据目录的 ``broadcast_groups.json``，
不写进 ``.env``（.env 是纯文本 key=value，装不下嵌套结构且并发写会互相覆盖）。

线程安全：所有写操作经模块级锁 + 临时文件原子替换；每次读取都重新读盘，
改完无需重启机器人。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.config import webot_data_path

logger = logging.getLogger(__name__)

CONFIG_FILE = "broadcast_groups.json"
CONFIG_VERSION = 1

MAX_GROUPS = 100
MAX_NAME_CHARS = 60
MAX_TARGETS_PER_GROUP = 500
MAX_TOTAL_TARGETS = 5000
VALID_TYPES = ("friend", "group")

_lock = threading.RLock()


def config_path() -> Path:
    """返回当前数据目录下的分组配置文件路径（每次现算，支持运行时改数据目录）。"""
    return webot_data_path(CONFIG_FILE)


def _default_config() -> dict:
    return {"version": CONFIG_VERSION, "groups": []}


def load() -> dict:
    """读取配置；文件不存在或损坏时回退到空配置，绝不抛出影响主流程。"""
    path = config_path()
    if not path.exists():
        return _default_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read %s, using empty config: %s", path, exc)
        return _default_config()
    if not isinstance(raw, dict):
        return _default_config()
    groups = raw.get("groups")
    if not isinstance(groups, list):
        return _default_config()
    return {"version": CONFIG_VERSION, "groups": groups}


def groups() -> list[dict]:
    """返回分组列表（只读视图，调用方不要原地修改）。"""
    return load().get("groups", [])


def validate(data: Any) -> dict:
    """校验并规范化整个配置，任何不合法结构都抛 ``ValueError``。

    规则：分组名非空、互不重复；目标 ``type`` 必须是 friend/group；
    目标 id 非空；同组内 (type, id) 去重；数量不超过上限。
    """
    if not isinstance(data, dict):
        raise ValueError("配置必须是 JSON 对象")
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list):
        raise ValueError("groups 必须是数组")
    if len(raw_groups) > MAX_GROUPS:
        raise ValueError(f"分组数量不能超过 {MAX_GROUPS} 个")

    cleaned: list[dict] = []
    seen_names: set[str] = set()
    total_targets = 0

    for index, item in enumerate(raw_groups):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 个分组必须是对象")
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError(f"第 {index + 1} 个分组缺少名称")
        if len(name) > MAX_NAME_CHARS:
            raise ValueError(f"分组名「{name}」超过 {MAX_NAME_CHARS} 个字符")
        if name in seen_names:
            raise ValueError(f"分组名「{name}」重复")
        seen_names.add(name)

        targets = item.get("targets", [])
        if not isinstance(targets, list):
            raise ValueError(f"分组「{name}」的 targets 必须是数组")
        if len(targets) > MAX_TARGETS_PER_GROUP:
            raise ValueError(f"分组「{name}」最多放 {MAX_TARGETS_PER_GROUP} 个目标")

        cleaned_targets: list[dict] = []
        seen_targets: set[tuple[str, str]] = set()
        for pos, target in enumerate(targets):
            if not isinstance(target, dict):
                raise ValueError(f"分组「{name}」第 {pos + 1} 个目标必须是对象")
            target_type = str(target.get("type") or "").strip().lower()
            if target_type not in VALID_TYPES:
                raise ValueError(
                    f"分组「{name}」第 {pos + 1} 个目标的 type 只能是 friend 或 group"
                )
            target_id = str(target.get("id") or "").strip()
            if not target_id:
                raise ValueError(f"分组「{name}」第 {pos + 1} 个目标缺少 id")
            if target_type == "group" and "@" in target_id and not target_id.endswith("@chatroom"):
                raise ValueError(f"群聊 id「{target_id}」不是有效的 chat_id")
            key = (target_type, target_id)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            cleaned_targets.append({
                "type": target_type,
                "id": target_id,
                "name": str(target.get("name") or "").strip()[:MAX_NAME_CHARS],
            })

        total_targets += len(cleaned_targets)
        cleaned.append({"name": name, "targets": cleaned_targets})

    if total_targets > MAX_TOTAL_TARGETS:
        raise ValueError(f"所有分组的目标总数不能超过 {MAX_TOTAL_TARGETS} 个")
    return {"version": CONFIG_VERSION, "groups": cleaned}


def save(data: Any) -> dict:
    """校验并原子写入配置，返回规范化后的配置。"""
    cleaned = validate(data)
    path = config_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
    logger.info(
        "Broadcast groups saved: %d groups / %d targets",
        len(cleaned["groups"]),
        sum(len(g["targets"]) for g in cleaned["groups"]),
    )
    return cleaned


def find_group(name: str) -> dict | None:
    """按名称精确查找分组；找不到返回 ``None``（大小写不敏感）。"""
    wanted = str(name or "").strip().casefold()
    if not wanted:
        return None
    for group in groups():
        if str(group.get("name") or "").strip().casefold() == wanted:
            return group
    return None


def target_ids(group: dict) -> list[str]:
    """取出分组内所有目标的 id（好友 wxid / 群 chat_id），用于发送。"""
    return [
        str(target.get("id") or "").strip()
        for target in group.get("targets", [])
        if isinstance(target, dict) and str(target.get("id") or "").strip()
    ]
