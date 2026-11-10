"""MCP（Model Context Protocol）服务端。

把 WeChatBot 已采集的微信群聊、群成员、好友与消息数据通过标准 MCP
协议暴露给 Codex、Trae 等外部智能体，用于群聊与联系人数据分析（周报、运营复盘、客户跟进等）。
"""

from src.mcp_server.server import (
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    TOOLS,
    describe_server,
    ensure_api_key,
    get_settings,
    handle_http,
    handle_rpc,
    update_settings,
    verify_api_key,
)

__all__ = [
    "MCP_SERVER_NAME",
    "MCP_SERVER_VERSION",
    "TOOLS",
    "describe_server",
    "ensure_api_key",
    "get_settings",
    "handle_http",
    "handle_rpc",
    "update_settings",
    "verify_api_key",
]
