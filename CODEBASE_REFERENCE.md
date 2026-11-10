# WeChatBot 代码参考手册

> 微信消息总结机器人 — 完整代码架构与 API 参考文档
> 生成日期: 2026-06-11
> 最后更新: 2026-06-11
> 二开新增模块（系统群发分组、微信通讯录标签只读、消息发送 MCP 工具、品牌改名）统一收录于文末 [附录：WeChatBot 二次开发新增模块](#附录wechatbot-二次开发新增模块)；正文 §1–§5 仍描述二开前的既有架构，二者并存、互不覆盖。

---

## 📝 维护指南（修改代码前必读）

**本文档必须与代码同步更新。** 每次修改代码后，在 `git commit` 之前，按照以下规则更新本文档对应章节。

### 变更类型 → 更新位置速查表

| 代码变更 | 更新本文档的位置 | 具体操作 |
|---|---|---|
| 新增 `.env` 环境变量 | §1.1 环境变量表 | 添加一行：名称、类型、默认值、定义位置、消费位置 |
| 删除/重命名环境变量 | §1.1 + §5.1 | 更新对应行，同步修改 `.env` 模板 |
| 新增模块级常量 | §1.2 模块级常量表 | 添加一行：常量名、类型、值、所在文件、用途 |
| 新增函数/方法 | §2 对应文件的函数表 | 添加一行：函数名、描述、参数、返回值 |
| 删除函数 | §2 对应文件的函数表 | 删除对应行 |
| 修改函数签名（参数名/类型/默认值） | §2 对应函数条目 | 更新参数列 |
| 修改函数返回值 | §2 对应函数条目 | 更新返回值列 |
| 函数A 新增调用了函数B | §2 函数A条目 + §3 调用关系图 | 更新"调用了哪些函数"字段 + 更新 ASCII 调用链 |
| 新增源文件 | §1 + §2 新增小节 + §3 | 添加文件的常量/函数/依赖关系 |
| 删除源文件 | §1 + §2 删除对应小节 + §3 | 移除所有相关条目 |
| 新增功能模块 | §4 新增功能小节 | 按模板写：涉及文件、调用链、关键参数、表结构 |
| 修改现有功能逻辑 | §4 对应功能小节 | 更新调用链 ASCII 图 + 关键参数表 |
| 新增/修改 API 端点 | §4 功能D + §2 server.py 表 | 更新端点清单和函数表 |
| 新增/修改数据库表 | §4 对应功能小节 + §2 schema.py | 更新 DDL + 表说明 |
| 新增/修改前端组件 | §4 功能D + §2 新增前端文件小节 | 更新组件树和函数表 |
| 修改 `build.spec` | §5.2 | 更新打包配置说明 |
| 修改 `requirements.txt` | §5.3 | 更新依赖说明 |

### 更新格式规范

1. **函数签名使用代码块**: `def func_name(param: type = default) -> ReturnType:`
2. **调用链使用 ASCII 图**: 保持 `│ ├ └ →` 风格一致
3. **表格对齐**: 所有 Markdown 表格的列数和表头必须一致
4. **文件路径可点击**: 使用反引号包裹路径如 `` `src/bot.py` ``
5. **交叉引用**: 修改函数时，同时检查"调用了哪些函数"和"被哪些函数调用"两个方向
6. **以代码为准**: 不要凭记忆写文档，必要时重新阅读源码确认

### 快速定位命令

```bash
# 查找某个函数在文档中的所有出现位置
grep "函数名" CODEBASE_REFERENCE.md

# 查找某个参数
grep "参数名" CODEBASE_REFERENCE.md

# 查找某个文件
grep "文件名" CODEBASE_REFERENCE.md
```

---

## 目录

1. [全局变量/参数清单](#1-全局变量参数清单)
2. [函数清单](#2-函数清单)
3. [模块间关系图](#3-模块间关系图)
4. [功能模块展开](#4-功能模块展开)
   - [功能A: 消息获取 (WCDB直读)](#功能a-消息获取-wcdb直读)
   - [功能B: AI总结/聊天](#功能b-ai总结聊天)
   - [功能C: 主动发言](#功能c-主动发言)
   - [功能D: Web UI 和 API](#功能d-web-ui-和-api)
   - [功能E: 微信窗口操控](#功能e-微信窗口操控)
   - [功能F: 触发器系统](#功能f-触发器系统)
   - [功能G: 待办事项](#功能g-待办事项)
   - [功能H: 飞书集成](#功能h-飞书集成)
   - [功能I: 语音识别](#功能i-语音识别)
   - [功能J: 聊天记忆](#功能j-聊天记忆)
   - [功能K: macOS适配](#功能k-macos适配)
   - [功能L: 文生图](#功能l-文生图)
5. [配置文件和环境变量](#5-配置文件和环境变量)
6. [附录：WeChatBot 二次开发新增模块](#附录wechatbot-二次开发新增模块)

---

## 1. 全局变量/参数清单

### 1.1 环境变量 (`.env` 配置项)

所有环境变量均通过 `src/config.py` → `load_config()` → `BotConfig` 数据类加载。

| 环境变量名 | 类型 | 默认值 | 定义位置 | 消费位置 |
|---|---|---|---|---|
| `AI_BACKEND` | `str` | `"openai_compatible"` | `src/config.py:load_config()` | `src/summarize/__init__.py:create_summarizer()`, `src/web/server.py:_fetch_ai_models()` |
| `ANTHROPIC_API_KEY` | `str` | `""` | `src/config.py` | `src/summarize/claude_backend.py:ClaudeSummarizer.__init__()` |
| `ANTHROPIC_BASE_URL` | `str` | `"https://api.anthropic.com"` | `src/config.py` | `src/summarize/claude_backend.py` |
| `SUMMARIZE_MODEL` | `str` | `""` (需通过模型列表选择) | `src/config.py` | `src/bot.py:_log_banner()`, `src/summarize/claude_backend.py` |
| `DEEPSEEK_API_KEY` | `str` | `""` | `src/config.py` | `src/summarize/deepseek_backend.py:DeepSeekSummarizer.__init__()` |
| `DEEPSEEK_MODEL` | `str` | `""` (legacy preset 需显式填写) | `src/config.py` | `src/summarize/deepseek_backend.py`, `src/bot.py:_log_banner()` |
| `DEEPSEEK_BASE_URL` | `str` | `"https://api.deepseek.com"` | `src/config.py` | `src/summarize/deepseek_backend.py` |
| `OPENAI_API_KEY` | `str` | `""` (本地兼容服务可空) | `src/config.py` | `src/utils/ai_compat.py:openai_api_key_for_client()`, `src/summarize/openai_compatible_backend.py` |
| `OPENAI_BASE_URL` | `str` | `"https://api.openai.com/v1"` | `src/config.py` (经 `normalize_openai_base_url()` 规范化) | `src/summarize/openai_compatible_backend.py` |
| `OPENAI_MODEL` | `str` | `""` (需通过模型列表选择) | `src/config.py` | `src/summarize/openai_compatible_backend.py`, `src/bot.py:_log_banner()` |
| `WECHAT_BACKEND` | `str` | `"wcdb"` | `src/config.py` | `src/bot.py:_create_wechat_backend()` |
| `WECHAT_GROUPS` | `str` | `"*"` | `src/config.py` (经 `_decode_wechat_groups` URL解码) | `src/bot.py:_create_wechat_backend()`, `src/wechat/wcdb_backend.py:_resolve_groups()` |
| `WECHAT_FRIENDS` | `str` | `""` (不回复任何好友) | `src/config.py` (经 `_decode_wechat_friends`；空值不展开为 `*`) | `src/bot.py:_create_wechat_backend()`, `src/wechat/wcdb_backend.py:_resolve_friends(), _poll_cycle()` |
| `GROUP_CHAT_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:handle()` (群聊 @ 对话与主动发言) |
| `FRIEND_CHAT_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:_handle_friend_chat()`, `src/wechat/wcdb_backend.py:_poll_cycle()` |
| `WECHAT_DATA_DIR` | `str` | `""` | `src/config.py` | `src/wechat/data_dir.py`, `src/wechat/local_wcdb_client.py`, `src/voice/file_locator.py`, `src/web/server.py` |
| `WEBOT_DATA_DIR` | `str` | 当前应用目录下 `data/` (留空) | `src/config.py` | `src/config.py` 路径辅助函数；WeChatBot 自有 DB、日志、昵称、模板、群缓存、语音缓存、崩溃日志 |
| `BOT_DISPLAY_NAME` | `str` | `"群聊小助手"` | `src/config.py` (经 `_sanitize_display_name` 清洗) | `src/router.py:handle()` (多处), `src/bot.py:_log_banner()` |
| `ADMIN_WXID` | `str` | `""` | `src/config.py` | `src/router.py:handle()` (管理员命令判断) |
| `TRIGGER_KEYWORDS` | `list[str]` | 见下方默认值 | `src/config.py` | `src/trigger/detector.py:TriggerDetector.__init__()` |
| `SUMMARIZE_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:_handle_summary()` |
| `FALLBACK_WINDOW_HOURS` | `int` | `8` | `src/config.py` | `src/router.py:_handle_summary()` |
| `FUN_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:handle()` (抽签) |
| `PROACTIVE_ENABLED` | `bool` | `False` | `src/config.py` | `src/proactive/gate.py:ProactiveGate.should_speak()` |
| `PROACTIVE_RATE_WINDOW_SEC` | `int` | `120` | `src/config.py` | `src/proactive/rate_tracker.py:RateTracker.__init__()` |
| `PROACTIVE_RATE_QUIET` | `float` | `1.5` | `src/config.py` | `src/proactive/modes.py:build_modes()` |
| `PROACTIVE_RATE_CASUAL` | `float` | `4.0` | `src/config.py` | `src/proactive/modes.py` |
| `PROACTIVE_RATE_LIVELY` | `float` | `6.5` | `src/config.py` | `src/proactive/modes.py` |
| `PROACTIVE_RATE_BURST` | `float` | `8.5` | `src/config.py` | `src/proactive/modes.py` |
| `WELCOME_ENABLED` | `bool` | `False` | `src/config.py` | `src/router.py:handle()` |
| `STICKY_MENTION_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:MessageRouter.__init__()` |
| `STICKY_MENTION_TTL_SEC` | `int` | `60` | `src/config.py` | `src/proactive/sticky.py:StickyMentionTracker.__init__()` |
| `TODO_ENABLED` | `bool` | `True` | `src/config.py` | `src/router.py:MessageRouter.__init__()` |
| `TODO_GROUPS` | `list[str]` | `["*"]` | `src/config.py` | `src/router.py:_is_todo_group()` |
| `TODO_MAX_PER_GROUP` | `int` | `50` | `src/config.py` | `src/todo/store.py:TodoStore.add()` |
| `TODO_COMPLETED_RETENTION_DAYS` | `int` | `30` | `src/config.py` | `src/todo/store.py:TodoStore.cleanup()` |
| `TODO_DELETED_RETENTION_DAYS` | `int` | `30` | `src/config.py` | `src/todo/store.py:TodoStore.cleanup()` |
| `TODO_ADD_KEYWORDS` | `list[str]` | `["记一下","添加待办","新建待办","帮我记","待办"]` | `src/config.py` | `src/todo/handler.py:TodoHandler.handle()` |
| `TODO_COMPLETE_KEYWORDS` | `list[str]` | `["搞定","做完了","完成","完成了","done"]` | `src/config.py` | `src/todo/handler.py` |
| `TODO_DELETE_KEYWORDS` | `list[str]` | `["删掉","删除","取消","不要了"]` | `src/config.py` | `src/todo/handler.py` |
| `POLL_INTERVAL_SEC` | `float` | `1.0` | `src/config.py` | `src/bot.py:_create_wechat_backend()` → `WcdbBackend.__init__()` |
| `DEDUP_WINDOW_SEC` | `int` | `60` | `src/config.py` | (通过 config 传递，当前代码未直接使用) |
| `MAX_MESSAGES_FOR_SUMMARY` | `int` | `5000` | `src/config.py` | `src/router.py:_handle_summary()` |
| `CHUNK_SIZE` | `int` | `400` | `src/config.py` | `src/summarize/__init__.py:create_summarizer()` → 各后端 |
| `LOG_LEVEL` | `str` | `"INFO"` | `src/config.py` | `src/bot.py:run()` → `setup_logging()` |
| `LOG_FILE` | `str` | `"data/bot.log"` (legacy 默认跟随 `WEBOT_DATA_DIR`) | `src/config.py` | `src/bot.py:run()` → `setup_logging()` |
| `DB_PATH` | `str` | `"data/messages.db"` (legacy 默认跟随 `WEBOT_DATA_DIR`) | `src/config.py` | `src/bot.py:run()` → `initialize_db()` |
| `VOICE_ASR_ENABLED` | `bool` | `False` | `src/config.py` | `src/voice/pipeline.py:VoicePipeline.__init__()` |
| `VOICE_ASR_BACKEND` | `str` | `"local_whisper"` | `src/config.py` | `src/voice/asr.py:create_asr()` |
| `VOICE_ASR_LANGUAGE` | `str` | `"zh"` | `src/config.py` | `src/voice/pipeline.py:VoicePipeline.__init__()` |
| `VOICE_OPENAI_API_KEY` | `str` | `""` | `src/config.py` | `src/voice/asr.py:OpenAiWhisperASR.__init__()` |
| `VOICE_OPENAI_BASE_URL` | `str` | `""` | `src/config.py` | `src/voice/asr.py:OpenAiWhisperASR.__init__()` |
| `VOICE_LOCAL_MODEL` | `str` | `"small"` | `src/config.py` | `src/voice/asr.py:LocalWhisperASR.__init__()` |
| `VOICE_ASR_TO_SIMPLIFIED` | `bool` | `True` | `src/config.py` | `src/voice/asr.py` (各ASR后端) |
| `IMAGE_GEN_ENABLED` | `bool` | `False` | `src/config.py` | `src/router.py:handle()` (生图分支), `src/imagegen/generator.py:create_image_generator()` |
| `IMAGE_GEN_PROTOCOL` | `str` | `"openai_images"` | `src/config.py` | `src/imagegen/generator.py:ImageGenerator.__init__()` |
| `IMAGE_GEN_API_KEY` | `str` | `""` (本地兼容服务可空) | `src/config.py` | `src/imagegen/generator.py:ImageGenerator.__init__()` |
| `IMAGE_GEN_BASE_URL` | `str` | `""` | `src/config.py` | `src/imagegen/generator.py:ImageGenerator.__init__()` |
| `IMAGE_GEN_MODEL` | `str` | `""` (需通过模型列表选择) | `src/config.py` | `src/imagegen/generator.py:ImageGenerator.__init__()` |
| `IMAGE_GEN_SIZE` | `str` | `""` (留空由模型默认) | `src/config.py` | `src/imagegen/generator.py:ImageGenerator.generate()` |
| `IMAGE_GEN_KEYWORDS` | `list[str]` | 见下方默认值 | `src/config.py` | `src/router.py:_handle_image_gen()` → `src/imagegen/intent.py` |
| `FEISHU_EXPORT_ENABLED` | `bool` | `False` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_APP_ID` | `str` | `""` | `src/config.py` | `src/integrations/feishu/client.py:FeishuClient.__init__()` |
| `FEISHU_APP_SECRET` | `str` | `""` | `src/config.py` | `src/integrations/feishu/client.py` |
| `FEISHU_EXPORT_MODE` | `str` | `"knowledge"` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_EXPORT_WINDOW_HOURS` | `int` | `8` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_AUTO_SYNC_ENABLED` | `bool` | `False` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_AUTO_SYNC_MIN_MESSAGES` | `int` | `20` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_AUTO_SYNC_COOLDOWN_SEC` | `int` | `1800` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_KNOWLEDGE_BASE_NAME` | `str` | `"webot 群聊沉淀"` | `src/config.py` | `src/integrations/feishu/exporter.py` |
| `FEISHU_EXPORT_TRIGGER_KEYWORDS` | `list[str]` | `["同步到飞书","导出到飞书","写到飞书","沉淀到飞书"]` | `src/config.py` | `src/integrations/feishu/exporter.py:is_export_command()` |
| `FEISHU_*` (其他) | — | — | `src/config.py` | `src/integrations/feishu/` (spreadsheet/bitable/doc 模式) |
| `WEBOT_APP_HOME` | `str` | `""` (自动检测) | `src/config.py:_resolve_project_root()` | `src/config.py`, `src/web/server.py`, `desktop.py` |
| `WEBOT_ENV_FILE` | `str` | `""` | `src/config.py:find_env_file()` | `src/config.py` (显式指定 .env 路径) |
| `ONBOARDING_DONE` | `bool` | `False` | `.env` 写入 | `src/config.py:is_onboarding_done()`, `src/web/server.py`, `desktop.py`；步骤草稿存入 SQLite `onboarding_state` |
| `WCDB_KEY` | `str` | `""` | `.env` / 引导流程写入 | 兼容字段；纯 Python 读取器从微信内存自动取密钥，不再依赖该值；引导草稿副本存入 SQLite `onboarding_state.wcdb_key` |
| `MCP_ENABLED` | `bool` | `True` | `src/mcp_server/server.py:get_settings()` | `src/mcp_server/server.py:_check_access()`；关闭后 `/mcp`、`/mcp/sse` 返回 403 |
| `MCP_API_KEY` | `str` | `""` (空时由控制台生成) | `src/mcp_server/server.py:ensure_api_key()` / `update_settings()` | `src/mcp_server/server.py:verify_api_key()`；所有 MCP 请求需 `Authorization: Bearer <key>` 或 `X-API-Key`（`?key=` 仅限旧版 SSE） |
| `MCP_ALLOWED_HOSTS` | `str` (逗号分隔) | `""`（仅回环） | `src/mcp_server/server.py:_allowed_hosts()` | 追加可信 Host/Origin 域名（隧道、反向代理）；不配置时只允许 `127.0.0.1` / `localhost` / `::1` |
| `MCP_GROUPS` | `str` | `""`（全部） | `src/mcp_server/server.py:update_settings()` | `src/mcp_server/data.py:_parse_scope()`；可读取的群聊，空或 `*` = 全部，`none` = 禁止，其余逗号分隔的群 ID |
| `MCP_FRIENDS` | `str` | `""`（全部） | `src/mcp_server/server.py:update_settings()` | `src/mcp_server/data.py:_parse_scope()`；可读取的好友，空或 `*` = 全部，`none` = 禁止，其余逗号分隔的 wxid |
| `MCP_HISTORY_SOURCE` | `str` | `"auto"` | 环境变量 | `src/mcp_server/history.py:enabled()`；`messages` 表示关闭微信本地完整历史读取，只查 `messages.db` |
| `MAC_WECHAT_SEND_SHORTCUT` | `str` | `"enter"` | `desktop_mac.py` | `src/wechat/mac_ui_backend.py` |
| `MAC_CHAT_TITLE_CACHE_FILE` | `str` | `""` | 环境变量 | `src/wechat/mac_hybrid_backend.py` |
| `MAC_CHAT_TITLE_MAP` | `str` (JSON) | `""` | 环境变量 | `src/wechat/mac_hybrid_backend.py` |

### 1.2 模块级常量

| 常量名 | 类型 | 值 | 所在文件 | 用途 |
|---|---|---|---|---|
| `PROJECT_ROOT` | `Path` | 自动解析 | `src/config.py` | 项目根目录（支持 frozen EXE 模式） |
| `UI_DIR` | `Path` | `ui/dist/` | `src/web/server.py` | 前端静态文件目录 |
| `WEBSOCKET_GUID` | `bytes` | `b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"` | `src/web/server.py` | WebSocket 协议 GUID |
| `CONSOLIDATE_MSG_THRESHOLD` | `int` | `50` | `src/memory/consolidator.py` | 触发记忆合并的消息数阈值 |
| `CONSOLIDATE_TIME_THRESHOLD_SEC` | `int` | `3600` (1小时) | `src/memory/consolidator.py` | 触发记忆合并的时间阈值 |
| `MAX_NEW_MSGS_PER_CONSOLIDATION` | `int` | `400` | `src/memory/consolidator.py` | 每次合并最多处理的消息数 |
| `CHAT_CONTEXT_WINDOW_SEC` | `int` | `600` | `src/router.py` | AI 聊天上下文时间窗口(秒) |
| `MAX_CONTENT_LENGTH` | `int` | `997` | `src/router.py` | 发送给 AI 的单条消息最大字符数 |
| `MAX_CONTENT_LINES` | `int` | `20` | `src/router.py` | AI 聊天上下文最大行数 |
| `AT_MENTION_MAX_AGE_SEC` | `int` | `300` | `src/router.py` | @mention 消息最大有效年龄(秒) |
| `DEFAULT_POLL_SEC` | `float` | `1.0` | `src/wechat/wcdb_backend.py` | 默认轮询间隔 |
| `MAX_DEDUP_SIZE` | `int` | `5000` | `src/wechat/wcdb_backend.py` | 去重集合最大容量 |
| `MAX_CONSECUTIVE_ERRORS` | `int` | `5` | `src/wechat/wcdb_backend.py` | 连续错误触发重初始化阈值 |
| `WECHAT_PROCESS_NAMES` | `set` | `{"wechat.exe", "weixin.exe"}` | `src/wechat/window_controller.py` | 微信进程名集合 |
| `MIN_WINDOW_WIDTH` / `MIN_WINDOW_HEIGHT` | `int` | `200` | `src/wechat/window_controller.py` | 窗口最小尺寸验证 |
| `MSG_TYPE_MAP` | `dict` | 见代码 | `src/wechat/helpers.py` | 消息类型映射表 |
| `_FILE_EXT_LABELS` | `dict` | 见代码 | `src/wechat/helpers.py` | 文件扩展名 → 摘要显示类型(PDF/PPT/Word等) |
| `DEFAULT_NICKNAME_PATH` | `Path` | `<WEBOT_DATA_DIR>/nicknames.json` | `src/nickname.py` | 昵称映射文件路径 |
| `DEFAULT_WELCOME_CONFIG_PATH` | `Path` | `<WEBOT_DATA_DIR>/welcome_templates.json` | `src/welcome.py` | 欢迎模板文件路径 |
| `HEX_KEY_LEN` | `int` | `64` | `src/wechat/mac_weflow_client.py` | WCDB 密钥长度 |
| `_FIRST_RUN_ENV_DEFAULTS` | `dict[str, str]` | 见代码 | `src/web/server.py` | 重置为首次运行时需要从进程环境清除的 WeChatBot 配置键集合 |
| `_CACHE_MAX_ENTRIES` | `int` | `10000` | `src/voice/pipeline.py` | 语音缓存最大条目 |
| `_CACHE_TTL_SEC` | `int` | `604800` (7天) | `src/voice/pipeline.py` | 语音缓存过期时间 |
| `GENERATE_TIMEOUT_SEC` | `int` | `180` | `src/imagegen/generator.py` | 生图 API 请求超时 |
| `DOWNLOAD_TIMEOUT_SEC` | `int` | `120` | `src/imagegen/generator.py` | 外链图片下载超时 |
| `MAX_IMAGE_BYTES` | `int` | `20MB` | `src/imagegen/generator.py` | 单张生成图片最大体积 |
| `IMAGE_PASTE_SEND_DELAY` | `float` | `0.5` | `src/wechat/window_controller.py` | 图片粘贴后等待微信生成预览的延时(秒) |

### 1.3 触发关键词默认值

```python
# 定义位置: src/config.py BotConfig 数据类

trigger_keywords: list[str] = [
    "总结一下", "之前发了什么", "错过了什么", "summarize",
    "what did i miss", "聊天总结", "帮我总结", "前面说了什么",
    "说了啥", "发生了什么",
]

feishu_export_trigger_keywords: list[str] = [
    "同步到飞书", "导出到飞书", "写到飞书", "沉淀到飞书",
]

todo_add_keywords: list[str] = [
    "记一下", "添加待办", "新建待办", "帮我记", "待办",
]

todo_complete_keywords: list[str] = [
    "搞定", "做完了", "完成", "完成了", "done",
]

todo_delete_keywords: list[str] = [
    "删掉", "删除", "取消", "不要了",
]

image_gen_keywords: list[str] = [
    "画一张", "画一个", "画一幅", "画一只", "画个", "帮我画",
    "生成一张", "生成一幅", "生成图片", "生图", "来一张图", "画出来",
]
```

---

## 2. 函数清单

### 2.1 `src/config.py`

| 函数 | 行号 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `_decode_wechat_groups(raw)` | ~20 | URL解码微信群名称 | `raw: str` | `str` (逗号分隔的解码后群名) |
| `_sanitize_display_name(name)` | ~40 | 清理机器人显示名中的危险字符 | `name: str` | `str` |
| `_resolve_project_root()` | ~70 | 解析项目根目录(支持 EXE frozen 模式) | 无 | `Path` |
| `_clean_path_value(raw)` | ~90 | 清理路径配置值，去掉引号并展开环境变量 | `raw: str \| Path \| None` | `str` |
| `resolve_webot_data_dir(raw=None)` | ~97 | 解析 WeChatBot 自有数据目录；留空默认当前 `WEBOT_APP_HOME`/应用目录下 `data/` | `raw: str \| Path \| None` | `Path` |
| `get_webot_data_dir()` | ~113 | 从当前环境读取并返回 WeChatBot 自有数据目录 | 无 | `Path` |
| `webot_data_path(*parts)` | ~118 | 拼接 WeChatBot 自有数据目录下的文件/子目录路径 | `*parts: str \| Path` | `Path` |
| `resolve_webot_storage_path(raw, legacy_default)` | ~123 | 解析 WeChatBot 自有文件路径；`data/messages.db`、`data/bot.log` 等 legacy 默认跟随 `WEBOT_DATA_DIR`，显式自定义路径保留覆盖 | `raw: str \| Path \| None, legacy_default: str` | `Path` |
| `find_env_file()` | ~152 | 按优先级查找 .env 文件 | 无 | `Path \| None` |
| `_validate_config(kwargs)` | ~352 | 验证数值配置范围 | `kwargs: dict` | `None` (无效时抛 RuntimeError) |
| `load_config()` | ~471 | 从环境变量加载并验证配置，解析 `WEBOT_DATA_DIR`、`DB_PATH`、`LOG_FILE` 的有效路径 | 无 | `BotConfig` |
| `is_onboarding_done()` | ~637 | 检查引导流程是否完成 | 无 | `bool` |

### 2.2 `src/bot.py`

| 函数 | 行号 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `HealthMonitor.__init__()` | ~30 | 初始化健康监控器 | `summarizer, router, conn, backend, config, on_tick=None` | `None` |
| `HealthMonitor.start()` | ~45 | 启动健康监控守护线程 | 无 | `None` |
| `HealthMonitor.stop()` | ~50 | 停止健康监控 | 无 | `None` |
| `HealthMonitor._run()` | ~55 | 健康监控主循环(每30s推送, 每5min全检) | 无 | `None` |
| `HealthMonitor._tick()` | ~75 | 执行一次完整健康检查 | 无 | `None` |
| `HealthMonitor._check_db()` | ~100 | 检查数据库连接 | 无 | `str` ("OK" 或错误信息) |
| `HealthMonitor._check_wechat_hwnd()` | ~110 | 检查微信窗口句柄(缓存缺失/失效时调用 `find_hwnd()` 重扫) | 无 | `str` |
| `HealthMonitor._last_api_ago()` | ~130 | 最后一次 API 调用距今时间 | 无 | `str` |
| `HealthMonitor._write_status_json()` | ~140 | 写入 bot_status.json 状态文件 | 无 | `None` |
| `Bot.__init__(config)` | ~165 | 初始化 Bot 实例 | `config: BotConfig` | `None` |
| `Bot.run()` | ~170 | 初始化所有组件并启动 bot (阻塞) | 无 | `None` |
| `Bot._log_banner()` | ~260 | 打印启动横幅日志 | 无 | `None` |
| `Bot._create_wechat_backend(store)` | ~275 | 根据配置创建微信后端实例 | `store: MessageStore` | `AbstractWeChatBackend` 子类实例 |

### 2.3 `src/router.py`

| 函数 | 行号 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `MessageRouter.__init__()` | ~45 | 初始化消息路由器 | `store, detector, summarizer, admin_handler, nickname_service, config, feishu_export_service=None` | `None` |
| `MessageRouter._strip_markdown(text)` | ~65 | 去除 Markdown 格式(静态方法) | `text: str` | `str` |
| `MessageRouter.handle(msg)` | ~70 | 处理传入群聊消息的主入口；`GROUP_CHAT_ENABLED=false` 时跳过 @ 对话与主动发言（总结/生图/待办不受影响）；返回 `ImageReply` 时由后端走图片发送通道 | `msg: dict` | `str \| ImageReply \| None` (回复文本或图片) |
| `MessageRouter._load_group_names()` | ~115 | 加载 chat_id → 群名映射(懒加载) | 无 | `dict[str, str]` |
| `MessageRouter._is_todo_group(chat_id)` | ~125 | 判断群聊是否启用待办功能 | `chat_id: str` | `bool` |
| `MessageRouter._get_group_memory(chat_id)` | ~140 | 获取群聊记忆文本 | `chat_id: str` | `str` |
| `MessageRouter._handle_summary(msg)` | ~145 | 生成聊天总结 | `msg: dict` | `str \| None` |
| `MessageRouter._handle_chat(msg, clean_content, is_group=True)` | ~230 | 处理 @bot AI 对话；好友私聊时不加 `@` 前缀 | `msg: dict, clean_content: str, is_group: bool` | `str \| None` |
| `MessageRouter._handle_friend_chat(msg)` | ~210 | 处理已勾选好友的私聊消息：`FRIEND_CHAT_ENABLED=false` 直接返回；无需 @，仅文本/已转写语音自动回复，非文本与过期消息跳过 | `msg: dict` | `str \| None` |
| `MessageRouter._handle_image_gen(msg, clean_content)` | — | 处理 @bot 生图请求：提取提示词 → 调用 Images API → 返回 `ImageReply`，失败回文本错误 | `msg: dict, clean_content: str` | `ImageReply \| str` |
| `MessageRouter._handle_welcome(msg)` | ~280 | 发送新成员欢迎消息 | `msg: dict` | `str \| None` |
| `MessageRouter._handle_proactive_chat(msg, mode)` | ~305 | 处理主动发言 | `msg: dict, mode: ProactiveMode` | `str \| None` |

### 2.4 `src/summarize/base.py` (AbstractSummarizer)

| 函数 | 行号 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `chat(message, ...)` | ~20 | AI 对话响应 (@bot 或好友私聊)；上下文中的图片/表情/文件占位禁止脑补画面 | `message: str, context_messages=None, requester_name="", bot_name="", group_name="", group_memory="", is_private=False` | `str` |
| `proactive_chat(mode, context_messages, ...)` | ~50 | 主动发言；上下文中的图片/表情/文件占位禁止脑补画面 | `mode: ProactiveMode, context_messages: list[dict], bot_name="", group_name="", group_memory=""` | `str` |
| `summarize(messages, requester_name)` | ~80 | 生成结构化摘要 | `messages: list[dict], requester_name: str` | `SummaryResult` |
| `_multi_level_map_reduce(chunks, requester_name)` | ~100 | 多级 Map-Reduce 处理大量消息 | `chunks: list[list[dict]], requester_name: str` | `SummaryResult` |
| `format_summary_for_reply(result, requester_name)` | ~130 | 格式化摘要为微信回复 | `result: SummaryResult, requester_name: str` | `str` |
| `_summarize_direct(messages, requester_name)` | — | 直接总结(单次调用) | `messages: list[dict], requester_name: str` | `SummaryResult` |
| `_summarize_map_reduce(chunks, requester_name)` | ~110 | 标准 Map-Reduce | `chunks: list[list[dict]], requester_name: str` | `SummaryResult` |
| `_summarize_chunk(chunk, chunk_num, total, requester_name)` | — | 总结单个分块 | `chunk: list[dict], chunk_num: int, total: int, requester_name: str` | `str` |
| `_merge_chunk_summaries(chunk_summaries, requester_name)` | — | 合并分块摘要 | `chunk_summaries: list[str], requester_name: str` | `SummaryResult` |
| `consolidate_memory(existing_memory, new_messages)` | — | 更新群聊记忆 | `existing_memory: str, new_messages: list[dict]` | `str` |
| `_call_chat_api(system_prompt, messages)` | — | 执行对话 API 调用(抽象) | `system_prompt: str, messages: list[dict]` | `str` |
| `_split_into_chunks(messages)` | — | 将消息列表分块 | `messages: list[dict]` | `list[list[dict]]` |
| `_estimate_tokens(messages)` | — | 估算 token 数(静态) | `messages: list[dict]` | `int` |
| `_retry_with_backoff(call_fn, label)` | — | 带指数退避的重试执行 | `call_fn: Callable, label: str` | `T` |

### 2.5 `src/summarize/claude_backend.py` (ClaudeSummarizer)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(api_key, model, base_url, chunk_size, max_retries)` | 初始化 Messages 协议客户端；`model` 为空时报错 | API配置 | `None` |
| `_call_chat_api(system_prompt, messages)` | Messages 对话 API，使用所选 `self.model` | prompt + messages | `str` |
| `_summarize_direct(messages, requester_name)` | 直接总结(Messages Pydantic parse) | 消息列表 | `SummaryResult` |
| `_summarize_chunk(chunk, chunk_num, total, requester_name)` | 分块提取，使用所选 `self.model` | 分块消息 | `str` |
| `_merge_chunk_summaries(chunk_summaries, requester_name)` | 合并分块(Messages Pydantic parse) | 摘要列表 | `SummaryResult` |
| `consolidate_memory(existing_memory, new_messages)` | 记忆合并，使用所选 `self.model` | 现有记忆 + 新消息 | `str` |

### 2.6 `src/summarize/openai_compatible_backend.py` (OpenAICompatibleSummarizer)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(api_key, model, base_url, chunk_size, max_retries, extra_body=None)` | 初始化 Chat Completions 兼容客户端；`model` 为空时报错 | API配置 | `None` |
| `_call_chat_api(system_prompt, messages)` | 通用对话 API | prompt + messages | `str` |
| `_summarize_direct(messages, requester_name)` | 直接总结(tool calling + fallback) | 消息列表 | `SummaryResult` |
| `_summarize_chunk(chunk, chunk_num, total, requester_name)` | 分块提取 | 分块消息 | `str` |
| `_merge_chunk_summaries(chunk_summaries, requester_name)` | 合并分块(tool calling + fallback) | 摘要列表 | `SummaryResult` |
| `consolidate_memory(existing_memory, new_messages)` | 记忆合并 | 现有记忆 + 新消息 | `str` |
| `_create_chat_completion(...)` | 通用 Chat Completions 请求封装(模块内) | messages + options | `ChatCompletion` |
| `_loads_json_object(text)` | 解析普通文本/Markdown fenced JSON 中的 JSON object | `text: str` | `dict \| None` |
| `_parse_summary_from_response(response)` | 解析 tool call / JSON / 文本响应(模块级) | `response` | `SummaryResult` |

#### `src/summarize/deepseek_backend.py` (DeepSeekSummarizer preset)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(api_key, model, base_url, chunk_size, max_retries)` | 初始化 DeepSeek 预设(继承 OpenAICompatibleSummarizer) | API配置 | `None` |

### 2.7 `src/summarize/prompts.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `build_summary_prompt(messages, requester_name)` | 构建直接总结 XML prompt；非文本占位只按占位/文件名理解 | 消息列表 + 请求人 | `str` |
| `build_chunk_summary_prompt(messages, chunk_num, total_chunks, requester_name)` | 构建分块提取 prompt；非文本占位禁止脑补内容 | 消息 + 序号 | `str` |
| `build_merge_prompt(chunk_summaries, requester_name)` | 构建分块合并 prompt；合并非文本占位时不编造画面细节 | 摘要列表 | `str` |
| `_format_messages_xml(messages)` | 将消息格式化为 XML(内部) | 消息列表 | `str` |
| `_format_time(timestamp)` | Unix时间戳→HH:MM(内部) | `timestamp: int` | `str` |
| `_escape_xml(text)` | XML 特殊字符转义(内部) | `text: str` | `str` |

### 2.8 `src/wechat/wcdb_backend.py` (WcdbBackend)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(bot_display_name, groups, poll_sec, store, config)` | 初始化 WCDB 后端 | 配置参数 | `None` |
| `start(callback)` | 启动消息监听(阻塞) | `callback: MessageCallback` | `None` |
| `send_text(chat_id, content)` | 发送文本消息 | `chat_id: str, content: str` | `bool` |
| `stop()` | 停止监听 | 无 | `None` |
| `_reinitialize()` | 关闭并重开 WCDB(故障恢复) | 无 | `None` |
| `_record_text(record, *keys)` | 从 WCDB JSON 记录中取第一个非空文本字段 | `record: dict, *keys: str` | `str` |
| `_record_username(record)` | 兼容多种字段名提取 chat/contact username | `record: dict` | `str` |
| `_record_display_name(record, username)` | 从 session/contact 记录提取群显示名 | `record: dict, username: str` | `str` |
| `_records_from_payload(payload, *list_keys)` | 将 list/dict WCDB payload 规整为记录列表 | `payload, *list_keys: str` | `list[dict]` |
| `_safe_int(value, default=0)` | 安全解析缓存中的数字元数据 | `value, default: int = 0` | `int` |
| `_merge_chatrooms(target, source)` | 合并群聊元数据，优先保留真实群名 | `target: dict, source: dict` | `int` |
| `_chatrooms_from_records(records)` | 从 session/contact 记录收集 `@chatroom` 群聊元数据 | `records` | `dict[str, dict]` |
| `_chatrooms_from_contacts()` | 从联系人列表加载群聊，作为 session 缺失时的兜底 | 无 | `dict[str, dict]` |
| `_load_cached_group_names()` | 读取 `<WEBOT_DATA_DIR>/group_names.json` 群名映射（含 `active` 失效标记）；仅当 `wechat_account.txt` 记录与当前账号一致时使用 | 无 | `dict[str, dict]` |
| `_add_configured_chatroom_ids(chatrooms, live_ids=None)` | 接受 `WECHAT_GROUPS` 中直接配置的 `@chatroom` ID；不在 `live_ids` 中时标记 `active=False` | `chatrooms: dict, live_ids: set[str] \| None` | `int` |
| `_resolve_groups()` | 按 session → contacts → chat_room → 缓存 → 直接 ID 解析群组；缓存中已不存在的群标记 `active=False`，且不参与匹配/轮询 | 无 | `None` |
| `_prepare_account_caches()` | 启动/重初始化时比对账号标记；账号切换则清空旧群聊缓存并写入当前账号 | 无 | `None` |
| `_save_group_names(chatrooms)` | 持久化群名映射并写入当前账号标记 | `chatrooms: dict` | `None` |
| `_save_group_members(chat_members)` | 持久化群成员列表；仅在账号一致时合并旧缓存 | `chat_members: dict` | `None` |
| `_is_friend_username(username)` | 判断 session/contact 用户名是否可作为好友私聊（排除 `@chatroom`、`gh_`、系统账号） | `username: str` | `bool` |
| `_is_friend_contact(record)` | 按 `contact.db` 字段判定真实好友：`local_type=1` 且 `flag ∈ (1,3)`，排除 `delete_flag=1` | `record: dict` | `bool` |
| `_friends_from_records(records)` | 从 session/contact 记录构建好友元数据；备注 → 昵称 → 微信号(`alias`) → wxid 依次兜底，无备注/昵称的好友不会被丢弃 | `records` | `dict[str, dict]` |
| `_friends_from_contacts()` | 从联系人加载好友（contact.db 为权威来源，联系人备注优先） | 无 | `dict[str, dict]` |
| `_load_cached_friend_names()` | 读取 `<WEBOT_DATA_DIR>/friend_names.json` 好友映射（含 `active` 失效标记）；账号不一致的缓存直接丢弃 | 无 | `dict[str, dict]` |
| `_save_friend_names(friends)` | 持久化好友映射（`{"account", "friends"}` 结构），供 Web UI 勾选列表使用 | `friends: dict` | `None` |
| `_check_account_switch()` | 每 30 秒检测微信是否已换号登录；是则重初始化并刷新群聊/好友数据 | 无 | `bool` |
| `_resolve_friends()` | 发现全部好友并写入缓存；通讯录中已不存在的好友标记 `active=False` 且不参与匹配/轮询；仅解析 `WECHAT_FRIENDS` 勾选的好友到 `_friend_ids` | 无 | `None` |
| `_poll_cycle(callback)` | 单次轮询周期；先群聊后好友私聊；`FRIEND_CHAT_ENABLED=false` 时完全跳过好友轮询（不存储、不回复） | `callback: MessageCallback` | `None` |
| `_poll_group(group_name, talker, callback, is_group=True)` | 轮询单个聊天消息；用 `_raw_message_key()` 去重、自发内容按聊天排除后记录新消息/join 日志再提交线程池 | `group_name, talker, callback, is_group` | `None` |
| `_handle_message(group_name, talker, standardized, callback)` | 处理单条消息(线程池)；回复为 `ImageReply` 时走 `_send_image_and_confirm()` 图片通道 | `group_name, talker, standardized, callback` | `None` |
| `_stable_id_text(value)` | 过滤 WCDB 空值/`0` 占位 ID，避免把所有 `server_id=0` 消息视为同一条 | `value` | `str` |
| `_raw_message_key(msg, talker)` | 生成轮询去重和消息 ID 使用的稳定群内原始键；优先非零 server/local ID，否则用发送人+内容+时间+类型 | `msg: dict, talker: str` | `str` |
| `_standardize(msg, group_name, talker, is_group=True)` | 标准化WCDB原始消息；图片/表情/文件转干净摘要占位；@mention 精确+模糊匹配(含字面 @name)，输出 `bot_mention_text` | `msg: dict, group_name: str, talker: str, is_group: bool` | `dict \| None` |
| `_send_and_confirm(group_name, talker, content)` | 通过键盘发送；成功后按 `(talker, content, timestamp)` 写入 `_recent_sends` 供同群自发自排除 | `group_name, talker, content` | `bool` |
| `_send_image_and_confirm(group_name, talker, image_path)` | 通过剪贴板粘贴发送生成图片；成功后按 `(talker, "[图片]", timestamp)` 写入 `_recent_sends` 防自触发 | `group_name, talker, image_path` | `bool` |
| `_get_voice()` | 懒初始化语音识别管道 | 无 | `VoicePipeline \| None \| False` |
| `_try_voice(msg)` | 尝试语音识别 | `msg: dict` | `str \| None` |

### 2.8.1 `src/wechat/data_dir.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `_extract_paths_from_command_line(command_line)` | 从微信子进程命令行提取 `--wechat-files-path` | `command_line: str` | `list[str]` |
| `_extract_paths_from_args(args)` | 从进程 argv 提取 `--wechat-files-path` | `args: Sequence[str]` | `list[str]` |
| `_wechat_files_paths_from_processes()` | 通过 `psutil` 扫描运行中的 WeChat/Weixin 进程，提取微信 4.x 数据目录 | 无 | `list[str]` |
| `_default_candidate_dirs()` | 返回 Documents/AppData/OneDrive 下的常见微信数据根目录候选 | 无 | `list[Path]` |
| `normalize_wechat_data_dir(path)` | 将用户输入/进程参数规范化为包含 `wxid_*` 的父目录 | `path: str \| Path` | `Path \| None` |
| `list_accounts_in_data_dir(path)` | 列出指定数据目录下带 `session.db` 的微信账号 | `path: str \| Path` | `list[WeChatAccountPath]` |
| `find_wxid_and_dbpath(custom_base_dir)` | 按自定义路径、微信进程参数、默认目录顺序检测账号和数据根目录 | `custom_base_dir: str = ""` | `tuple[str, str]` |
| `detect_default_data_dir()` | 返回自动检测到的微信数据根目录，失败返回空字符串 | 无 | `str` |

### 2.9 `src/wechat/local_wcdb_client.py` (LocalWcdbClient)

纯 Python WCDB 读取客户端，已在 Windows 后端取代 `wcdb_client.py`（原 `wcdb_api.dll` ctypes 方案）。密钥从 `Weixin.exe` 内存提取，数据库逐页解密后交给 `sqlite3`，不再依赖任何原生 DLL。

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(dll_dir=None, config_path=None)` | 兼容原客户端签名 | `dll_dir: str \| None, config_path: str \| None` | `None` |
| `init()` | 定位微信数据目录并打开 `WeChatDB`；会话库无密钥时抛出中文错误 | 无 | `None` |
| `open()` | 兼容钩子（实际打开在 `init()`） | 无 | `bool` |
| `close()` / `health()` | 释放引用 / 健康检查 | 无 | `None` / `bool` |
| `get_sessions(limit=500)` | 会话列表，并补全 `nick_name` / `display` | `limit: int` | `list[dict]` |
| `get_contacts(limit=0)` | 从 `contact.db` 读取联系人（30 秒缓存）；`limit<=0` 返回全部，并携带 `local_type`/`flag`/`alias`，排除当前账号自己 | `limit: int` | `list[dict]` |
| `account` (property) | 当前实际打开的微信账号目录名（如 `wxid_rli50t0h8lfd22_0111`） | 无 | `str` |
| `resolve_nickname(wxid)` / `get_display_names(wxids)` | wxid → 备注/昵称 | `wxid: str` / `wxids: list[str]` | `str` / `dict[str, str]` |
| `get_group_members(chatroom)` | 群成员列表（60 秒缓存） | `chatroom: str` | `list[dict]` |
| `get_messages(talker, limit=50, offset=0)` | 消息列表，映射为 `sender_username` / `message_content` / `local_type` / `create_time` 等后端字段 | `talker: str, limit: int, offset: int` | `list[dict]` |

### 2.9.1 `src/wechat/wxdb_reader.py` (WeChatDB)

从 `wechatauto-replica` 1.2.10（Apache-2.0）移植的微信 4.x SQLCipher 读取实现：`Config.Cipher` 内存扫描取密钥、按页 AES-CBC 解密到临时缓存、`sqlite3` 查询。除 `logging` 外无内部包依赖，可选 `zstandard` 解码长文本消息。

**账号选择（单账号原则）**：微信 PC 同一实例只允许一个账号在线；历史账号目录（`wxid_*_xxxx`）只是旧登录残留。自动模式（不显式传 `account`）下，初始化时用 `Weixin.exe` 进程内存密钥对每个账号目录做页 1 HMAC 校验，能解开的才是当前登录账号（`_select_account_by_keys(..., force=True)`）；不再合并其它账号的 `keys.json` 缓存，避免旧账号缓存“看起来可解密”导致静默读错账号。最近一次校验通过的账号写入 `%TEMP%/wechatauto_db/last_account.txt`，微信未运行时作为 mtime 之外的兜底。显式传入 `account` 时保持调用方指定账号，不做自动切换。

### 2.9.2 `src/wechat/wcdb_client.py` (WcdbNativeClient, 已弃用)

旧 `wcdb_api.dll` 方案保留供 macOS/测试参考，Windows 后端不再实例化。该 DLL 带在线 DRM 与自毁逻辑，加载时会触发 `wcdb_init failed` 或直接删除自身，启动报 `wcdb_api.dll not found` 即源于此。

### 2.10 `src/wechat/window_controller.py` (WeChatWindowController)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__()` | 初始化窗口控制器 | 无 | `None` |
| `find_hwnd(force=False)` | 查找微信窗口 HWND；可用性仅按尺寸过滤(隐藏/最小化的主窗口也可选，由 `activate()` 恢复) | `force: bool` | `int \| None` |
| `_validate_hwnd(hwnd)` | 验证 HWND 有效性 | `hwnd: int` | `bool` |
| `invalidate_cache()` | 清除 HWND 缓存 | 无 | `None` |
| `activate(hwnd)` | 激活微信窗口(4层策略) | `hwnd: int` | `bool` |
| `navigate_to_chat(hwnd, group_name)` | 键盘导航到指定群聊 | `hwnd: int, group_name: str` | `bool` |
| `send_message(hwnd, text)` | 键盘发送消息(Ctrl+V→Enter) | `hwnd: int, text: str` | `bool` |
| `send_image_message(hwnd, image_path)` | 键盘发送图片：剪贴板写入 CF_DIB → Ctrl+V 粘贴 → 等待预览生成 → Enter 发送 | `hwnd: int, image_path: Path` | `bool` |
| `_set_clipboard_image(image_path)` | 将图片以 CF_DIB 格式写入剪贴板(PIL 转 BMP 后去掉 14 字节文件头)，失败重试 3 次 | `image_path: Path` | `bool` |
| `send_to_chat(group_name, text, max_retries=2)` | 完整文本发送管道(主入口) | `group_name: str, text: str, max_retries: int` | `bool` |
| `send_image_to_chat(group_name, image_path, max_retries=2)` | 完整图片发送管道：find → activate → navigate → 粘贴发送 | `group_name: str, image_path, max_retries: int` | `bool` |
| `_run_send_pipeline(group_name, describe, payload, send_fn, max_retries)` | 文本/图片共用的发送管道；`describe` 用于成功/失败日志，失败详情日志记录实际 `payload` | `group_name, describe: str, payload, send_fn, max_retries` | `bool` |
| `_score_window(hwnd)` | 给窗口打分(模块级)；最小化窗口用 `GetWindowPlacement` 正常位置矩形代替 -16000 占位 | `hwnd: int` | `WindowCandidate` |
| `_get_process_name(pid)` | 获取进程名(模块级) | `pid: int` | `str` |
| `get_foreground_info()` | 获取前台窗口诊断信息 | 无 | `str` |

### 2.11 `src/wechat/extract_key.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `extract_wcdb_key(require_restart=True, on_progress=None)` | 提取 WCDB 解密密钥(主入口)；优先纯 Python 内存扫描，失败后回退 wx_key.dll Hook | `require_restart: bool, on_progress: Callable \| None` | `str \| None` (64字符hex) |
| `_extract_key_via_memory()` | 通过 `wxdb_reader.WeChatDB` 从微信内存提取密钥，无需重启微信 | 无 | `str \| None` |
| `_find_wechat_pid()` | 查找微信进程 PID(内部) | 无 | `int \| None` |
| `_find_wx_key_dll()` | 定位 wx_key.dll(内部) | 无 | `str \| None` |
| `_verify_dll_loadable(dll_path)` | 预检查 DLL 是否能加载(内部) | `dll_path: str` | `str \| None` (None=OK, str=错误信息) |
| `_hook_and_poll(pid, dll_path, timeout=180)` | 安装 Hook 并轮询密钥(内部) | `pid: int, dll_path: str, timeout: int` | `str \| None` |
| `extract_aes_key()` | 兼容包装 | 无 | `str \| None` |
| `decrypt_wcdb_key(aes_hex)` | 验证hex密钥有效性 | `aes_hex: str` | `str \| None` |

### 2.12 `src/wechat/helpers.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `normalize_msg_type(raw_type)` | 标准化消息类型码；支持数字字符串和中文/英文类型名 | `raw_type: Any` | `int` |
| `format_nontext_content(raw_type, raw_content="")` | 非文本消息摘要；图片/表情/视频提取大小，文件/链接提取标题、扩展名和大小，避免 XML 泄漏进总结 | `raw_type: Any, raw_content: str` | `str` |
| `_format_media_placeholder(label, raw_content)` | 格式化图片/表情/视频占位，解析 XML 中的大小字段 | `label: str, raw_content: str` | `str` |
| `_format_app_message(raw_content)` | 格式化 appmsg/文件/链接消息，提取标题、描述、扩展名和大小 | `raw_content: str` | `str` |
| `_format_plain_app_content(raw_content)` | 格式化没有 XML 的文件/链接消息，普通文件名或路径只保留文件名和类型 | `raw_content: str` | `str` |
| `_file_display_name(title)` | 将文件标题/路径清洗为可展示文件名 | `title: str` | `str` |
| `_parse_wechat_xml(raw_content)` | 从微信内容中解析 XML payload | `raw_content: str` | `Element \| None` |
| `_extract_xml_payload(raw_content)` | 去掉群消息前缀并提取 `<msg>/<appmsg>/<img>/<emoji>/<videomsg>` XML 起点 | `raw_content: str` | `str` |
| `_first_xml_text(root, names)` | 读取第一个非空 XML 节点文本 | `root: Element, names: tuple[str, ...]` | `str` |
| `_has_element(root, name)` | 判断 XML 树是否包含指定元素 | `root: Element, name: str` | `bool` |
| `_format_size(raw_size)` | 字节数格式化为 B/KB/MB/GB | `raw_size: Any` | `str` |
| `generate_message_id(*fields)` | 生成稳定消息 ID(MD5) | `*fields: Any` | `str` |
| `DedupSet.__init__(max_size)` | 初始化去重集合 | `max_size: int` | `None` |
| `DedupSet.add(item)` | 添加并自动裁剪 | `item: str` | `None` |

### 2.13 `src/wechat/keyboard.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `press_key(vk)` | 发送单键按下/释放 | `vk: int` | `None` |
| `send_combo(mod_vk, key_vk)` | 发送组合键 | `mod_vk: int, key_vk: int` | `None` |

### 2.14 `src/proactive/gate.py` (ProactiveGate)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(config)` | 初始化主动发言门控 | `config: BotConfig` | `None` |
| `should_speak(msg)` | 判断是否触发 AI 评估 (4层门控) | `msg: dict` | `tuple[bool, ProactiveMode \| None, str]` |
| `record_eval(chat_id)` | 记录评估时间 | `chat_id: str` | `None` |
| `record_silence(chat_id)` | 累加静默计数(指数退避) | `chat_id: str` | `None` |
| `record_speech(chat_id)` | 重置静默计数 | `chat_id: str` | `None` |
| `get_consecutive_silence(chat_id)` | 获取连续静默次数 | `chat_id: str` | `int` |

### 2.15 `src/proactive/modes.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `build_modes(config)` | 从配置构建模式列表 | `config: BotConfig` | `list[ProactiveMode]` |
| `get_modes(config)` | 获取模式列表(模块缓存) | `config: BotConfig` | `list[ProactiveMode]` |
| `reset_modes()` | 重置模式缓存 | 无 | `None` |
| `lookup_mode(rate, config)` | 根据消息速率查找模式 | `rate: float, config: BotConfig` | `ProactiveMode` |

### 2.16 `src/proactive/rate_tracker.py` (RateTracker)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(window_sec)` | 初始化速率追踪器 | `window_sec: int` | `None` |
| `record(chat_id)` | 记录一条消息 | `chat_id: str` | `None` |
| `cleanup()` | 清理过期条目 | 无 | `None` |
| `rate(chat_id)` | 返回消息速率(条/分钟) | `chat_id: str` | `float` |
| `count(chat_id)` | 返回窗口内消息数 | `chat_id: str` | `int` |
| `clear(chat_id)` | 清除群聊追踪数据 | `chat_id: str` | `None` |

### 2.17 `src/proactive/sticky.py` (StickyMentionTracker)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(ttl_sec)` | 初始化粘性@mention追踪 | `ttl_sec: int` | `None` |
| `register(chat_id, sender_id)` | 注册粘性@mention | `chat_id: str, sender_id: str` | `None` |
| `consume(chat_id, sender_id)` | 消费(原子检查+删除) | `chat_id: str, sender_id: str` | `bool` |
| `clear(chat_id, sender_id)` | 显式移除 | `chat_id: str, sender_id: str` | `None` |

### 2.18 `src/memory/consolidator.py` (MemoryConsolidator)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(store, summarizer)` | 初始化记忆合并器 | `store: MessageStore, summarizer: AbstractSummarizer` | `None` |
| `check_and_consolidate(chat_id)` | 检查并执行合并 | `chat_id: str` | `bool` |

### 2.19 `src/db/schema.py` (initialize_db / ThreadSafeConnection)

| 函数/类 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `initialize_db(db_path)` | 建表并返回线程安全连接代理 | `db_path: str` | `ThreadSafeConnection` |
| `ThreadSafeConnection.execute(sql, params)` | 加锁执行并物化结果游标 | `sql, params` | `_CursorProxy` |
| `ThreadSafeConnection.__enter__/__exit__` | 事务上下文(commit/rollback)，与 execute 可重入 | — | — |

> 主连接在轮询线程池、Web 服务、健康监控之间共享；sqlite3 连接跨线程
> 并发使用会偶发 InterfaceError/UNIQUE 错误导致丢消息，故用单一 RLock
> 串行化所有调用。TodoStore 自行开短连接，不受影响。

### 2.20 `src/db/store.py` (MessageStore)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `insert_message(msg)` | 插入消息+更新last-message游标 | `msg: dict` | `bool` |
| `log_trigger(chat_id, requester_id, trigger_msg_id)` | 记录触发事件 | `chat_id, requester_id, trigger_msg_id: str` | `None` |
| `cleanup_old_triggers()` | 清理7天前的触发记录 | 无 | `int` |
| `get_sender_display_name(sender_id)` | 查找已知显示名 | `sender_id: str` | `str \| None` |
| `get_user_last_timestamp(chat_id, sender_id)` | 获取用户最后发言时间 | `chat_id, sender_id: str` | `int \| None` |
| `get_user_previous_timestamp(chat_id, sender_id, before_ts)` | 获取用户在某时间前的最后发言 | `chat_id, sender_id: str, before_ts: int` | `int \| None` |
| `get_messages_since(chat_id, since_ts, until_ts, limit)` | 获取时间窗口内消息 | `chat_id, since_ts, until_ts, limit` | `list[dict]` |
| `was_recently_triggered(chat_id, window_sec)` | 检查最近是否触发过 | `chat_id: str, window_sec: int` | `bool` |
| `get_group_memory(chat_id)` | 获取群聊记忆 | `chat_id: str` | `dict \| None` |
| `upsert_group_memory(chat_id, memory_text, message_count, last_message_id)` | 更新/插入群聊记忆 | `chat_id, memory_text, message_count, last_message_id` | `None` |
| `get_new_message_count(chat_id, since_message_id)` | 统计新消息数 | `chat_id: str, since_message_id: str \| None` | `int` |
| `get_messages_since_id(chat_id, since_message_id, limit)` | 获取某ID之后的消息 | `chat_id, since_message_id, limit` | `list[dict]` |

### 2.21 `src/todo/store.py` (TodoStore)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(db_path)` | 初始化待办存储 | `db_path: str` | `None` |
| `add(chat_id, content, creator_id, creator_name, max_per_group)` | 添加待办 | 群/内容/创建者 | `TodoResult` |
| `complete(chat_id, target, operator_id, operator_name)` | 完成待办 | 群/目标/操作者 | `TodoResult` |
| `delete(chat_id, target, operator_id, operator_name)` | 软删除待办 | 群/目标/操作者 | `TodoResult` |
| `restore(chat_id, target)` | 恢复已删除待办 | 群/目标 | `TodoResult` |
| `list_active(chat_id)` | 列出活跃待办 | `chat_id: str` | `TodoResult` |
| `list_completed(chat_id)` | 列出已完成 | `chat_id: str` | `TodoResult` |
| `list_deleted(chat_id)` | 列出已删除 | `chat_id: str` | `TodoResult` |
| `clear_completed(chat_id)` | 清空已完成 | `chat_id: str` | `TodoResult` |
| `clear_deleted(chat_id)` | 清空已删除 | `chat_id: str` | `TodoResult` |
| `cleanup(chat_id, completed_retention_days, deleted_retention_days)` | 自动清理过期待办 | `chat_id, completed_retention_days, deleted_retention_days` | `None` |
| `get_all(status, chat_id, search)` | 获取待办列表(管理UI) | `status, chat_id, search` | `list[TodoItem]` |
| `get_counts(chat_id)` | 获取各状态计数 | `chat_id: str` | `dict[str, int]` |
| `get_active_groups()` | 获取有活跃待办的群 | 无 | `list[str]` |

### 2.22 `src/todo/handler.py` (TodoHandler)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(store, config)` | 初始化待办命令处理器 | `store: TodoStore, config` | `None` |
| `handle(clean_content, chat_id, sender_id, sender_name, is_admin)` | 解析并执行待办命令 | `clean_content, chat_id, sender_id, sender_name, is_admin` | `TodoResult \| None` |
| `_contains_any(text, keywords)` | 子串匹配(静态) | `text: str, keywords: list[str]` | `bool` |
| `_match_prefix(text, keywords)` | 前缀匹配(静态, 长关键词优先) | `text: str, keywords: list[str]` | `tuple[Optional[str], str]` |
| `format_todo_reply(result, sender_name)` | 格式化待办回复(模块级) | `result: TodoResult, sender_name: str` | `str` |

### 2.23 `src/nickname.py` (NicknameService)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(path)` | 初始化昵称服务 | `path: Path \| str` | `None` |
| `load(force=False)` | 加载昵称映射(带缓存) | `force: bool` | `dict[str, str]` |
| `resolve_wxids(text)` | 替换文本中所有 wxid | `text: str` | `str` |
| `resolve_name(wxid)` | 解析单个 wxid | `wxid: str` | `str` |
| `update(wxid, nickname)` | 添加/更新昵称映射 | `wxid: str, nickname: str` | `None` |
| `remove(wxid)` | 删除昵称映射 | `wxid: str` | `None` |
| `merge_manual(overrides)` | 批量合并手动覆盖 | `overrides: dict[str, str]` | `None` |

### 2.24 `src/welcome.py` (WelcomeManager)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `WelcomeManager.__init__(path)` | 初始化欢迎管理器 | `path: Path \| str` | `None` |
| `WelcomeManager.load()` | 加载配置 | 无 | `dict` |
| `WelcomeManager.save(data)` | 原子写入配置 | `data: dict` | `None` |
| `WelcomeManager.resolve_message(chat_id, new_member_id)` | 解析欢迎消息 | `chat_id: str, new_member_id: str` | `str \| None` |
| `get_welcome_manager()` | 获取模块单例(模块级) | 无 | `WelcomeManager` |

### 2.25 `src/admin.py` (AdminCommandHandler)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(nickname_service)` | 初始化管理员命令处理器 | `nickname_service: NicknameService` | `None` |
| `handle(content, requester_name)` | 解析并执行管理命令 | `content: str, requester_name: str` | `str \| None` |
| `_cmd_rename(content, requester_name)` | 处理"改名"命令 | `content: str, requester_name: str` | `str \| None` |
| `_cmd_delete_nickname(content, requester_name)` | 处理"删除昵称"命令 | `content: str, requester_name: str` | `str \| None` |

### 2.26 `src/fun.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `load_lots_config()` | 读取抽签配置 | 无 | `dict` |
| `save_lots_config(data)` | 保存抽签配置 | `data: dict` | `None` |
| `reset_lots_cache()` | 清除抽签缓存 | 无 | `None` |
| `draw_lots(requester_name)` | 抽签 | `requester_name: str` | `str` |

### 2.27 `src/voice/pipeline.py` (VoicePipeline)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `VoicePipeline.__init__(config)` | 初始化语音管道 | `config` | `None` |
| `VoicePipeline.process(msg)` | 转写语音消息 | `msg: dict` | `str \| None` |
| `VoicePipeline.flush()` | 持久化缓存 | 无 | `None` |

### 2.28 `src/voice/asr.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `LocalWhisperASR.transcribe(audio_path, language)` | 本地 Whisper 转写 | `audio_path: Path, language: str` | `TranscribeResult` |
| `OpenAiWhisperASR.transcribe(audio_path, language)` | OpenAI Whisper API 转写 | `audio_path: Path, language: str` | `TranscribeResult` |
| `create_asr(config)` | ASR 工厂函数 | `config` | `AbstractASR` |

### 2.29 `src/voice/decoder.py` (SilkDecoder)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `SilkDecoder.decode(audio_path)` | 解码 SILK/AMR → WAV | `audio_path: Path` | `Path` |

### 2.30 `src/voice/file_locator.py` (VoiceFileLocator)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `VoiceFileLocator.__init__(wechat_data_dir)` | 初始化文件定位器 | `wechat_data_dir: str` | `None` |
| `VoiceFileLocator.find_voice_file(msg)` | 查找语音文件 | `msg: dict` | `Path \| None` |

### 2.31 `src/integrations/feishu/client.py` (FeishuClient)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(app_id, app_secret, base_url, ...)` | 初始化飞书客户端 | 认证信息 | `None` |
| `tenant_access_token()` | 获取/刷新 tenant token | 无 | `str` |
| `append_spreadsheet_rows(...)` | 电子表格追加行 | `spreadsheet_token, range_name, rows` | `dict` |
| `create_bitable_record(...)` | 创建多维表格记录 | `app_token, table_id, fields` | `dict` |
| `create_bitable_app(name, folder_token)` | 创建多维表格应用 | `name, folder_token` | `dict` |
| `create_bitable_table(...)` | 创建数据表 | `app_token, table_name, fields` | `dict` |
| `create_docx_document(title, folder_token)` | 创建文档 | `title, folder_token` | `dict` |
| `create_docx_blocks(document_id, block_id, children)` | 文档追加内容 | `document_id, block_id, children` | `dict` |
| `create_docx_with_markdown(title, markdown, folder_token)` | 创建文档(含markdown内容) | `title, markdown, folder_token` | `dict` |

### 2.32 `src/integrations/feishu/exporter.py` (FeishuExportService)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `__init__(config, store, summarizer, client, resource_store, classifier)` | 初始化导出服务 | 各依赖 | `None` |
| `is_export_command(content)` | 判断是否飞书导出命令 | `content: str` | `bool` |
| `export_recent_chat(trigger_msg)` | 导出最近聊天(手动) | `trigger_msg: dict` | `FeishuExportResult` |
| `maybe_auto_export(msg)` | 自动同步(静默) | `msg: dict` | `FeishuExportResult \| None` |

### 2.33 `src/utils/ai_compat.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `normalize_ai_backend(raw)` | 将 `chat-completions` / openai / new-api / one-api / litellm / openrouter 等别名归一化为 `openai_compatible`，将 `messages` / anthropic 等别名归一化为 `claude` | `raw: str` | `str` |
| `normalize_openai_base_url(raw, default)` | 规范化 Chat Completions 兼容 Base URL，自动补协议并剥离 `/chat/completions` / `/images/generations` / `/responses` / `/models` 端点后缀 | `raw: str, default: str` | `str` |
| `openai_api_key_for_client(raw)` | 为 OpenAI SDK 返回可用 key；空值转为本地兼容服务占位 key | `raw: str` | `str` |

### 2.34 `src/utils/logging_config.py`

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `setup_logging(level, log_file)` | 配置日志系统 | `level: str, log_file: str \| None` | `None` |

### 2.35 `src/web/server.py` (核心 API 模块)

| 函数 | 描述 | 参数 | 返回值 |
|---|---|---|---|
| `start_web_server(host, port)` | 启动 Web UI 守护线程(幂等) | `host: str, port: int` | `threading.Thread \| None` |
| `update_status(**kwargs)` | 推送状态到所有 WebSocket 客户端 | 关键字参数 | `None` |
| `register_bot(thread, backend)` | 注册 bot 线程/后端 | `thread, backend` | `None` |
| `_stop_bot()` | 停止运行中的 bot | 无 | `bool` |
| `_start_bot_in_thread()` | 在新守护线程中启动 bot | 无 | `dict` ({"ok": True/False}) |
| `_register_backend(backend)` | 从 Bot.run() 注册后端 | `backend` | `None` |
| `_bot_exited()` | 通知 bot 线程已退出 | 无 | `None` |
| `signal_shutdown()` | 信号关闭所有组件 | 无 | `None` |
| `is_shutting_down()` | 检查关闭信号 | 无 | `bool` |
| `_handle_ws_upgrade(headers, conn)` | WebSocket 握手 | `headers, conn` | `bool` |
| `_send_ws_frame(sock, text)` | 发送 WebSocket 文本帧 | `sock, text: str` | `None` |
| `_read_ws_frame(sock)` | 读取 WebSocket 帧 | `sock` | `bytes \| None` |
| `_recv_exactly(sock, n)` | 精确接收 n 字节 | `sock, n: int` | `bytes \| None` |
| `_find_or_create_env()` | 查找或创建 .env 文件 | 无 | `Path` |
| `_ai_config_from_raw(raw)` | 从 `.env` 键值生成 UI AI 协议配置；legacy `deepseek` 映射为 Chat Completions | `raw: dict[str, str]` | `dict` |
| `_ai_updates_from_config(config)` | 从 UI payload 生成 AI 相关 `.env` 更新；缺失字段返回 `None` 以保留现值 | `config: dict` | `dict[str, str \| None]` |
| `_secret_update(new_value, old_value)` | 密钥字段安全更新；回传值含 `***`（掩码）时保留原密钥，避免掩码覆盖真实值 | `new_value, old_value: str` | `str \| None` |
| `_image_gen_config_from_raw(raw)` | 从 `.env` 键值生成 UI 生图配置；API Key 与 LLM 配置一致明文返回给本地 UI | `raw: dict[str, str]` | `dict` |
| `_image_gen_updates_from_config(config)` | 从 UI payload 生成生图相关 `.env` 更新；API Key 与 LLM 配置一致按前端值保存，base_url 按 OpenAI Images、Google Gemini Image 或 DashScope 协议归一化 | `config: dict` | `dict[str, str \| None]` |
| `_normalize_anthropic_base_url(raw)` | 规范化 Messages 协议 Base URL，剥离 `/v1/messages` / `/v1/models` | `raw: str` | `str` |
| `_extract_model_items(payload)` | 从常见模型列表响应中提取、去重并排序模型项 | `payload: dict \| list` | `list[dict[str, str]]` |
| `_request_json(url, headers)` | 发起 JSON GET 请求 | `url: str, headers: dict[str, str]` | `dict \| list` |
| `_fetch_ai_models(protocol, api_key, base_url)` | 按协议动态请求模型列表；Chat Completions 调 `/models`，Messages 调 `/v1/models` | `protocol: str, api_key: str, base_url: str` | `dict` |
| `_detect_wxid_and_db_path()` | 通过共享数据目录探测器检测微信 wxid 和 `session.db` 路径 | 无 | `tuple[str \| None, str \| None]` |
| `_set_env_key(env_path, key, value)` | 原子设置 .env 键值 | `env_path: Path, key: str, value: str` | `None` |
| `_read_env_raw(env_path)` | 从 `.env` 读取简单键值对，忽略注释和空行 | `env_path: Path \| None` | `dict[str, str]` |
| `_write_env_updates(env_path, updates)` | 批量原子写入 `.env` 并同步 `os.environ` | `env_path: Path, updates: dict[str, str \| None]` | `list[str]` |
| `_migrate_webot_data_dir(old_raw, new_raw)` | `WEBOT_DATA_DIR` 变更且 bot 已停止时，非覆盖复制旧目录中的 WeChatBot 自有数据文件/模型目录到新目录 | `old_raw: str, new_raw: str` | `list[str]` |
| `_remove_env_keys(env_path, keys)` | 从 `.env` 和 `os.environ` 移除指定键，用于清理旧引导草稿键 | `env_path: Path, keys: set[str]` | `None` |
| `_onboarding_db_path()` | 返回结构化应用状态使用的 SQLite 路径；legacy `DB_PATH=data/messages.db` 跟随 `WEBOT_DATA_DIR` | 无 | `Path` |
| `_read_onboarding_state()` | 读取 SQLite `onboarding_state` 单行草稿/进度 | 无 | `dict \| None` |
| `_save_onboarding_state(updates)` | 将引导草稿/步骤进度增量保存到 SQLite | `updates: dict` | `None` |
| `_reset_onboarding_database(db_path)` | 删除指定 SQLite 数据库中的引导草稿/进度行 | `db_path: Path` | `None` |
| `_reset_onboarding_state()` | 删除当前 SQLite 数据库中的引导草稿/进度行 | 无 | `None` |
| `_runtime_data_dir()` | 返回运行缓存/日志所在的 WeChatBot 自有数据目录 | 无 | `Path` |
| `_reset_runtime_database(db_path)` | 清空 `messages`、`user_last_message`、`trigger_log`、`group_memory`、`todos` 等运行表 | `db_path: Path` | `dict` |
| `_reset_runtime_files(data_dir)` | 删除生成的运行日志和缓存文件，如 `bot.log`、`bot_status.json`、群元数据、昵称缓存 | `data_dir: Path` | `list[str]` |
| `_reset_in_memory_onboarding()` | 重置内存中的引导草稿和密钥提取状态 | 无 | `None` |
| `_reset_app_config_to_first_run()` | 删除 `.env`、清除进程内 WeChatBot 配置键，并重置引导内存状态 | 无 | `dict` |
| `_reset_runtime_data()` | 停止状态下清空本地数据、删除 `.env`、清理 `onboarding_state` 并返回首次运行状态；运行中返回 `requires_stop` | 无 | `dict` |
| `_onboarding_draft_from_row(row)` | 从 SQLite 行生成引导页可回填草稿 | `row: dict` | `dict` |
| `_onboarding_draft_from_raw(raw)` | 从旧 `.env` 键值生成引导页可回填草稿(兼容迁移) | `raw: dict[str, str]` | `dict` |
| `_load_onboarding_progress()` | 读取引导草稿、步骤完成标记和整体完成状态，优先 SQLite，回退旧 `.env` | 无 | `tuple[dict, dict[str, bool], bool]` |
| `_hydrate_onboarding_from_store()` | 将持久化引导草稿合并回内存状态 | 无 | `tuple[dict, dict[str, bool], bool]` |
| `_detect_default_data_dir()` | 检测默认微信数据目录，包含微信 4.x 进程 `--wechat-files-path` | 无 | `str` |
| `_platform_dependency_report(...)` | 平台依赖诊断 | 可选参数 | `dict` |
| `_platform_wechat_report(...)` | 微信进程状态诊断 | 可选参数 | `dict` |
| `_macos_wechat_diagnostics(...)` | macOS 微信权限诊断 | 可选参数 | `dict` |
| `_read_recent_logs()` | 从配置后的日志路径读取最近 500 行日志 | 无 | `dict` |
| `_clear_log_file()` | 清空配置后的 `bot.log`，并截断活动中的日志 `FileHandler` | 无 | `dict` |
| `_run_step1_extraction()` | 后台执行密钥提取 | 无 | `None` |
| `_write_onboarding_to_env(env_path)` | 写入引导数据到 .env | `env_path` | `None` |

### 2.36 前端组件 (`ui/src/components/`)

| 文件 | 组件名 | 描述 |
|---|---|---|
| `Onboarding.jsx` | `Onboarding` | 4步引导流程主容器(侧边栏+步骤内容)，启动时从 `/api/onboarding/status` 回填草稿和步骤状态 |
| `OnboardingSteps.jsx` | `Step3AIConfig` | LLM模型配置步骤；按请求地址和 Key 动态获取模型列表 |
| `Dashboard.jsx` | `Dashboard` | 主仪表板(指标卡片+系统状态+控制栏+数据重置入口；重置成功后回到首次启动引导) |
| `Dashboard.jsx` | `MetricCard` | 指标卡片组件(图标/标签/数值/副标题/迷你SVG图表) |
| `Dashboard.jsx` | `LiveIndicator` | 实时状态指示灯(脉冲动画) |
| `Dashboard.jsx` | `KeyExtractionBanner` | 内联密钥提取横幅(单文件内组件) |
| `LogViewer.jsx` | `LogViewer` | 实时日志查看器(过滤/搜索/高亮/清空日志文件) |
| `ConfigPanel.jsx` | `AiSection` | 系统配置里的 LLM模型配置；支持模型获取和选择 |
| `ConfigPanel.jsx` | `VoiceSection` | 系统配置里的语音模型配置；本地/云端识别后端切换与模型下载 |
| `ConfigPanel.jsx` | `ImageGenSection` | 系统配置里的生图模型配置；总开关 + 协议/密钥/地址 + 生图模型/尺寸选择；OpenAI Images 通过 `/api/ai/models` 获取模型列表，Google/DashScope 使用内置模型选项 |
| `ConfigPanel.jsx` | `DataPathSection` | 系统配置里的 WeChatBot 数据目录与微信数据目录配置；WeChatBot 目录支持浏览/手输并与微信目录分离，微信目录支持浏览、检测和手输路径 |
| `FriendChatPanel.jsx` | `FriendChatPanel` | 左侧“好友私聊”页：好友勾选列表/搜索/全选/清空，保存走 `/api/friends/selection`；好友总开关关闭时显示提示 |
| `FeaturesPanel.jsx` | `ChatSection` | 功能开关 → AI 对话：群聊 AI 对话与好友私聊 AI 对话两个总开关 |
| `McpPanel.jsx` | `McpPanel` | 「MCP 服务」页：展示请求地址/API Key、启停开关、一键轮换密钥（自动生成随机新密钥并复制）、一键复制全部配置、Trae/Claude Desktop/Codex/SSE/curl 客户端配置、真实连接测试、工具清单 |
| `SharedComponents.jsx` | `Select` | 通用下拉选择；支持 `showValue=false` 避免协议显示重复 |

### 2.37 `src/imagegen/` (文生图)

| 函数 | 所在文件 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `ImageReply` | `reply.py` | 路由返回的图片回复数据类 | `image_path: str, caption: str = ""` | dataclass |
| `match_image_gen_keyword(text, keywords)` | `intent.py` | 返回命中的第一个生图关键词(长词优先)；未命中返回空串 | `text: str, keywords: list[str]` | `str` |
| `is_image_gen_intent(text, keywords)` | `intent.py` | 判断文本是否带生图意图 | `text: str, keywords: list[str]` | `bool` |
| `extract_image_prompt(text, keywords)` | `intent.py` | 提取生图提示词：移除首次命中的关键词，仅清理首尾标点空白；结果为空时回退完整文本 | `text: str, keywords: list[str]` | `str` |
| `normalize_image_gen_protocol(raw)` | `generator.py` | 规范化生图协议别名：`openai_images` / `google_gemini_image` / `dashscope_qwen`；New API/One API/GPT 等归入 OpenAI Images 兼容协议 | `raw: str` | `str` |
| `infer_image_gen_protocol(protocol, base_url, model)` | `generator.py` | 兼容旧配置：阿里云 `compatible-mode` + `qwen-image*` 自动推断为 `dashscope_qwen`，Google Gemini 地址 + gemini 模型自动推断为 `google_gemini_image` | `protocol, base_url, model: str` | `str` |
| `normalize_dashscope_base_url(raw)` | `generator.py` | 规范化 DashScope/Qwen-Image Base URL，剥离完整端点并将 `compatible-mode` 纠正为 `/api/v1` | `raw: str` | `str` |
| `normalize_google_gemini_base_url(raw)` | `generator.py` | 规范化 Google Gemini Image Base URL，剥离 `/interactions` 并自动补 `/v1beta` | `raw: str` | `str` |
| `google_response_format_from_size(size)` | `generator.py` | 将已有图片尺寸字段映射为 Google Gemini Interactions `response_format`，支持常见分辨率、比例与 1K/2K/4K | `size: str` | `dict` |
| `normalize_dashscope_size(size)` | `generator.py` | 将 UI 共用的 `1024x1024` 尺寸格式转换为 DashScope 接受的 `1024*1024` | `size: str` | `str` |
| `ImageGenerator.__init__(api_key, base_url, model, size, timeout, protocol="openai_images")` | `generator.py` | 初始化生图客户端；`model` 为空时抛 `ValueError`，按协议归一化 base_url | API配置 | `None` |
| `ImageGenerator.generate(prompt)` | `generator.py` | 按 `IMAGE_GEN_PROTOCOL` 调 OpenAI Images 兼容、Google Gemini Image 或 DashScope Qwen-Image 生成图片并落盘到 `<WEBOT_DATA_DIR>/images/` | `prompt: str` | `Path` |
| `ImageGenerator._generate_openai_images(prompt)` | `generator.py` | 调用 OpenAI 兼容 `/images/generations` | `prompt: str` | `Path` |
| `ImageGenerator._generate_dashscope_qwen(prompt)` | `generator.py` | 调用 DashScope `/services/aigc/multimodal-generation/generation` 同步文生图接口 | `prompt: str` | `Path` |
| `ImageGenerator._generate_google_gemini_image(prompt)` | `generator.py` | 调用 Google Gemini `/interactions` 图片生成接口，使用 `x-goog-api-key` 认证 | `prompt: str` | `Path` |
| `ImageGenerator._extract_image_bytes(body)` | `generator.py` | 从响应提取图片二进制；兼容 `b64_json` 内联、`url` 外链、DashScope 图片 URL 与 Google Gemini base64 图片块 | `body: dict` | `bytes` |
| `ImageGenerator._download(image_url)` | `generator.py` | 下载外链图片，限 20MB(静态) | `image_url: str` | `bytes` |
| `ImageGenerator._save_image(image_bytes)` | `generator.py` | 按魔数推断扩展名(png/jpg/webp)写入 images 目录(静态) | `image_bytes: bytes` | `Path` |
| `create_image_generator(config)` | `generator.py` | 工厂：未启用或缺 model/base_url 时返回 `None` | `config: BotConfig` | `ImageGenerator \| None` |

### 2.38 `src/mcp_server/` (MCP 服务)

把已采集的微信数据通过标准 MCP 协议暴露给 Codex、Trae 等外部智能体。只读本地数据，**不依赖机器人运行**，只要 Web 控制台进程在运行即可查询历史数据；消息类工具默认优先读微信本地完整历史，失败时回退 `messages.db`。

| 函数 | 所在文件 | 描述 | 参数 | 返回值 |
|---|---|---|---|---|
| `get_settings()` | `server.py` | 读取 `MCP_ENABLED`（默认开）、`MCP_API_KEY` 与数据范围 `MCP_GROUPS` / `MCP_FRIENDS` | 无 | `dict` |
| `update_settings(enabled, api_key, regenerate, groups, friends)` | `server.py` | 更新开关/密钥/数据范围并原子写入 `.env`；`regenerate=True` 立即生成一组新的随机密钥（旧密钥失效），同时清空失败鉴权计数 | 关键字参数 | `dict` |
| `ensure_api_key()` | `server.py` | 返回现有 Key，缺失时生成 `webot_...` 并写入 `.env` | 无 | `str` |
| `describe_server(base_url)` | `server.py` | 控制台连接信息（地址、密钥、工具清单、协议版本、数据范围与候选列表） | `base_url: str \| None` | `dict` |
| `verify_api_key(headers, query)` | `server.py` | 常量时间校验 Bearer / `X-API-Key` / `?key=` | 请求头与查询参数 | `bool` |
| `is_trusted_request(handler)` | `server.py` | 校验 Host 是否可信、Origin 是否为可信来源（防 DNS rebinding / 跨站读取） | `handler` | `bool` |
| `_allowed_hosts()` | `server.py` | 回环主机 + `MCP_ALLOWED_HOSTS` 追加的可信主机集合 | 无 | `set[str]` |
| `_check_access(handler, query, allow_query_key)` | `server.py` | 来源校验 → 开关 → 失败限流（20 次/60 秒）→ API Key；失败直接写 403/429/401 | 关键字参数 | `bool` |
| `handle_rpc(payload)` | `server.py` | JSON-RPC 2.0 分发（initialize / tools/list / tools/call / ping，支持批量，单批上限 20 条） | `payload: dict \| list` | `dict \| list \| None` |
| `handle_http(handler)` | `server.py` | 挂载 `/mcp`、`/mcp/sse`、`/mcp/messages` 到现有 HTTP 服务；命中返回 `True`；SSE 会话上限 20 | `handler` | `bool` |
| `get_scope()` | `data.py` | 读取数据范围原始配置（`*` 表示全部） | 无 | `dict` |
| `allowed_group_ids()` / `allowed_friend_ids()` | `data.py` | 解析 `MCP_GROUPS` / `MCP_FRIENDS`：`None`=全部，空集合=禁止 | 无 | `set[str] \| None` |
| `is_chat_allowed(chat_id)` | `data.py` | 判断群聊/好友是否在可访问范围内 | `chat_id: str` | `bool` |
| `_scope_sql(column)` | `data.py` | 生成范围过滤 SQL 片段与参数（群 `@chatroom` 与好友分别判断） | `column: str` | `tuple[str, list]` |
| `scope_options()` | `data.py` | 控制台数据范围候选：全部群聊（含成员数与 `active` 标记）与好友（含备注与 `active` 标记） | 无 | `dict` |
| `list_groups(args)` | `data.py` | 群列表 + 成员数/消息数/活跃人数/最近消息时间；可刷新缓存，返回 `refreshed` 标记 | `args: dict` | `dict` |
| `get_group(args)` | `data.py` | 单群基础信息与活跃概况 | `args: dict` | `dict` |
| `list_group_members(args)` | `data.py` | 群成员 + 群内显示名 + 发言统计（可识别活跃客户） | `args: dict` | `dict` |
| `list_friends(args)` | `data.py` | 好友列表 + 私聊消息数/最近互动时间 | `args: dict` | `dict` |
| `get_messages(args)` | `data.py` | 指定群/好友的消息，支持时间、发送者、关键词、分页；默认微信本地完整历史（`source=auto\|wechat_db\|messages_db`），单条内容超 2000 字截断并标记 `content_truncated` | `args: dict` | `dict` |
| `search_messages(args)` | `data.py` | 关键词搜索；指定 `chat` 时检索本地完整历史，否则跨会话搜已采集消息库（报价、联系方式等线索） | `args: dict` | `dict` |
| `get_group_activity(args)` | `data.py` | 群活跃度报表：消息量、活跃人数、新发言人数、Top 成员 | `args: dict` | `dict` |
| `get_member_activity(args)` | `data.py` | 成员发言排行与占比，默认基于本地完整历史 | `args: dict` | `dict` |
| `search_contacts(args)` | `data.py` | 按关键词查找群/好友/群成员并关联所在群 | `args: dict` | `dict` |
| `find_new_senders(args)` | `data.py` | 时间窗内首次发言的新联系人（群名、wxid、首条消息、发言数），支持 `min_messages` 过滤 | `args: dict` | `dict` |
| `get_contact_profile(args)` | `data.py` | 单联系人画像：好友信息、所在群、跨群/私聊发言统计、最近消息 | `args: dict` | `dict` |
| `get_data_overview(args)` | `data.py` | 数据总览（账号、群/好友/消息数、时间范围、近 7 天活跃、messages.db 更新时间/大小、本地历史数据源状态） | `args: dict` | `dict` |
| `parse_time(value, end_of_day)` | `data.py` | 解析 unix 秒、日期时间、`7d`/`24h`/`today` | 时间值 | `int \| None` |
| `_get_client()` | `history.py` | 懒加载微信本地库客户端；优先复用机器人已打开的实例，账号切换/失败时重建或退避 | 无 | `LocalWcdbClient` |
| `query_messages(chat_id, ...)` | `history.py` | 完整历史查询入口（时间/发送者/关键词/分页），不可用时抛 `HistoryUnavailable` | 关键字参数 | `tuple[list[dict], bool]` |
| `sender_stats(chat_id, ...)` | `history.py` | 按发送者聚合完整历史的发言数与首末时间 | 关键字参数 | `list[dict]` |
| `status()` | `history.py` | 不触发初始化，返回本地历史数据源是否启用/就绪/当前账号/错误 | 无 | `dict` |
| `reset()` | `history.py` | 清空缓存的本地库客户端（测试或账号切换后） | 无 | `None` |

安全默认值：`/api/mcp` 与所有 MCP 端点仅接受回环 Host，Origin 若存在也必须是回环/`MCP_ALLOWED_HOSTS` 中的域名；流式端点不接受 `?key=`（避免密钥落日志）；失败鉴权按 IP 限流；工具调用仅记录工具名与来源 IP。


---

## 3. 模块间关系图

### 3.1 高层架构

```
desktop.py  (桌面入口)
    │
    ├── src/web/server.py  (Web UI + API + WebSocket, 守护线程)
    │       ├── ui/dist/  (React 前端)
    │       └── src/mcp_server/  (MCP 服务：只读微信本地完整历史 / messages.db / 群/好友缓存，机器人未启动也可用)
    │             ├── server.py  (JSON-RPC / Streamable HTTP / SSE / API Key)
    │             ├── history.py (微信本地完整历史数据源：懒加载、账号切换检测、失败回退)
    │             └── data.py    (群聊、群成员、好友、消息、活跃统计工具)
    │
    └── src/bot.py  (Bot 主控)
            │
            ├── src/config.py  (配置加载 .env → BotConfig)
            ├── src/utils/ai_compat.py  (AI 协议别名 + Chat Completions URL 规范化)
            ├── src/db/  (数据库层)
            │     ├── schema.py  → initialize_db()
            │     └── store.py   → MessageStore
            ├── src/trigger/detector.py  (触发检测)
            ├── src/router.py  (消息路由)
            │       ├── src/proactive/  (主动发言)
            │       │     ├── gate.py       → ProactiveGate (4层门控)
            │       │     ├── modes.py      → ProactiveMode (5种模式)
            │       │     ├── rate_tracker.py → RateTracker (滑动窗口)
            │       │     └── sticky.py     → StickyMentionTracker (粘性@)
            │       ├── src/memory/consolidator.py  (记忆合并)
            │       ├── src/todo/  (待办)
            │       │     ├── store.py  → TodoStore (SQLite)
            │       │     └── handler.py → TodoHandler (命令解析)
            │       ├── src/nickname.py  (昵称服务)
            │       ├── src/admin.py  (管理员命令)
            │       ├── src/fun.py  (趣味功能:抽签)
            │       ├── src/welcome.py  (欢迎新成员)
            │       └── src/integrations/feishu/  (飞书导出)
            ├── src/summarize/  (AI 协议后端)
            │     ├── base.py           → AbstractSummarizer
            │     ├── claude_backend.py  → ClaudeSummarizer
            │     ├── openai_compatible_backend.py → OpenAICompatibleSummarizer
            │     ├── deepseek_backend.py → DeepSeekSummarizer
            │     ├── models.py         → SummaryResult (Pydantic)
            │     └── prompts.py        → Prompt 模板
            └── src/wechat/  (微信后端)
                  ├── base.py              → AbstractWeChatBackend
                  ├── wcdb_backend.py      → WcdbBackend (Windows 直读)
                  │     ├── local_wcdb_client.py → LocalWcdbClient (纯 Python SQLCipher 读取)
                  │     ├── wxdb_reader.py       → WeChatDB (内存取密钥 + 逐页解密, Apache-2.0 vendored)
                  │     └── window_controller.py → WeChatWindowController (键盘操控)
                  ├── extract_key.py       → 密钥提取 (内存扫描优先, wx_key.dll Hook 回退)
                  ├── keyboard.py          → 键盘模拟 (keybd_event)
                  ├── helpers.py           → 去重/类型映射/非文本消息摘要
                  ├── mac_ui_backend.py     → MacUIBackend (macOS 界面自动化)
                  ├── mac_hybrid_backend.py → MacHybridBackend (macOS WCDB + 自动化)
                  └── mac_weflow_client.py  → MacWeFlowClient (macOS WCDB 直读)
```

### 3.2 调用关系图

#### src/bot.py → 调用链

```
Bot.run()
  ├── setup_logging()                    [src/utils/logging_config.py]
  ├── initialize_db()                    [src/db/schema.py]
  ├── MessageStore()                     [src/db/store.py]
  ├── TriggerDetector()                  [src/trigger/detector.py]
  ├── create_summarizer()                [src/summarize/__init__.py]
  │     ├── normalize_ai_backend()        [src/utils/ai_compat.py]
  │     ├── ClaudeSummarizer()            [src/summarize/claude_backend.py]
  │     ├── OpenAICompatibleSummarizer()  [src/summarize/openai_compatible_backend.py]
  │     └── DeepSeekSummarizer()          [src/summarize/deepseek_backend.py]
  ├── NicknameService()                  [src/nickname.py]
  ├── AdminCommandHandler()              [src/admin.py]
  ├── FeishuExportService()              [src/integrations/feishu/exporter.py]
  ├── MessageRouter()                    [src/router.py]
  │     ├── ProactiveGate()              [src/proactive/gate.py]
  │     ├── StickyMentionTracker()       [src/proactive/sticky.py]
  │     ├── MemoryConsolidator()         [src/memory/consolidator.py]
  │     ├── TodoStore()                  [src/todo/store.py]
  │     ├── TodoHandler()                [src/todo/handler.py]
  │     └── create_image_generator()     [src/imagegen/generator.py]
  ├── HealthMonitor()                    [src/bot.py]
  └── WcdbBackend / MacUIBackend / MacHybridBackend  [src/wechat/]
```

#### src/web/server.py → 调用链

```
_API 请求 → _UIHandler._handle_request()
  ├── /api/start          → _start_bot_in_thread() → Bot.run()
  ├── /api/stop           → _stop_bot()
  ├── /api/runtime/reset  → _reset_runtime_data() → 清运行表/缓存文件、删除 .env、重置 onboarding 并刷新状态
  ├── /api/load-config    → _find_or_create_env() → 读取 .env
  ├── /api/config         → 写入 .env；WEBOT_DATA_DIR 变更且 bot 停止时复制旧 WeChatBot 数据
  ├── /api/ai/models      → _fetch_ai_models() → _request_json()
  ├── /api/nicknames      → NicknameService
  ├── /api/nicknames/groups → <WEBOT_DATA_DIR>/group_names.json / messages.db
  ├── /api/friends        → <WEBOT_DATA_DIR>/friend_names.json (配置面板好友勾选列表)
  ├── /api/welcome/templates → WelcomeManager
  ├── /api/sandbox/test   → create_summarizer() → .chat()
  ├── /api/todos          → TodoStore
  ├── /api/todos/action   → TodoStore
  ├── /api/todos/counts   → TodoStore
  ├── /api/voice/model-status → 检查 HuggingFace 缓存
  ├── /api/voice/download-model → snapshot_download()
  ├── /api/lots           → load_lots_config() / save_lots_config()
  ├── /api/onboarding/*   → 引导流程状态管理 + SQLite 草稿/进度持久化，最终运行配置写入 .env
  ├── /api/logs           → _read_recent_logs()
  ├── /api/logs/clear     → _clear_log_file()
  ├── /api/status         → _status.snapshot()
  ├── /api/browse         → _list_dir_entries()
  ├── /api/wechat-data-dir/detect → data_dir.list_accounts_in_data_dir()
  └── /ws                 → WebSocket 升级 → _status 广播
```

#### src/wechat/* → 微信后端的层次结构

```
AbstractWeChatBackend (base.py)
    │
    ├── WcdbBackend (wcdb_backend.py) — Windows 原生
    │     ├── LocalWcdbClient (local_wcdb_client.py) — 纯 Python SQLCipher 读取
    │     │     └── WeChatDB (wxdb_reader.py) — 内存扫描取密钥 + 逐页 AES-CBC 解密
    │     ├── data_dir.py — 微信数据目录自动探测(WECHAT_DATA_DIR / 进程参数 / 默认目录)
    │     ├── WeChatWindowController (window_controller.py) — 键盘操控发送
    │     │     └── keyboard.py — keybd_event 底层模拟
    │     └── helpers.py — DedupSet / 消息类型映射 / 图片表情文件摘要
    │
    ├── MacUIBackend (mac_ui_backend.py) — macOS 界面自动化
    │     └── MacUIAutomation — AppleScript + CoreGraphics + Vision OCR
    │
    └── MacHybridBackend (mac_hybrid_backend.py) — macOS 混合
          ├── MacWeFlowClient (mac_weflow_client.py) — WCDB 直读
          │     └── _WCDBSQLiteReader — ctypes 加载 libWCDB.dylib
          └── MacUIAutomation — 复用 UI 自动化(发送)
```

#### src/summarize/* → AI 协议后端的层次结构

```
AbstractSummarizer (base.py)
    │  ├── chat()           — @bot AI 对话
    │  ├── proactive_chat() — 主动发言
    │  ├── summarize()      — 结构化总结
    │  ├── consolidate_memory() — 记忆合并(抽象)
    │  └── _retry_with_backoff() — 指数退避重试
    │
    ├── ClaudeSummarizer (claude_backend.py)
    │     ├── _call_chat_api()           — client.messages.create()
    │     ├── _summarize_direct()        — client.messages.parse() + Pydantic
    │     ├── _summarize_chunk()         — client.messages.create() + selected model
    │     ├── _merge_chunk_summaries()   — client.messages.parse() + Pydantic
    │     └── consolidate_memory()       — client.messages.create() + selected model
    │
    ├── OpenAICompatibleSummarizer (openai_compatible_backend.py)
    │     ├── _call_chat_api()           — client.chat.completions.create()
    │     ├── _summarize_direct()        — tool calling → fallback plain text
    │     ├── _summarize_chunk()         — client.chat.completions.create()
    │     ├── _merge_chunk_summaries()   — tool calling → fallback plain text
    │     └── consolidate_memory()       — client.chat.completions.create()
    │
    └── DeepSeekSummarizer (deepseek_backend.py)
          └── OpenAICompatibleSummarizer preset + thinking disabled
```

### 3.3 数据流: 消息从微信到AI总结到前端展示的完整链路

```
1. 微信客户端写入加密 WCDB 数据库
         │
2. WcdbBackend._poll_cycle() 每秒轮询
         │
3. LocalWcdbClient.get_messages() — 从微信进程内存取密钥，逐页解密 SQLCipher 数据库后读取
         │
4. WcdbBackend._standardize() — 标准化为统一消息格式
         │  (解析 sender, content, timestamp, msg_type, @mention 等)
         │
5. WcdbBackend._handle_message() — 提交到 ThreadPoolExecutor
         │
6. MessageRouter.handle(msg)
         │
         ├─→ [@mention 路径]
         │      │
         │      ├─ trigger check → TriggerDetector.is_trigger()
         │      ├─ summary → _handle_summary()
         │      │     ├─ MessageStore.get_user_previous_timestamp()
         │      │     ├─ MessageStore.get_messages_since()
         │      │     ├─ NicknameService.resolve_wxids()
         │      │     └─ AbstractSummarizer.summarize()
         │      │           ├─ _split_into_chunks()
         │      │           ├─ _summarize_direct() 或 _summarize_map_reduce()
         │      │           └─ format_summary_for_reply()
         │      │
         │      ├─ chat → _handle_chat()
         │      │     ├─ MessageStore.get_messages_since() (上下文)
         │      │     └─ AbstractSummarizer.chat()
         │      │
         │      ├─ admin command → AdminCommandHandler.handle()
         │      ├─ todo command → TodoHandler.handle()
         │      ├─ feishu export → FeishuExportService.export_recent_chat()
         │      └─ fun (抽签) → draw_lots()
         │
         └─→ [非 @ 路径]
                │
                ├─ 关键词触发 → TriggerDetector.is_trigger(is_at_mentioned=False)
                │     └─ 命中 (如裸发"总结一下"，≤300s 新消息) → _handle_summary()
                │
                └─ [未命中] ProactiveGate.should_speak() — 4层门控
                      ├─ RateTracker.record() + rate()
                      ├─ lookup_mode() — 确定模式
                      ├─ 评估间隔检查 + 指数退避
                      └─ 概率骰子
                           └─ _handle_proactive_chat()
                                 └─ AbstractSummarizer.proactive_chat()

7. 生成回复文本
         │
8. WcdbBackend._send_and_confirm()
         │
9. WeChatWindowController.send_to_chat()
         │  (find_hwnd → activate → navigate_to_chat → send_message)
         │  (Ctrl+F → 粘贴群名 → Enter → Ctrl+V 粘贴消息 → Enter)
         │
10. MessageStore.insert_message() — 持久化到 SQLite
         │
11. _status.update() → WebSocket 广播到前端
         │
12. Dashboard.jsx 实时更新指标卡片
```

---

## 4. 功能模块展开

### 功能A: 消息获取 (WCDB直读)

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `wcdb_backend.py` | `src/wechat/wcdb_backend.py` | 后端主控, 消息轮询与标准化 |
| `local_wcdb_client.py` | `src/wechat/local_wcdb_client.py` | WCDB 后端适配器，纯 Python 解密读取 |
| `wxdb_reader.py` | `src/wechat/wxdb_reader.py` | 微信 4.x SQLCipher 解密/查询实现 (vendored, Apache-2.0) |
| `data_dir.py` | `src/wechat/data_dir.py` | 微信数据目录自动检测，支持自定义路径、微信 4.x 进程参数和常见目录 |
| `extract_key.py` | `src/wechat/extract_key.py` | 密钥提取 (内存扫描优先, wx_key.dll Hook 回退) |
| `base.py` | `src/wechat/base.py` | 抽象基类 (接口定义) |
| `helpers.py` | `src/wechat/helpers.py` | 去重集合、消息类型映射、图片/表情/文件占位摘要 |

#### 调用链和关键函数

```
WcdbBackend.start(callback)
  │
  ├── LocalWcdbClient.init()
  │     ├── data_dir.find_wxid_and_dbpath() → 检测 wxid_* 数据根目录
  │     └── WeChatDB(...) → 内存取密钥 + 逐页解密缓存
  │
  ├── LocalWcdbClient.open()
  │     ├── WeChatDB → 扫描 Weixin.exe 的 Config.Cipher 对象提取密钥
  │     ├── 按页 AES-256-CBC 解密到临时缓存 → sqlite3 查询
  │     └── 会话库无密钥时抛出明确错误（提示保持微信登录）
  │
  ├── _resolve_groups()
  │     ├── get_sessions() → 从最近会话收集 @chatroom
  │     ├── get_contacts() → session 无群/缺群时从联系人收集 @chatroom
  │     ├── _load_cached_group_names() → 读取 <WEBOT_DATA_DIR>/group_names.json 兜底
  │     ├── _add_configured_chatroom_ids() → 接受 WECHAT_GROUPS 中的直接 @chatroom ID
  │     ├── get_group_members() → 解析群成员
  │     ├── get_display_names() → 批量解析昵称
  │     └── _save_group_names() → 持久化到 <WEBOT_DATA_DIR>/group_names.json
  │
  ├── _resolve_friends()
  │     ├── sessions/contacts → 收集非 @chatroom / 非 gh_ / 非系统账号的个人好友
  │     ├── _save_friend_names() → 持久化全部好友到 <WEBOT_DATA_DIR>/friend_names.json
  │     └── 仅将 WECHAT_FRIENDS 勾选的好友解析进 _friend_ids (未勾选不轮询)
  │
  └── while self._running:           # 主轮询循环
        ├── _poll_cycle(callback)
        │     ├── for each group:  _poll_group(group_name, talker, callback)
        │     └── for each friend: _poll_group(friend_name, talker, callback, is_group=False)
        │             ├── get_messages(talker, limit=50)
        │             ├── _raw_message_key() → 非零 ID/内容组合轻量去重，旧消息不进入 standardize
        │             ├── _standardize() → 统一消息格式
        │             │     └── helpers.format_nontext_content()
        │             │           → 图片/表情/文件 XML 提炼为可总结文本
        │             ├── 去重 (_known_ids) → 跳过旧消息
        │             ├── 自发自排除 (_recent_sends 同群内容匹配) → 跳过机器人自己的回复
        │             ├── 新消息: 记录 "New message" / "Join event detected" 日志
        │             └── _handle_message() → 线程池提交
        │
        └── time.sleep(poll_sec)
```

#### 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `poll_sec` | `1.0` | 轮询间隔(秒), 对应 `POLL_INTERVAL_SEC` |
| `limit` | `50` | 每次查询最多返回消息数 |
| `max_workers` | `4` | 回调线程池大小 |
| `MAX_CONSECUTIVE_ERRORS` | `5` | 连续错误触发重初始化 |
| `MAX_DEDUP_SIZE` | `5000` | 去重集合上限 |

#### 消息标准化输出格式

```python
{
    "message_id": str,      # MD5 哈希的稳定 ID
    "chat_id": str,         # @chatroom talker ID
    "group_name": str,      # 群显示名
    "sender_id": str,       # wxid_xxx
    "sender_name": str,     # 解析后的显示名
    "content": str,         # 消息文本 ("[图片]", "[语音]" 等占位符)
    "msg_type": int,        # 1=text, 3=image, 34=voice, 47=emoji, 49=link
    "timestamp": int,       # Unix 秒
    "is_at_mentioned": bool, # 是否 @机器人 (精确+模糊匹配 BOT_DISPLAY_NAME)
    "bot_mention_text": str, # 命中的 @ 文本 (如 "@俞")，供 router 剥离；未命中为 ""
    "is_group": bool,       # 是否群聊(好友私聊为 False)
    "is_system_join": bool, # 是否"xxx 加入了群聊"事件
    "new_member_id": str,   # 新成员 wxid
}
```

---

### 功能B: AI总结/聊天

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `base.py` | `src/summarize/base.py` | 抽象基类 (chat, proactive_chat, summarize, format) |
| `claude_backend.py` | `src/summarize/claude_backend.py` | Claude API (Pydantic parse) |
| `openai_compatible_backend.py` | `src/summarize/openai_compatible_backend.py` | 通用 OpenAI 兼容 API (Chat Completions + tool fallback) |
| `ai_compat.py` | `src/utils/ai_compat.py` | OpenAI 兼容别名、Base URL 规范化、空 Key 兼容 |
| `deepseek_backend.py` | `src/summarize/deepseek_backend.py` | DeepSeek 预设 (继承通用后端) |
| `prompts.py` | `src/summarize/prompts.py` | Prompt 模板 (XML格式, Map-Reduce, 记忆合并) |
| `models.py` | `src/summarize/models.py` | Pydantic 数据模型 |
| `__init__.py` | `src/summarize/__init__.py` | 工厂函数 create_summarizer() |
| `router.py` | `src/router.py` | 消息路由 (调用摘要/对话) |

#### 调用链和关键函数

```
MessageRouter.handle(msg)
  │
  ├── 剥离 @前缀: 先用 msg["bot_mention_text"] (后端模糊命中的 @ 文本)，
  │     再按配置的 BOT_DISPLAY_NAME 剥离，得到 clean_content
  │
  ├── [摘要请求] → _handle_summary(msg)
  │     ├── MessageStore.get_user_previous_timestamp() — 确定摘要起点
  │     ├── MessageStore.get_messages_since() — 获取消息窗口
  │     ├── 排除请求者自己发送的消息
  │     ├── NicknameService.resolve_wxids() — 替换文本中的 wxid
  │     └── AbstractSummarizer.summarize(messages, requester_name)
  │           │
  │           ├── _estimate_tokens() — 估算 token 数
  │           ├── 策略选择:
  │           │     ├── ≤budget → _summarize_direct() (单次调用)
  │           │     ├── ≤5*chunk_size → _summarize_map_reduce() (分块+合并)
  │           │     └── 超大量 → _multi_level_map_reduce() (多级合并)
  │           │
  │           └── format_summary_for_reply() — 格式化为微信回复
  │
  ├── [好友私聊] → _handle_friend_chat(msg)   # 仅后端轮询的已勾选好友；FRIEND_CHAT_ENABLED=false 时直接返回 None
  │     └── 仅 msg_type 1/34(有转写) 且未过期 → _handle_chat(msg, content, is_group=False)
  │
  └── [AI 对话] → _handle_chat(msg, clean_content)   # GROUP_CHAT_ENABLED=false 时不进入此分支，主动发言也不执行
        ├── MessageStore.get_messages_since() — 获取最近 600s 上下文
        ├── NicknameService.resolve_name() — 解析发送者昵称
        └── AbstractSummarizer.chat(
              message=clean_content,
              context_messages=context,
              requester_name=display_name,
              bot_name=config.bot_display_name,
              group_name=group_name,
              group_memory=memory,
            )
```

#### 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `token_budget` (Claude) | `150000` | Claude 上下文窗口安全预算 |
| `token_budget` (OpenAI-compatible) | `100000` | 通用兼容后端保守上下文预算 |
| `token_budget` (DeepSeek) | `900000` | DeepSeek 上下文窗口安全预算 |
| `chunk_size` | `400` | 每个分块的消息数 |
| `merge_batch_size` | `5` | 合并批次大小 |
| `max_retries` | `3` | API 调用最大重试次数 |
| `max_messages_for_summary` | `5000` | 摘要最大消息数 |
| `fallback_window_hours` | `8` | 摘要回退时间窗口(小时) |
| `CHAT_CONTEXT_WINDOW_SEC` | `600` | AI 对话上下文时间窗口(秒) |
| `MAX_CONTENT_LENGTH` | `997` | 单条消息最大字符数 |
| `AT_MENTION_MAX_AGE_SEC` | `300` | @mention 最大有效年龄(秒) |

#### Messages 协议后端特有

- 使用 `client.messages.parse()` 进行原生 Pydantic 结构化输出
- 聊天、直接总结、分块提取、合并和记忆整理均使用 UI 选择的 `SUMMARIZE_MODEL`
- 重试异常: `RateLimitError`, `APIConnectionError`, `InternalServerError`, `OverloadedError`

#### Chat Completions 兼容后端特有

- 通过 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 接入任意兼容 Chat Completions 的服务
- `AI_BACKEND` 支持 `chat-completions`, `openai`, `new-api`, `one-api`, `litellm`, `openrouter` 等别名，统一归一化为 `openai_compatible`
- `OPENAI_BASE_URL` 会自动补全协议，并将误填的完整 `/chat/completions`、`/responses` 或 `/models` endpoint 修正为 SDK base URL
- `OPENAI_API_KEY` 允许为空；`openai_api_key_for_client()` 会用本地兼容服务占位 key 调用 OpenAI SDK
- `OPENAI_MODEL` 不提供代码默认值，需通过模型列表接口获取后选择或手动填写
- 优先使用 OpenAI-compatible tool calling (`STORE_SUMMARY_TOOL`) 进行结构化输出
- 当服务商拒绝 tool calling 时自动重试普通 Chat Completions，并把 tool call / JSON / fenced JSON / 文本包装为 `SummaryResult`
- 重试异常: `RateLimitError`, `APIConnectionError`, `APIStatusError`

#### DeepSeek 预设特有

- `DeepSeekSummarizer` 继承 `OpenAICompatibleSummarizer`
- 默认 `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL` 不提供代码默认值，legacy preset 也需显式填写
- **禁用 thinking 模式**: `extra_body={"thinking": {"type": "disabled"}}`

---

### 功能C: 主动发言

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `gate.py` | `src/proactive/gate.py` | 4层门控: 开关→速率→间隔→概率 |
| `modes.py` | `src/proactive/modes.py` | 5种模式定义 (SLEEP/QUIET/CASUAL/LIVELY/BURST) |
| `rate_tracker.py` | `src/proactive/rate_tracker.py` | 滑动窗口速率追踪 |
| `sticky.py` | `src/proactive/sticky.py` | 粘性 @mention 追踪 |

#### 调用链

```
MessageRouter.handle(msg) → [无 @mention]
  │
  ├── TriggerDetector.is_trigger(content, is_at_mentioned=False, sender_name)
  │     └── 关键词命中 (如裸发"总结一下") → _handle_summary(msg)
  │
  ├── [关键词未命中] ProactiveGate.should_speak(msg)
  │     │
  │     ├── Gate 1: proactive_enabled? → 主开关
  │     ├── Gate 2: rate = RateTracker.rate(chat_id)
  │     │           lookup_mode(rate) → 5种模式之一
  │     │           mode.name == "SLEEP"? → 跳过
  │     ├── Gate 3: 评估间隔检查
  │     │           elapsed >= mode.eval_interval_sec * backoff?
  │     │           连续静默 → 指数退避 (2^consecutive, 上限16x)
  │     └── Gate 4: random.random() <= mode.reply_probability?
  │
  └── _handle_proactive_chat(msg, mode)
        │
        ├── RateTracker.rate() → MessageStore.get_messages_since()
        ├── AbstractSummarizer.proactive_chat(mode, context, ...)
        │     ├── PROACTIVE_SYSTEM_PROMPT.format(...)
        │     └── _call_chat_api(system_prompt, messages)
        │
        └── AI 返回空 → record_silence() → 指数退避
            AI 返回内容 → record_speech() → 重置静默计数
```

#### 5种主动发言模式

| 模式 | 标签 | 评估间隔 | 回复概率 | 最大字符 | 上下文消息数 | 速率阈值(默认) |
|---|---|---|---|---|---|---|
| SLEEP | 沉睡 | 9999s | 0.0 | 0 | 0 | 0.0 (始终兜底) |
| QUIET | 冷清 | 300s | 0.10 | 30 | 30 | 1.5 msgs/min |
| CASUAL | 闲聊 | 120s | 0.25 | 50 | 50 | 4.0 msgs/min |
| LIVELY | 热闹 | 60s | 0.50 | 35 | 60 | 6.5 msgs/min |
| BURST | 炸了 | 30s | 0.70 | 20 | 80 | 8.5 msgs/min |

#### 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `proactive_enabled` | `False` | 主动发言总开关 |
| `proactive_rate_window_sec` | `120` | 速率计算窗口(秒) |
| `proactive_rate_quiet` | `1.5` | QUIET 模式最低速率 |
| `proactive_rate_casual` | `4.0` | CASUAL 模式最低速率 |
| `proactive_rate_lively` | `6.5` | LIVELY 模式最低速率 |
| `proactive_rate_burst` | `8.5` | BURST 模式最低速率 |
| `exponential_backoff_max` | `16x` | 静默指数退避上限 |

---

### 功能D: Web UI 和 API

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `server.py` | `src/web/server.py` | HTTP + WebSocket 服务器 |
| `desktop.py` | `desktop.py` | Windows 桌面入口 (WebView2) |
| `desktop_mac.py` | `desktop_mac.py` | macOS 桌面入口 (WebView Cocoa) |
| React 前端 | `ui/src/` | SPA 前端 (Onboarding + Dashboard + LogViewer) |

#### API 端点清单

| 方法 | 路径 | 功能 | 认证 |
|---|---|---|---|
| `GET` | `/` | SPA 入口 (index.html) | 无 |
| `GET` | `/api/status` | 获取 bot 运行状态 | 无 |
| `POST` | `/api/start` | 启动 bot | 无 |
| `POST` | `/api/stop` | 停止 bot | 无 |
| `POST` | `/api/runtime/reset` | 停止状态下清空本地运行数据、删除 `.env`、清除密钥/AI/功能配置和 `onboarding_state`，使前端回到首次启动流程 | 无 |
| `GET` | `/api/load-config` | 加载当前配置 (保留可编辑密钥原值用于配置回填) | 无 |
| `POST` | `/api/config` | 保存配置到 .env；持久化 `WEBOT_DATA_DIR`，停止状态下复制旧 WeChatBot 数据到新目录 | 无 |
| `GET` | `/api/config/export` | 导出配置为 JSON 文件 | 无 |
| `POST` | `/api/config/import` | 导入 JSON 配置文件；支持导入 `WEBOT_DATA_DIR` 并迁移旧 WeChatBot 数据 | 无 |
| `POST` | `/api/ai/models` | 根据 `ai_backend`、请求地址和 Key 动态获取模型列表 | 无 |
| `GET` | `/api/nicknames?chat_id=xxx` | 获取群成员昵称列表 | 无 |
| `POST` | `/api/nicknames` | 保存/删除昵称映射 | 无 |
| `GET` | `/api/nicknames/groups` | 获取群组列表 | 无 |
| `GET` | `/api/friends` | 获取已发现的好友列表 (`friend_names.json`)，供配置面板勾选 | 无 |
| `GET` | `/api/mcp` | 获取 MCP 服务连接信息（请求地址、SSE 地址、API Key、工具清单、数据范围与候选项）；Key 缺失时自动生成；仅接受本机 Host/Origin | 无 |
| `POST` | `/api/mcp` | 更新 MCP 开关 / API Key / 轮换密钥 / 数据范围，写入 `.env`；仅接受本机 Host/Origin | `{"enabled": bool, "api_key": "...", "regenerate": bool, "groups": "id1,id2｜*｜none", "friends": "wxid1,wxid2｜*｜none"}` |
| `POST` | `/mcp` | MCP Streamable HTTP 端点（JSON-RPC 2.0）；不接受 `?key=` | `Authorization: Bearer <MCP_API_KEY>` 或 `X-API-Key` |
| `GET` | `/mcp/sse` | 兼容旧版 MCP HTTP+SSE 传输，返回 endpoint 事件与消息流 | 同上（也支持 `?key=`） |
| `POST` | `/mcp/messages?session_id=` | 旧版 SSE 会话的 JSON-RPC 提交端点 | 同上 |
| `POST` | `/api/friends/selection` | 仅保存 `WECHAT_FRIENDS`（好友私聊勾选），不覆盖其它配置 | `{"friends": "URL编码逗号列表 / \\"*\\" / \\"\\""}` |
| `GET` | `/api/welcome/templates` | 获取欢迎模板配置 | 无 |
| `POST` | `/api/welcome/templates` | 保存欢迎模板配置 | 无 |
| `GET` | `/api/todos?status=active&chat_id=xxx` | 获取待办列表 | 无 |
| `GET` | `/api/todos/counts?chat_id=xxx` | 获取各状态待办计数 | 无 |
| `POST` | `/api/todos/action` | 执行待办操作 (complete/delete/restore/clear) | 无 |
| `GET` | `/api/logs` | 获取最近 500 行日志 | 无 |
| `POST` | `/api/logs/clear` | 清空配置后的 `bot.log` 并重置运行日志页展示 | 无 |
| `POST` | `/api/sandbox/test` | AI 沙盒测试 (不发送) | 无 |
| `GET` | `/api/lots` | 获取抽签配置 | 无 |
| `POST` | `/api/lots` | 保存抽签配置 | 无 |
| `GET` | `/api/browse?path=` | 浏览文件系统目录 | 无 |
| `POST` | `/api/wechat-data-dir/detect` | 检测自定义微信数据目录 | 无 |
| `GET` | `/api/onboarding/status` | 引导流程状态 + SQLite 草稿回填数据(兼容旧 `.env` 草稿读取) | 无 |
| `GET` | `/api/onboarding/diagnose` | 系统环境诊断 | 无 |
| `POST` | `/api/onboarding/step1` | 启动密钥提取(异步) | 无 |
| `POST` | `/api/wechat/extract-key` | 独立获取微信数据库密钥（不修改 onboarding 状态，机器人未启动也可用） | 无 |
| `POST` | `/api/wechat/sync` | 不启动机器人，打开微信数据库刷新群聊/群成员/好友缓存，返回同步数量；缺密钥时返回 `need_key` | 无 |
| `GET` | `/api/onboarding/step1-status` | 轮询密钥提取状态 | 无 |
| `POST` | `/api/onboarding/step1-manual` | 保存手动输入的 WCDB 密钥、wxid 和数据库路径到 SQLite，镜像 `WCDB_KEY` 到 `.env` | 无 |
| `POST` | `/api/onboarding/step2` | 保存微信配置到 SQLite，并将运行时微信配置镜像到 `.env` | 无 |
| `POST` | `/api/onboarding/step3` | 保存 AI 配置到 SQLite，并将运行时 AI 配置镜像到 `.env` | 无 |
| `POST` | `/api/onboarding/step4` | 保存功能设置、标记完成引导，并写入最终 `.env` 运行配置 | 无 |
| `POST` | `/api/onboarding/reset` | 删除 SQLite 引导状态并清理兼容 `.env` 键 | 无 |
| `GET` | `/api/voice/model-status?model=small` | 语音模型下载状态 | 无 |
| `POST` | `/api/voice/download-model` | 触发语音模型下载 | 无 |
| `GET` | `/api/macos/diagnose` | macOS 微信权限诊断 | 无 |
| `GET` | `/ws` | WebSocket 升级 (状态推送) | 无 |

#### 引导状态数据库表

引导流程的步骤完成度、WCDB 草稿信息、微信配置草稿、AI 配置草稿和功能开关草稿存入应用 SQLite 数据库的单行表；`.env` 只保留启动兼容需要的最终运行配置，例如 `ONBOARDING_DONE` 和 `WCDB_KEY`。

```sql
CREATE TABLE onboarding_state (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    step1_done              INTEGER NOT NULL DEFAULT 0,
    step2_done              INTEGER NOT NULL DEFAULT 0,
    step3_done              INTEGER NOT NULL DEFAULT 0,
    step4_done              INTEGER NOT NULL DEFAULT 0,
    onboarding_done         INTEGER NOT NULL DEFAULT 0,
    wcdb_key                TEXT    NOT NULL DEFAULT '',
    wxid                    TEXT    NOT NULL DEFAULT '',
    db_path                 TEXT    NOT NULL DEFAULT '',
    bot_display_name        TEXT    NOT NULL DEFAULT '',
    wechat_groups           TEXT    NOT NULL DEFAULT '*',
    wechat_backend          TEXT    NOT NULL DEFAULT 'wcdb',
    ai_backend              TEXT    NOT NULL DEFAULT 'openai_compatible',
    deepseek_api_key        TEXT    NOT NULL DEFAULT '',
    deepseek_base_url       TEXT    NOT NULL DEFAULT 'https://api.deepseek.com',
    deepseek_model          TEXT    NOT NULL DEFAULT '',
    openai_api_key          TEXT    NOT NULL DEFAULT '',
    openai_base_url         TEXT    NOT NULL DEFAULT 'https://api.openai.com/v1',
    openai_model            TEXT    NOT NULL DEFAULT '',
    anthropic_api_key       TEXT    NOT NULL DEFAULT '',
    anthropic_base_url      TEXT    NOT NULL DEFAULT 'https://api.anthropic.com',
    summarize_model         TEXT    NOT NULL DEFAULT '',
    fun_enabled             INTEGER NOT NULL DEFAULT 1,
    proactive_enabled       INTEGER NOT NULL DEFAULT 0,
    sticky_mention_enabled  INTEGER NOT NULL DEFAULT 1,
    created_at              INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at              INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
```

#### WebSocket 消息类型

WebSocket 仅用于服务器→客户端单向推送状态快照:

```json
{
    "running": false,
    "uptime_sec": 0,
    "messages_processed": 0,
    "wechat_backend": "wcdb",
    "ai_backend": "deepseek",
    "db_ok": true,
    "last_api_call_sec_ago": -1,
    "last_api_call_time": 0.0,
    "timestamp": "2026-06-11T12:00:00",
    "error": ""
}
```

---

### 功能E: 微信窗口操控

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `window_controller.py` | `src/wechat/window_controller.py` | 窗口发现/验证/激活/导航/发送 |
| `keyboard.py` | `src/wechat/keyboard.py` | 键盘底层模拟 (keybd_event) |

#### 调用链

```
WeChatWindowController.send_to_chat(group_name, text)  ← 主入口
  │
  ├── find_hwnd(force=False)
  │     ├── EnumWindows → _score_window() 打分所有窗口
  │     ├── 验证: 进程名 ∈ {wechat.exe, weixin.exe}
  │     ├── 评分: title="微信" (+50), Qt class (+30), visible (+20), size (+10)
  │     └── 缓存 30 秒
  │
  ├── activate(hwnd) — 4层激活策略
  │     ├── Layer 1: _prime_foreground_authority() — Alt 按键获取前台权限
  │     │           + AllowSetForegroundWindow(-1) + SetForegroundWindow
  │     ├── Layer 2: _force_foreground() — AttachThreadInput 绕过
  │     ├── Layer 3: _alt_tab_to_window() — Alt+Esc 循环切换
  │     └── Layer 4: (失败)
  │
  ├── navigate_to_chat(hwnd, group_name)
  │     ├── Phase 0: _goto_contacts_tab() — Ctrl+2 到通讯录标签
  │     ├── Phase 1: Ctrl+F → 聚焦搜索框
  │     ├── Phase 2: Ctrl+A → set_clipboard → Ctrl+V → 粘贴群名
  │     ├── Phase 3: Enter → 选择第一个搜索结果
  │     └── _verify_chat_title() — UIA 或窗口标题验证
  │
  └── send_message(hwnd, text)
        ├── _set_clipboard(text) — 写入剪贴板
        ├── Ctrl+V — 粘贴
        └── Enter — 发送
```

#### 关键常量

| 常量 | 值 | 说明 |
|---|---|---|
| `WECHAT_PROCESS_NAMES` | `{"wechat.exe", "weixin.exe"}` | 有效微信进程名 |
| `MIN_WINDOW_WIDTH/HEIGHT` | `200` | 最小有效窗口尺寸 |
| `SEARCH_FOCUS_DELAY` | `0.15s` | Ctrl+F 后等待 |
| `PASTE_DELAY` | `0.05s` | Ctrl+A 后等待 |
| `SEARCH_POPULATE_DELAY` | `0.3s` | 粘贴后等待搜索结果 |
| `SELECT_RESULT_DELAY` | `0.15s` | Enter 后等待 |
| `WHITE_SCREEN_MEAN_THRESHOLD` | `248` | 白屏检测亮度均值阈值 |
| `WHITE_SCREEN_STDDEV_THRESHOLD` | `3.5` | 白屏检测标准差阈值 |

> 白屏保护 (`_looks_like_blank_window`) 采样 3 次、间隔 0.4s：刚从
> 最小化/隐藏恢复的窗口会短暂绘白，单次采样会误判；连续 3 次全白才拒绝发送。

---

### 功能F: 触发器系统

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `detector.py` | `src/trigger/detector.py` | 触发检测：关键词匹配 + @mention |

#### 触发条件类型

1. **@mention 触发**: 消息中 bot 被 @提及 → 总是触发
2. **关键词触发**: 消息内容匹配 `TRIGGER_KEYWORDS` 中任一关键词 → 触发总结

```python
class TriggerDetector:
    """两种触发条件:
    1. bot 被 @mention → 总是触发
    2. 消息内容匹配关键词列表 → 触发总结
    """
    def is_trigger(content, is_at_mentioned, sender_name) -> bool
```

#### 配置

| 参数 | 默认值 |
|---|---|
| `trigger_keywords` | `["总结一下", "之前发了什么", "错过了什么", "summarize", "what did i miss", "聊天总结", "帮我总结", "前面说了什么", "说了啥", "发生了什么"]` |
| `bot_display_name` | `"群聊小助手"` |

---

### 功能G: 待办事项

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `store.py` | `src/todo/store.py` | SQLite 存储 (CRUD + 自动清理) |
| `handler.py` | `src/todo/handler.py` | 命令解析与分发 |

#### 调用链

```
@bot 消息 → MessageRouter.handle(msg)
  │
  └── TodoHandler.handle(clean_content, chat_id, sender_id, sender_name, is_admin)
        │
        ├── 优先级1: 查看活跃待办 → list_active()
        ├── 优先级2: 查看已完成 → list_completed()
        ├── 优先级3: 查看已删除 → list_deleted()
        ├── 优先级4: 清空列表 (admin) → clear_completed() / clear_deleted()
        ├── 优先级5: 添加 (前缀匹配) → add()
        ├── 优先级6: 完成 (前缀匹配) → complete()
        ├── 优先级7: 删除 (前缀匹配) → delete()
        └── 优先级8: 恢复 (前缀匹配, admin) → restore()
```

#### 数据库表结构

```sql
CREATE TABLE todos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    display_order   INTEGER NOT NULL,  -- 每群单调递增, 永不改变
    status          TEXT    NOT NULL DEFAULT 'active',  -- active|completed|deleted
    creator_id      TEXT    NOT NULL DEFAULT '',
    creator_name    TEXT    NOT NULL DEFAULT '',
    created_at      REAL    NOT NULL,
    completed_by_id   TEXT    DEFAULT '',
    completed_by_name TEXT    DEFAULT '',
    completed_at      REAL    DEFAULT 0,
    deleted_by_id     TEXT    DEFAULT '',
    deleted_by_name   TEXT    DEFAULT '',
    deleted_at        REAL    DEFAULT 0
);
```

#### 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `todo_enabled` | `True` | 待办功能主开关 |
| `todo_groups` | `["*"]` | 启用待办的群组("*"=全部) |
| `todo_max_per_group` | `50` | 每群最大活跃待办数 |
| `todo_completed_retention_days` | `30` | 已完成保留天数(0=永久) |
| `todo_deleted_retention_days` | `30` | 已删除保留天数(0=永久) |

---

### 功能H: 飞书集成

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `client.py` | `src/integrations/feishu/client.py` | 飞书 OpenAPI 客户端 (纯 stdlib HTTP) |
| `exporter.py` | `src/integrations/feishu/exporter.py` | 导出服务 (协调消息→AI→飞书) |
| `knowledge.py` | `src/integrations/feishu/knowledge.py` | 知识库资源管理 + 内容分类器 |

#### 调用链

```
MessageRouter.handle(msg) → [飞书导出命令]
  │
  ├── FeishuExportService.is_export_command(content)
  │     └── 匹配 feishu_export_trigger_keywords
  │
  ├── [手动导出] FeishuExportService.export_recent_chat(trigger_msg)
  │     ├── _validate_target() — 验证配置完整性
  │     ├── _recent_messages() — 获取时间窗口内消息
  │     ├── _summarizer.summarize() — AI 总结
  │     ├── 按 mode 分支:
  │     │     ├── knowledge → _export_knowledge()
  │     │     │     ├── _ensure_knowledge_resources() — 创建/复用 Bitable
  │     │     │     └── KnowledgeClassifier.classify() — 结构化分类
  │     │     ├── spreadsheet → append_spreadsheet_rows()
  │     │     ├── bitable → create_bitable_record()
  │     │     └── docx → create_docx_with_markdown()
  │     └── 返回 FeishuExportResult
  │
  └── [自动同步] FeishuExportService.maybe_auto_export(msg)
        ├── 检查: auto_sync_enabled + mode == "knowledge"
        ├── 冷却: cooldown_sec 内不重复触发
        ├── 最低消息数: >= auto_sync_min_messages
        └── 同上 knowledge 导出流程
```

#### 4种导出模式

| 模式 | 目标 | 所需配置 |
|---|---|---|
| `knowledge` | 飞书多维表格知识库(5张表) | `app_id` + `app_secret` (自动创建) |
| `spreadsheet` | 飞书电子表格追加行 | `spreadsheet_token` + `spreadsheet_range` |
| `bitable` | 飞书多维表格单记录 | `bitable_app_token` + `bitable_table_id` |
| `docx` | 飞书文档 (markdown→段落) | `doc_folder_token` (可选) |

#### 知识库5张表

| 表 | key | 字段 |
|---|---|---|
| 群聊摘要 | `summary` | 同步时间,群聊,请求人,消息数,开始时间,结束时间,主题,摘要 |
| 待办 | `todo` | 创建时间,群聊,事项,负责人,截止时间,状态,来源 |
| 需求 | `requirement` | 创建时间,群聊,需求,提出人,优先级,状态,来源 |
| 日常记录 | `daily` | 记录时间,群聊,记录,分类,参与人,来源 |
| 项目 | `project` | 创建时间,群聊,项目,阶段,负责人,协作人,角色分工,提出人,来源 |

---

### 功能I: 语音识别

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `pipeline.py` | `src/voice/pipeline.py` | 端到端管道 (定位→解码→ASR→缓存) |
| `file_locator.py` | `src/voice/file_locator.py` | 语音文件定位 (.silk/.amr) |
| `decoder.py` | `src/voice/decoder.py` | SILK/AMR 解码 (pysilk + ffmpeg) |
| `asr.py` | `src/voice/asr.py` | ASR 后端 (LocalWhisper / OpenAI Whisper) |

#### 调用链

```
VoicePipeline.process(msg)
  │
  ├── 检查: voice_asr_enabled?
  │
  ├── VoiceCache.get(msg_svr_id) → 命中则直接返回
  │
  ├── VoiceFileLocator.find_voice_file(msg)
  │     ├── 搜索: {wxid}/msg/voice/{msg_svr_id}/*.silk
  │     ├── 搜索: {wxid}/msg/voice/{msg_svr_id}/*.amr
  │     ├── 搜索: {wxid}/msg/attach/{msg_svr_id}/*.silk
  │     └── 搜索: {wxid}/msg/attach/{msg_svr_id}/*.amr
  │
  ├── SilkDecoder.decode(audio_path) → .wav
  │     ├── .silk → _strip_wechat_silk_header() + pysilk.decode() → PCM → WAV
  │     └── .amr → ffmpeg subprocess → WAV
  │
  ├── AbstractASR.transcribe(wav_path, language)
  │     ├── LocalWhisperASR: faster_whisper.WhisperModel.transcribe()
  │     └── OpenAiWhisperASR: client.audio.transcriptions.create()
  │
  ├── VoiceCache.set(msg_svr_id, text, confidence)
  └── 清理临时 WAV 文件
```

#### ASR 后端对比

| 特性 | LocalWhisper (faster-whisper) | OpenAI Whisper API |
|---|---|---|
| 成本 | 免费 | $0.006/分钟 |
| 网络 | 离线 | 需要联网 |
| 内存 | ~1 GB (small 模型) | 0 |
| 模型大小 | tiny/base/small/medium | whisper-1 |
| 初次加载 | 下载 ~500MB | 即时 |
| 繁→简 | opencc t2s | opencc t2s |

#### 关键参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `voice_asr_enabled` | `False` | 语音识别主开关 |
| `voice_asr_backend` | `"local_whisper"` | ASR 后端选择 |
| `voice_asr_language` | `"zh"` | 识别语言 ("zh-en"/"auto"=自动) |
| `voice_local_model` | `"small"` | 本地 Whisper 模型大小 |
| `voice_asr_to_simplified` | `True` | 繁体→简体转换 |
| `_LOW_CONFIDENCE_THRESHOLD` | `0.6` | 低置信度打标 "[可能不准确]" |

---

### 功能J: 聊天记忆

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `consolidator.py` | `src/memory/consolidator.py` | 记忆合并触发和编排 |
| `store.py` | `src/db/store.py` | `group_memory` 表 CRUD |
| `schema.py` | `src/db/schema.py` | `group_memory` 表定义 |
| `prompts.py` | `src/summarize/prompts.py` | `MEMORY_CONSOLE_PROMPT` 模板 |

#### 数据库表结构

```sql
CREATE TABLE group_memory (
    chat_id           TEXT PRIMARY KEY,
    memory_text       TEXT NOT NULL DEFAULT '',
    message_count     INTEGER NOT NULL DEFAULT 0,
    last_message_id   TEXT,
    last_consolidated REAL,
    created_at        REAL NOT NULL DEFAULT (unixepoch()),
    updated_at        REAL NOT NULL DEFAULT (unixepoch())
);
```

#### 调用链

```
MessageRouter.handle(msg)
  │
  └── MemoryConsolidator.check_and_consolidate(chat_id)
        │
        ├── 获取当前记忆: MessageStore.get_group_memory(chat_id)
        ├── 统计新消息: MessageStore.get_new_message_count(chat_id, last_id)
        │
        ├── 触发条件 (任一满足):
        │     ├── 新消息数 >= CONSOLIDATE_MSG_THRESHOLD (50)
        │     └── 距上次合并 >= CONSOLIDATE_TIME_THRESHOLD_SEC (3600s)
        │
        ├── 获取新消息: MessageStore.get_messages_since_id()
        │
        ├── AI 合并: summarizer.consolidate_memory(existing, new_messages)
        │     └── 30s 超时 (ThreadPoolExecutor)
        │
        └── 持久化: MessageStore.upsert_group_memory()
```

#### 记忆格式

记忆采用**第一人称日记体**:
- "我"是 AI 助手在群中的身份
- 记录群友特点、口头禅、互动情况
- 记录群聊氛围和潜规则
- 限制 2000 字以内

#### 关键参数

| 参数 | 值 | 说明 |
|---|---|---|
| `CONSOLIDATE_MSG_THRESHOLD` | `50` | 触发合并的消息数阈值 |
| `CONSOLIDATE_TIME_THRESHOLD_SEC` | `3600` | 触发合并的时间阈值(1小时) |
| `MAX_NEW_MSGS_PER_CONSOLIDATION` | `400` | 每次合并最多处理的消息数 |
| 超时 | `30s` | AI 合并单次超时 |

---

### 功能K: macOS适配

#### 涉及文件

| 文件 | 路径 | 角色 |
|---|---|---|
| `desktop_mac.py` | `desktop_mac.py` | macOS 桌面入口 (WebView Cocoa) |
| `mac_ui_backend.py` | `src/wechat/mac_ui_backend.py` | macOS 界面自动化后端 |
| `mac_hybrid_backend.py` | `src/wechat/mac_hybrid_backend.py` | macOS 混合后端 (WCDB直读+自动化发送) |
| `mac_weflow_client.py` | `src/wechat/mac_weflow_client.py` | macOS WCDB 直读客户端 (WeFlow风格) |

#### MacHybridBackend 架构

```
MacHybridBackend
  │
  ├── 读路径: MacWeFlowClient
  │     ├── _WCDBSQLiteReader — ctypes 加载 libWCDB.dylib
  │     ├── 读取 session.db → get_sessions()
  │     ├── 读取 contact.db → get_contacts() → 显示名映射
  │     ├── 读取 message/*.db → get_new_messages()
  │     └── 密钥: all_keys.json (由 WeFlow 生成)
  │
  └── 写路径: MacUIAutomation
        ├── AppleScript (System Events) — 微信激活/搜索/发送
        ├── CoreGraphics (CGEventPost) — 屏幕点击
        ├── Vision OCR (VNRecognizeTextRequest) — 搜索匹配/标题验证
        └── 聊天标题映射缓存 — group_names.json + 日志行解析；实时 contacts/chatrooms 标题可覆盖旧缓存，sessions 标题保守替换
```

#### MacUIBackend (纯界面自动化)

- 无 WCDB 访问 — 完全依赖 UI 文本读取
- 通过 AppleScript `System Events` 读取可见文本
- 使用 Vision OCR 识别当前聊天标题和搜索结果
- 通过 CoreGraphics 模拟鼠标点击进行界面操作

#### macOS 特有配置

| 环境变量 | 说明 |
|---|---|
| `WEBOT_APP_HOME` | 应用数据目录 (默认 `~/Library/Application Support/WeChatBot`) |
| `MAC_WECHAT_APP_NAME` | 微信应用名 (默认 `"WeChat"`) |
| `MAC_WECHAT_SEND_SHORTCUT` | 发送快捷键 (`"enter"` 或 `"cmd_enter"`) |
| `MAC_CHAT_TITLE_MAP` | 聊天标题映射 (`{"username": "display_name", ...}` JSON) |
| `MAC_CHAT_TITLE_CACHE_FILE` | 聊天标题缓存文件路径 |
| `MAC_WEFLOW_WCDB_LIB_DIR` | WeFlow WCDB 库目录 |
| `MAC_WEFLOW_DATA_DIR` | WeChat 数据目录 |
| `MACOS_CODESIGN_IDENTITY` | macOS 代码签名身份 (构建时) |

#### macOS 构建 (`build-macos.spec`)

- 输出: `dist/WeChatBot.app`
- 捆绑 `libWCDB.dylib` → `native/macos/`
- hiddenimports 包含 `AppKit`, `Quartz`, `objc` 等 macOS 框架
- excludes 排除 Windows 专用模块 (`uiautomation`, `win32api`, `comtypes` 等)
- 权限声明: `NSAppleEventsUsageDescription` + `NSScreenCaptureUsageDescription`

### 功能L: 文生图

@机器人 且消息带生图意图时，调用 OpenAI 兼容 Images API 生成图片，通过剪贴板粘贴发送到群聊。

#### 触发条件（两者同时满足）

1. 消息 @机器人（含粘性提及）
2. 消息文本命中任一生图关键词（`IMAGE_GEN_KEYWORDS`，长词优先匹配）

关键词之后的内容作为生图提示词，例如“@机器人 画一张赛博朋克风格的猫” → 提示词“赛博朋克风格的猫”。

#### 调用链

```
WcdbBackend._poll_group() → _handle_message() [线程池]
  └── router.handle(msg)                                   [src/router.py]
        ├── @mention 路径: todo → 生图分支 → 总结/聊天
        ├── is_image_gen_intent(clean_content, keywords)   [src/imagegen/intent.py]
        └── _handle_image_gen(msg, clean_content)
              ├── extract_image_prompt()                   [src/imagegen/intent.py]
              ├── ImageGenerator.generate(prompt)          [src/imagegen/generator.py]
              │     ├── openai_images → POST {base}/images/generations (OpenAI/New API/One API 等兼容协议，urllib, 180s 超时)
              │     ├── google_gemini_image → POST {base}/interactions
              │     ├── dashscope_qwen → POST {base}/services/aigc/multimodal-generation/generation
              │     ├── _extract_image_bytes() — b64_json 内联 / url 外链 / DashScope image URL / Google base64 图片块
              │     └── _save_image() → <WEBOT_DATA_DIR>/images/imggen_<ts>_<rand>.<ext>
              └── 返回 ImageReply(image_path) / 失败回文本错误
WcdbBackend._handle_message()
  └── isinstance(reply, ImageReply)
        └── _send_image_and_confirm(group_name, talker, image_path)
              ├── WeChatWindowController.send_image_to_chat()  [src/wechat/window_controller.py]
              │     └── _run_send_pipeline(send_fn=send_image_message)
              │           ├── find → activate → 空白窗口检查 → navigate_to_chat
              │           ├── _set_clipboard_image() — PIL 转 BMP → 去 14 字节文件头 → CF_DIB 剪贴板
              │           ├── Ctrl+V 粘贴 → 等待 IMAGE_PASTE_SEND_DELAY(0.5s) 预览生成 → Enter 发送
              └── 成功后 _recent_sends 记入 (talker, "[图片]", ts) 防自触发
```

#### 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `IMAGE_GEN_ENABLED` | `false` | 总开关 |
| `IMAGE_GEN_PROTOCOL` | `openai_images` | 生图协议：`openai_images`、`google_gemini_image` 或 `dashscope_qwen`；OpenAI/New API/One API/GPT 兼容服务用 `openai_images`，Google 用 `google_gemini_image`，阿里云 compatible-mode + qwen-image 旧配置会自动推断为 DashScope |
| `IMAGE_GEN_API_KEY` | 空 | Images API 密钥；与 LLM 配置一致，UI 读取和保存均使用完整值 |
| `IMAGE_GEN_BASE_URL` | 空 | API 地址；OpenAI Images 保存时剥离 `/images/generations` `/models` 等后缀，Google 保存时补 `/v1beta`，DashScope 保存时纠正为 `/api/v1` |
| `IMAGE_GEN_MODEL` | 空 | 生图模型 ID；OpenAI Images 可通过 `POST /api/ai/models` 获取，Google/DashScope UI 提供内置选项 |
| `IMAGE_GEN_SIZE` | 空 | 可选尺寸；OpenAI/DashScope 直接传 size，Google 映射到 `response_format` |
| `IMAGE_GEN_KEYWORDS` | 见 §1.3 | 生图意图关键词，逗号分隔 |

#### 注意事项

- 未启用或缺 `IMAGE_GEN_MODEL` / `IMAGE_GEN_BASE_URL` 时，`create_image_generator()` 返回 `None`，生图分支自动跳过并回退普通 AI 对话
- 生图失败（网络/服务端错误）时回文本提示，不阻断其他路由分支
- 仅 Windows WCDB 后端支持图片发送；macOS 后端不在本功能范围内

---

## 5. 配置文件和环境变量

### 5.1 `.env` 文件完整配置项

```ini
# === AI 协议 ===
AI_BACKEND=openai_compatible                  # "openai_compatible"=Chat Completions；"claude"=Messages；legacy "deepseek" 仍兼容

# === Chat Completions 协议 ===
OPENAI_API_KEY=sk-xxx                          # API 密钥；本地无鉴权服务可空
OPENAI_BASE_URL=https://api.openai.com/v1      # API 地址；可填 .../v1 或完整 .../v1/chat/completions / .../v1/models
OPENAI_MODEL=                                  # 通过 UI 获取模型后选择

# === Messages 协议 ===
ANTHROPIC_API_KEY=sk-xxx                       # API 密钥
ANTHROPIC_BASE_URL=https://api.anthropic.com   # API 地址
SUMMARIZE_MODEL=                               # 通过 UI 获取模型后选择

# === Legacy provider preset fields ===
DEEPSEEK_API_KEY=sk-xxx                        # 旧预设兼容字段
DEEPSEEK_MODEL=                                # 旧预设模型 ID，需显式填写
DEEPSEEK_BASE_URL=https://api.deepseek.com     # 旧预设 API 地址

# === 微信后端 ===
WECHAT_BACKEND=wcdb                            # "wcdb" / "mac_hybrid" / "mac_ui"
WECHAT_GROUPS=*                                # 群名(逗号分隔, URL编码, "*"=全部)
WECHAT_FRIENDS=                                # 好友名/wxid(逗号分隔, URL编码, 空=不回复, "*"=全部)；优先在 UI 勾选
GROUP_CHAT_ENABLED=true                        # 群聊 AI 对话总开关；false 时不回复 @ 闲聊，主动发言也停止
FRIEND_CHAT_ENABLED=true                       # 好友私聊 AI 对话总开关；false 时完全不轮询好友私聊
WECHAT_DATA_DIR=                               # 微信数据目录(留空自动从微信进程参数/默认目录检测)
WEBOT_DATA_DIR=                                # WeChatBot 自身数据目录(留空=程序目录下 data；不影响微信数据目录)

# === 机器人身份 ===
BOT_DISPLAY_NAME=群聊小助手                     # 机器人显示名
ADMIN_WXID=                                    # 管理员 wxid

# === 触发关键词 ===
TRIGGER_KEYWORDS=总结一下,之前发了什么,错过了什么

# === 摘要配置 ===
SUMMARIZE_ENABLED=true
FALLBACK_WINDOW_HOURS=8

# === 主动发言 ===
PROACTIVE_ENABLED=false
PROACTIVE_RATE_WINDOW_SEC=120
PROACTIVE_RATE_QUIET=1.5
PROACTIVE_RATE_CASUAL=4.0
PROACTIVE_RATE_LIVELY=6.5
PROACTIVE_RATE_BURST=8.5

# === 欢迎新成员 ===
WELCOME_ENABLED=false

# === 粘性 @mention ===
STICKY_MENTION_ENABLED=true
STICKY_MENTION_TTL_SEC=60

# === 待办事项 ===
TODO_ENABLED=true
TODO_GROUPS=*
TODO_MAX_PER_GROUP=50
TODO_COMPLETED_RETENTION_DAYS=30
TODO_DELETED_RETENTION_DAYS=30

# === 调优 ===
POLL_INTERVAL_SEC=1.0
DEDUP_WINDOW_SEC=60
MAX_MESSAGES_FOR_SUMMARY=5000
CHUNK_SIZE=400

# === 日志 ===
LOG_LEVEL=INFO
LOG_FILE=data/bot.log                           # 留空/保持 legacy 默认时跟随 WEBOT_DATA_DIR；显式自定义路径则覆盖

# === 数据库 ===
DB_PATH=data/messages.db                        # 留空/保持 legacy 默认时跟随 WEBOT_DATA_DIR；显式自定义路径则覆盖

# === 趣味功能 ===
FUN_ENABLED=true

# === MCP 服务（暴露给 Codex / Trae 等智能体）===
MCP_ENABLED=true                               # 关闭后 /mcp、/mcp/sse 返回 403
MCP_API_KEY=                                   # 留空时在控制台「MCP 服务」一键生成；请求需 Bearer / X-API-Key
MCP_ALLOWED_HOSTS=                             # 可信 Host/Origin（默认仅回环，隧道/反代时追加域名）
MCP_GROUPS=                                    # 可读取的群聊：空或 * = 全部，none = 禁止，其余逗号分隔的群 ID
MCP_FRIENDS=                                   # 可读取的好友：空或 * = 全部，none = 禁止，其余逗号分隔的 wxid

# === 语音识别 ===
VOICE_ASR_ENABLED=false
VOICE_ASR_BACKEND=local_whisper
VOICE_ASR_LANGUAGE=zh
VOICE_LOCAL_MODEL=small
VOICE_ASR_TO_SIMPLIFIED=true

# === 文生图 ===
IMAGE_GEN_ENABLED=false                        # 总开关：@机器人 + 生图意图关键词时触发
IMAGE_GEN_PROTOCOL=openai_images              # openai_images / google_gemini_image / dashscope_qwen
IMAGE_GEN_API_KEY=                             # 生图 API 密钥；本地无鉴权服务可空
IMAGE_GEN_BASE_URL=                            # API 地址；OpenAI 可填 .../v1 或完整 .../v1/images/generations，Google 可填 .../v1beta，DashScope 可填 .../api/v1
IMAGE_GEN_MODEL=                               # 通过 UI 生图模型配置获取模型后选择
IMAGE_GEN_SIZE=                                # 可选尺寸(如 1024x1024)；留空由模型默认
IMAGE_GEN_KEYWORDS=画一张,画一个,画一幅,画一只,画个,帮我画,生成一张,生成一幅,生成图片,生图,来一张图,画出来

# === 飞书导出 ===
FEISHU_EXPORT_ENABLED=false
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_EXPORT_MODE=knowledge
FEISHU_EXPORT_WINDOW_HOURS=8
FEISHU_AUTO_SYNC_ENABLED=false
FEISHU_AUTO_SYNC_MIN_MESSAGES=20
FEISHU_AUTO_SYNC_COOLDOWN_SEC=1800
FEISHU_KNOWLEDGE_BASE_NAME=webot 群聊沉淀
FEISHU_EXPORT_TRIGGER_KEYWORDS=同步到飞书,导出到飞书,写到飞书,沉淀到飞书

# === 引导流程 ===
# 草稿/步骤进度存储在 SQLite onboarding_state 表。
ONBOARDING_DONE=false
WCDB_KEY=
```

### 5.2 `build.spec` 打包配置 (Windows)

```python
# 入口: desktop.py
# 输出: dist/WeChatBot.exe
# 二进制:
#   - WebView2Loader.dll → runtimes/win-x64/native
#   - WebBrowserInterop.x64.dll → lib/
#   - MSVCP140.dll → native/windows/
#   - VCRUNTIME140.dll → native/windows/
#   - VCRUNTIME140_1.dll → native/windows/
#   - wx_key.dll → native/windows/ (仅密钥提取回退路径使用)
# 说明: Windows 读取器已改为纯 Python，不再打包 wcdb_api.dll / WCDB.dll
# 数据:
#   - ui/dist → ui/dist (前端构建产物)
#   - .env.example → . (示例配置)
# 排除: faster_whisper, ctranslate2, numpy, onnxruntime, pysilk, tkinter, matplotlib, scipy
```

#### Windows 安装包 (`installer.nsi`)

- 输出: `dist/WeChatBot-setup.exe`
- 页面: 欢迎 → 许可证 → 安装目录 → WeChatBot 数据目录 → 安装进度 → 完成
- 安装目录默认: `$LOCALAPPDATA\WeChatBot`
- 升级安装时会从 HKCU 卸载注册表键读取 `InstallLocation`，自动复用上次安装目录；兼容旧版安装包，旧版没有该字段时从 `UninstallString` 推断安装目录
- 覆盖 `$INSTDIR\WeChatBot.exe` 前会先尝试删除旧文件；如果被运行中的 WeChatBot 占用，安装器会提示用户并调用 `taskkill /IM WeChatBot.exe /T /F` 自动关闭后重试，避免出现 NSIS 原生的 Abort/Retry/Ignore 写入失败弹窗
- WeChatBot 数据目录默认: `$INSTDIR\data`；用户可在安装时浏览/手输其他目录
- 安装阶段会创建所选数据目录，并向 `$INSTDIR\.env` 追加 `WEBOT_DATA_DIR=<所选目录>`；如果 `.env` 不存在，先从 `.env.example` 复制
- 安装完成会向 HKCU 卸载注册表键写入 `InstallLocation`、`WebotDataDir`、`QuietUninstallString` 等字段；升级安装时优先复用 `WebotDataDir`，旧版没有该字段时从既有 `.env` 的最后一个 `WEBOT_DATA_DIR=` 读取
- 该目录只保存 WeChatBot 自身数据，不移动、不修改微信自己的数据目录
- 静默安装未显示自定义页时，`WEBOT_DATA_DIR` 自动回退为 `$INSTDIR\data`

### 5.3 `requirements.txt` 依赖说明

| 包名 | 用途 | 必需 |
|---|---|---|
| `python-dotenv>=1.0.0` | 加载 .env 环境变量 | 是 |
| `anthropic>=0.45.0` | Claude API SDK | 按后端需求 |
| `openai>=1.0.0` | OpenAI 兼容 Chat Completions 后端 / DeepSeek 预设 / Whisper API | 按后端需求 |
| `ddgs>=9.0` | DuckDuckGo 搜索 (AI 上下文增强) | 是 |
| `pydantic>=2.0.0` | 结构化输出模型 (SummaryResult) | 是 |
| `uiautomation>=2.0` | Windows UI 自动化 (窗口操控) | Windows 必需 |
| `pywin32>=300` | Windows API 绑定 (窗口/剪贴板/进程) | Windows 必需 |
| `comtypes>=1.4` | COM 类型库 (UIA) | Windows 必需 |
| `pywebview>=5.0` | 桌面 WebView 窗口 | 是 |
| `Pillow>=10.0` | 图像处理 (白屏检测) | 是 |
| `psutil>=5.0` | 进程管理 | 是 |
| `pyperclip>=1.8` | 剪贴板操作 | 是 |
| `silk-python>=0.2.8` | SILK v3 音频解码 | 语音功能 |
| `faster-whisper>=1.0` | 本地语音识别 | 语音功能 |
| `opencc-python-reimplemented>=0.1.7` | 繁简中文转换 | 语音功能 |

### 5.4 前端依赖 (`ui/package.json`)

| 包名 | 用途 |
|---|---|
| `react` / `react-dom` `^19.2.7` | UI 框架 |
| `framer-motion` `^12.40.0` | 动画库 (Spring 过渡) |
| `@phosphor-icons/react` `^2.1.10` | 图标库 |
| `@tailwindcss/vite` `^4.3.0` | Tailwind CSS v4 集成 |
| `@vitejs/plugin-react` `^6.0.2` | Vite React 插件 |
| `tailwindcss` `^4.3.0` | CSS 框架 |
| `vite` `^8.0.16` | 构建工具 |

### 5.5 数据文件 (运行时生成)

默认情况下，WeChatBot 自身生成的数据写入 `WEBOT_DATA_DIR`（留空时为程序目录下 `data/`）。`DB_PATH` 与 `LOG_FILE` 如果保持 `data/messages.db` / `data/bot.log` legacy 默认，也会跟随 `WEBOT_DATA_DIR`；只有填写其他显式路径时才单独覆盖。`WECHAT_DATA_DIR` 仍只指向微信自己的数据目录，不参与这些文件的存储。

| 文件路径 | 生成者 | 内容 |
|---|---|---|
| `<WEBOT_DATA_DIR>/messages.db` | `src/db/schema.py` | SQLite 消息数据库 |
| `<WEBOT_DATA_DIR>/bot.log` | `src/utils/logging_config.py` | 运行日志 |
| `<WEBOT_DATA_DIR>/bot_status.json` | `src/bot.py:HealthMonitor` | 状态 JSON (外部监控) |
| `<WEBOT_DATA_DIR>/nicknames.json` | `src/nickname.py` | wxid → 昵称映射 |
| `<WEBOT_DATA_DIR>/group_names.json` | `src/wechat/wcdb_backend.py` | chat_id → {name, member_count, active}（`active=False` 表示已退群/群解散） |
| `<WEBOT_DATA_DIR>/friend_names.json` | `src/wechat/wcdb_backend.py` | `{"account", "friends"}`；friends 内 wxid → {name, alias, active}（`active=False` 表示已不是好友） |
| `<WEBOT_DATA_DIR>/group_members.json` | `src/wechat/wcdb_backend.py` | chat_id → {wxid: display_name} |
| `<WEBOT_DATA_DIR>/welcome_templates.json` | `src/welcome.py` | 欢迎模板 + 群映射 |
| `<WEBOT_DATA_DIR>/lots.json` | `src/fun.py` | 自定义抽签配置 |
| `<WEBOT_DATA_DIR>/feishu_resources.json` | `src/integrations/feishu/knowledge.py` | 飞书知识库资源 ID |
| `<WEBOT_DATA_DIR>/voice_cache.json` | `src/voice/pipeline.py` | 语音识别缓存 |
| `<WEBOT_DATA_DIR>/send_failures.log` | `src/wechat/window_controller.py` | 发送失败记录 |
| `<WEBOT_DATA_DIR>/crash.log` | `desktop.py` / `desktop_mac.py` | 崩溃日志 |
| `<WEBOT_DATA_DIR>/models/` | `src/voice/asr.py` | 本地 Whisper 模型缓存 |

`POST /api/runtime/reset` 会清空配置后的 `messages.db` 中的运行表(`messages`、`user_last_message`、`trigger_log`、`group_memory`、`todos`)，删除当前及重置后默认 WeChatBot 数据目录中的运行缓存/日志文件(`bot.log`、`bot_status.json`、`send_failures.log`、`group_members.json`、`group_names.json`、`nicknames.json`)，删除 `.env`，清理 `onboarding_state` 和进程内 WeChatBot 配置键，使前端重新进入首次启动流程；不删除欢迎模板、抽签配置、飞书资源记录、语音模型或语音缓存。

---

## 附录：WeChatBot 二次开发新增模块

> 本附录记录项目从上游 `webot` 二次开发为 **WeChatBot** 后，本次会话新增/修改的模块。正文 §1–§5 描述的是二开前的既有架构，本附录与正文并存、互不覆盖：新增内容统一放在这里，正文仅保留少量交叉引用（见文首指引与目录第 6 项）。所有函数签名、常量、参数均逐字取自源码。
>
> 本次变更一览：
> - 新增「系统群发分组」配置层 `src/broadcast.py`（独立于微信原生通讯录标签）；
> - 新增「微信通讯录标签」只读读取链 `src/wechat/labels.py` → `wxdb_reader.py` → `local_wcdb_client.py`；
> - `src/mcp_server/data.py` 新增消息发送（单发/批量共用内核）与分组/标签只读工具，`server.py` 的 `TOOLS` 由 14 增至 18 个（新增 4 个）；
> - `src/web/server.py` 新增 3 个 Web API 端点、1 条 `do_POST` 白名单与 1 个数据迁移项；
> - 前端新增 2 个面板、2 处 `TABS`/分支改动；
> - 品牌统一改名 WeChatBot，但一批内部标识符刻意保持不变（见 附录.5）。

### 附录.1 新增源文件

#### 附录.1.1 `src/broadcast.py` — 群发分组配置（独立于微信原生标签）

用户在控制台自行维护的分组，**与微信自带的通讯录标签完全独立**：不读取、不导入、不同步微信标签，两者互不影响。同一分组里可同时放好友和群聊，用 `type` 区分。配置存数据目录的 `broadcast_groups.json`，不写进 `.env`（`.env` 是纯文本 key=value，装不下嵌套结构且并发写会互相覆盖）。所有写操作经模块级 `threading.RLock` + `.tmp` 临时文件原子替换；每次读取都重新读盘，改完无需重启机器人。

**模块级常量**

| 常量 | 值 | 用途 |
|---|---|---|
| `CONFIG_FILE` | `"broadcast_groups.json"` | 配置文件名，交给 `webot_data_path(CONFIG_FILE)` 定位 |
| `CONFIG_VERSION` | `1` | 配置结构版本 |
| `MAX_GROUPS` | `100` | 分组数量上限 |
| `MAX_NAME_CHARS` | `60` | 分组名 / 目标展示名最大字符数 |
| `MAX_TARGETS_PER_GROUP` | `500` | 单分组目标数上限 |
| `MAX_TOTAL_TARGETS` | `5000` | 所有分组目标总数上限 |
| `VALID_TYPES` | `("friend", "group")` | 合法目标类型 |
| `_lock` | `threading.RLock()` | 模块级锁，保护 `save()` 的原子写 |

**函数清单**（签名逐字取自源码）

| 函数 | 签名 | 说明 |
|---|---|---|
| `config_path` | `def config_path() -> Path:` | 返回当前数据目录下的分组配置文件路径（每次现算，支持运行时改数据目录），值 = `webot_data_path(CONFIG_FILE)` |
| `_default_config` | `def _default_config() -> dict:` | 返回 `{"version": CONFIG_VERSION, "groups": []}` |
| `load` | `def load() -> dict:` | 读取配置；文件不存在/损坏/非 dict/`groups` 非 list 时回退到空配置，绝不抛出影响主流程；成功返回 `{"version": CONFIG_VERSION, "groups": groups}` |
| `groups` | `def groups() -> list[dict]:` | 返回分组列表（只读视图，`load().get("groups", [])`） |
| `validate` | `def validate(data: Any) -> dict:` | 校验并规范化整个配置，任何不合法结构抛 `ValueError`；规则：分组名非空且互不重复、目标 `type` 只能是 friend/group、目标 id 非空、同组内 `(type, id)` 去重、数量不超过上限、群 id 带 `@` 时须以 `@chatroom` 结尾 |
| `save` | `def save(data: Any) -> dict:` | 先 `validate(data)`，再在 `_lock` 内写 `.tmp` 并 `tmp.replace(path)` 原子替换，返回规范化后的配置；日志记录分组数/目标数 |
| `find_group` | `def find_group(name: str) -> dict \| None:` | 按名称精确查找分组，大小写不敏感（`casefold`）；找不到返回 `None` |
| `target_ids` | `def target_ids(group: dict) -> list[str]:` | 取出分组内所有非空目标 id（好友 wxid / 群 chat_id），用于发送 |

**存储结构**

```json
{
  "version": 1,
  "groups": [
    {"name": "客户通知", "targets": [
      {"type": "friend", "id": "wxid_abc", "name": "张三"},
      {"type": "group",  "id": "12345@chatroom", "name": "客户群"}
    ]}
  ]
}
```

`id` 用稳定标识（好友存 wxid，群存 `xxx@chatroom`）；`name` 只是展示用快照，昵称改了不影响发送。路径由 `webot_data_path(CONFIG_FILE)` 决定，读失败回退空配置（`_default_config()`）。

#### 附录.1.2 `src/wechat/labels.py` — 微信通讯录标签只读入口

**与系统群发分组完全独立**：这里读的是微信自带的通讯录标签，不会被导入、同步或合并到 `src.broadcast` 维护的群发分组里。供 Web API 与 MCP 工具共用，避免两处各自解密数据库。

| 函数 | 签名 | 说明 |
|---|---|---|
| `_running_client` | `def _running_client():` | 优先复用运行中机器人已解密的 WCDB 客户端：从 `src.web.server._bot_control.get_backend()` 取 `_client`（要求 `_client._db` 不为 None），避免重复取密钥/解密；异常时返回 `None` |
| `_friend_names` | `def _friend_names() -> dict[str, str]:` | 读 `<WEBOT_DATA_DIR>/friend_names.json`，产出 wxid → 展示名，用于给标签成员补昵称；文件不存在/损坏返回 `{}` |
| `read_contact_labels` | `def read_contact_labels() -> dict:` | 返回微信原生通讯录标签报告；优先 `_running_client()`，无则 `LocalWcdbClient()` + `.init()`；再调 `client.get_contact_labels()`；`pop("member_names")` 拿到 contact.db 里的 remark/nick_name，与 `_friend_names()` 合并（好友缓存优先）后把每个标签的 `members` 从 wxid 列表补成 `[{"wxid", "name"}]`，并重算 `member_count`；已经是 dict 的 member 也兼容 |

**返回结构**

```python
{
  "available": bool,        # 是否读到 contact_label 表
  "labels": [
    {
      "label_id": str, "name": str, "sort_order": ...,
      "member_count": int,
      "members": [{"wxid": str, "name": str}],   # labels.py 补昵称后的结构
    },
  ],
  "source": str,            # 命中的关联来源，如 "contact.extra_buffer#30"
                            # 或 "contact_label_contact.label_id_/username_"
  "tables": [str],          # 标签相关表 + 命中 extra_buffer 时的 "contact"，仅用于诊断
  "note": str,              # 成功时说明好友数与来源；失败/降级时说明原因
}
```

`member_names` 是 `client.get_contact_labels()` 的中间产物（wxid → 展示名），
在 `read_contact_labels()` 里被 `pop` 掉，不会出现在 API / MCP 返回值中。

失败时返回 `available=False` + `note`，不抛异常（如 `"微信本地数据库不可用：{exc}"`）。

#### 附录.1.3 `src/wechat/wxdb_reader.py` — 标签读取（模块级助手 + `WeChatDB` 方法）

**模块级常量与助手**（放在 `MSG_TYPE_NAMES` 之前）

| 名称 | 签名 | 说明 |
|---|---|---|
| `_LABEL_LIST_RE` | `re.compile(r"^[0-9]{1,10}(?:\s*[,;|]\s*[0-9]{1,10})*$")` | 逗号/分号/竖线分隔的数字 id 串 |
| `_pb_varint` | `def _pb_varint(buf: bytes, pos: int):` | 读一个 protobuf varint，返回 `(value, new_pos)`；截断/超长抛 `ValueError` |
| `_pb_fields` | `def _pb_fields(buf: bytes):` | 最小 wire-format 解析，产出 `[(field_no, wire_type, value), ...]`；只处理 0/1/2/5，遇到未知或截断就地停止、不抛异常，不假设 schema |
| `_pb_label_ids` | `def _pb_label_ids(value, known_ids: set) -> list:` | 把 bytes 值解析成标签 id 列表；要求纯 ascii、长度 ≤200、形如数字串、且**每个 id 都在 `contact_label` 里**，否则返回 `[]`（避免头像 URL / 地区名 / 单数字标志位误判） |

**`WeChatDB` 方法**

| 方法 | 签名 | 说明 |
|---|---|---|
| `_label_contact_columns` | `def _label_contact_columns(self, conn: sqlite3.Connection, table: str):` | 在候选关联表里 `PRAGMA table_info` 探列，找出 `(标签列, 联系人列)`；标签列优先 `label_id*`、避开 `label_name*`、短列名优先，联系人列按 `contact/username/user_name/wxid/member/uid` 提示匹配再退回 `*id`/`usrname`；无法确认返回 `(None, None)` |
| `_labels_from_extra_buffer` | `def _labels_from_extra_buffer(self, conn: sqlite3.Connection, known_ids: set):` | **微信 4.x 主路径**：扫描 `contact.extra_buffer` 的 protobuf 字段，统计各字段命中合法标签 id 的次数；field 30 优先（4.1.15.13 实测），否则按「覆盖 ≥2 种标签 → 多标签条数 → 命中数」打分选字段；返回 `(mapping, member_names, source)` |
| `contact_label_report` | `def contact_label_report(self) -> dict:` | 纯只读、尽力而为、绝不抛影响主流程；依次尝试 `extra_buffer` → 独立关联表 → `contact` 内 label 列三种来源，任何一步失败都静默降级；返回 `member_names` 供上层补昵称 |

**`contact_label_report()` 读取策略（ASCII 调用链）**

```
contact_label_report()
  │
  ├─ list_labels() → 读 contact_label 表拿标签定义；为空则 note 提示并返回 available=False
  ├─ _contact_conn() → 打开 contact.db；不可读则 note="contact.db 不可读"
  ├─ 枚举 sqlite_master 中含 label 的表 → report["tables"]
  ├─ known_ids = {str(label["label_id"]) for label in labels}
  │
  ├─ 来源⓪ _labels_from_extra_buffer(conn, known_ids)   ← 微信 4.x 实际存储
  │     ├─ PRAGMA table_info(contact) → 需有 username + extra_buffer
  │     ├─ SELECT username, extra_buffer, remark, nick_name
  │     │     FROM contact WHERE extra_buffer 非空
  │     ├─ 逐行 _pb_fields(bytes(blob)) → 对 wire=2 的字段调 _pb_label_ids()
  │     │     └─ 按 field_no 累计 hits[(wxid, [label_id...], name)]
  │     ├─ 选字段：30 存在则取 30，否则 max(hits, key=score)
  │     └─ 命中 → mapping / member_names / source="contact.extra_buffer#N"
  │           └─ report["tables"] 追加 "contact"
  │
  ├─ PRAGMA table_info(contact) → 若含 id/username，建 contact.id → username 映射
  │
  ├─ 来源① 独立关联表（仅当 mapping 仍为空；跳过 contact_label / contact）
  │     ├─ _label_contact_columns(conn, table) → (label_col, contact_col)
  │     ├─ SELECT label_col, contact_col → 逐行还原
  │     │     └─ 关联值是数字 id 时用 id_to_username 还原 wxid，否则原样当 wxid
  │     └─ 命中即写 report["source"]=f"{table}.{label_col}/{contact_col}" 并 break
  │
  ├─ 来源② 回退：contact 表内直接存逗号分隔 label id 的字段（如 label_list_）
  │     ├─ PRAGMA table_info(contact) → 找含 label 且不含 name 的字段
  │     ├─ SELECT field, username FROM contact → re.split(r"[,;|\s]+", raw)
  │     └─ 命中即写 report["source"]=f"contact.{field}"
  │
  ├─ 兜底补昵称：member_names 里缺的 wxid 按 400 个一批回查 contact 表
  │
  └─ 组装 out：[{label_id, name, sort_order, member_count, members:[wxid,...]}]
        ├─ 无 source → note="未找到标签与联系人的关联数据…"
        └─ 有 source → note="已读取 N 位好友的标签归属（来源 …）" + 只读声明
```

> 实测背景：4.1.15.13 的 `contact.db` 共 17 张表，只有 `contact_label`
> （13 行）一张标签表，**没有** `contact_label_contact` 之类关联表，
> `contact` 也没有 label 列。旧实现因此只能显示标签、成员恒为空。
> 标签 id 逗号串实际存在 `contact.extra_buffer` protobuf 的 field 30，
> 本机 54 位好友 / 81 条标签归属全部可读。

注意：`contact_label_report()` 返回的 `members` 仍是 **wxid 字符串列表**；补昵称成 `[{"wxid","name"}]` 是 `src/wechat/labels.py:read_contact_labels()` 完成的。

#### 附录.1.4 `src/wechat/local_wcdb_client.py` — 新增透传方法

| 方法 | 签名 | 说明 |
|---|---|---|
| `get_contact_labels` | `def get_contact_labels(self) -> dict:` | 只读返回微信通讯录标签及成员；`return self._require_db().contact_label_report()`；异常时 `logger.warning` 并返回 `{"available": False, "labels": [], "source": "", "tables": [], "note": str(exc)}` |

#### 附录.1.5 `src/mcp_server/data.py` — 消息发送与分组/标签工具

**新增模块级常量**

| 常量 | 值 | 用途 |
|---|---|---|
| `MAX_SEND_CONTENT_CHARS` | `2000` | 消息正文最大字符数 |
| `MAX_SEND_TARGETS` | `50` | 单批发送目标数上限 |
| `DEFAULT_SEND_INTERVAL_MS` | `800` | 批量发送每条之间的默认间隔（毫秒） |
| `MAX_SEND_INTERVAL_MS` | `5000` | `interval_ms` 上限 |

**新增函数清单**（签名逐字取自源码）

| 函数 | 签名 | 说明 |
|---|---|---|
| `_running_backend` | `def _running_backend():` | 延迟导入 `src.web.server._bot_control`，取 `get_backend()`；backend 为 None 或无 `send_text` 时抛 `ValueError`（提示先启动机器人） |
| `_send_content` | `def _send_content(args: dict) -> str:` | 取并校验 `content`：空抛 `ValueError`，超过 `MAX_SEND_CONTENT_CHARS` 抛 `ValueError`，返回正文 |
| `_send_one` | `def _send_one(raw, content: str, backend, dry_run: bool) -> dict:` | **单发/批量共用的发送内核**；返回 `{chat, chat_id, ok, error, dry_run}`，返回值与日志都不含正文 |
| `_scoped_targets` | `def _scoped_targets(targets: list) -> tuple[list, int]:` | 按 MCP 数据范围过滤分组目标，返回 `(可见目标, 被隐藏数量)`；跳过非 dict / 无 id / 不在范围内的目标 |
| `list_broadcast_groups` | `def list_broadcast_groups(args: dict) -> dict:` | 只读列出系统群发分组；`name` 模糊筛选；每个分组经 `_scoped_targets` 过滤后返回 `name / target_count / hidden_count / targets`；顶层 `total / groups / note` |
| `send_message` | `def send_message(args: dict) -> dict:` | 单发：取正文 → `dry_run = _arg_bool(args, "dry_run", False)` → `backend = None if dry_run else _running_backend()` → `_send_one(...)`；日志只记 `ok/dry_run` |
| `batch_send_messages` | `def batch_send_messages(args: dict) -> dict:` | 批量：`chats` 数组 + `group` 分组名合并去重 → 校验 `MAX_SEND_TARGETS` → 串行逐个 `_send_one`，每条之间 `time.sleep(interval_ms / 1000.0)`（仅非 dry_run 且 index>0）→ 返回 `total/succeeded/failed/dry_run/group/interval_ms/results` |
| `list_wechat_labels` | `def list_wechat_labels(args: dict) -> dict:` | 只读；调 `read_contact_labels()`，追加 `scope="wechat_native_labels"` 并拼接 `note`，返回报告 |

`TOOL_FUNCTIONS` 映射（`src/mcp_server/data.py` 末尾）同步登记了上述 4 个新函数，键即工具名。

**`_send_one` 内核调用链（单发与批量共用）**

```
send_message() ───────┐
                      ├→ _send_content(args) → 校验/返回 content
batch_send_messages() ┘   │
                          ├→ _running_backend()   ← dry_run 时不调用，backend=None
                          │
                          └→ _send_one(raw, content, backend, dry_run)
                               │
                               ├─ _resolve_chat(str(raw)) → 群名/昵称/wxid 解析为 chat_id
                               ├─ _require_chat_allowed(chat_id) → MCP 数据范围校验（越界抛 ValueError）
                               ├─ dry_run=True → 直接 ok=True 返回，不发送
                               └─ backend.send_text(chat_id, content) → 实际发送
                                    └─ 返回 False → error="发送失败，请确认微信窗口可见且该会话存在"
```

要点：
- `_send_one` 是单发/批量**共用内核**，调用链 `_resolve_chat` → `_require_chat_allowed` → `backend.send_text(chat_id, content)`；`ValueError` 与 `Exception` 都收敛进 `item["error"]`，不影响其他目标。
- `dry_run=True` 时 `send_message` / `batch_send_messages` 都**不取 backend**（`backend = None if dry_run else _running_backend()`），只做解析与范围校验。
- 批量发送**串行**执行、每条之间 `time.sleep`（剪贴板与微信前台窗口是全局资源，间隔降低丢消息概率）；`dry_run` 或 `interval_ms=0` 不 sleep。
- **日志与返回值都不含消息正文**：日志只记录 `ok / dry_run / succeeded / total / group`，返回值只含 chat_id / 目标结果与统计元信息。

### 附录.2 新增/修改的 Web API（`src/web/server.py`）

| 方法 | 路径 | 请求体 | 返回 | 实现要点 |
|---|---|---|---|---|
| `GET` | `/api/broadcast/groups` | — | `{ok, groups, options}` | `groups` = `broadcast.groups()`；`options` = `mcp_server.data.scope_options()`（供前端选目标的群聊/好友候选）；异常返回 `{ok:False, error}` |
| `POST` | `/api/broadcast/groups` | `{"groups":[...]}` | `{ok, groups}` | 读 body → `json.loads` → `broadcast.save(data)`（内部 `validate` 校验 + `.tmp` 原子写）→ 返回 `saved["groups"]`；`ValueError` 单独捕获回传错误信息 |
| `GET` | `/api/wechat/labels` | — | `{ok, **read_contact_labels()}` | 纯只读；`{"ok": True, **read_contact_labels()}` 把 available/labels/source/tables/note 平铺返回；异常返回 `{ok:False, error}` |

配套改动：
- `do_POST` 白名单（约 `server.py:1924`）新增 `"/api/broadcast/groups"`，命中后委托 `do_GET()` 处理（与 `/api/config` 等一致）。
- `_WEBOT_DATA_MIGRATION_ITEMS`（约 `server.py:585`，供 `_migrate_webot_data_dir()` 在 `WEBOT_DATA_DIR` 变更时搬迁 WeChatBot 自有数据）新增 `"broadcast_groups.json"`。

**Web API → 配置层 调用链**

```
GET  /api/broadcast/groups
  ├→ broadcast.groups() → broadcast.load() → config_path() → webot_data_path(CONFIG_FILE)
  └→ mcp_server.data.scope_options() → {groups:[...], friends:[...]}

POST /api/broadcast/groups
  └→ broadcast.save(data)
       ├→ broadcast.validate(data)  → 结构/数量/去重校验，非法抛 ValueError
       └→ _lock → .tmp 写入 → tmp.replace(path) 原子替换

GET  /api/wechat/labels
  └→ src.wechat.labels.read_contact_labels()
       ├→ _running_client() 或 LocalWcdbClient().init()
       ├→ client.get_contact_labels() → WeChatDB.contact_label_report()
       └→ _friend_names() → members 补 [{"wxid","name"}]
```

### 附录.3 MCP 工具（`src/mcp_server/server.py`）

`TOOLS` 本次新增 **4 个**工具，总数由 14 增至 **18 个**（与 `TOOL_FUNCTIONS` 映射一致）。模块顶部 `for _tool in TOOLS: _tool.setdefault("annotations", dict(READ_ONLY_ANNOTATIONS))` 给所有工具补默认注解；`READ_ONLY_ANNOTATIONS = {readOnlyHint: True, destructiveHint: False, idempotentHint: True, openWorldHint: False}`。

**新增 4 个工具**

| 工具名 | 用途 | 参数（inputSchema） | annotations | 前置条件 |
|---|---|---|---|---|
| `list_broadcast_groups` | 只读列出系统群发分组（与微信原生标签无关），供发送前确认分组名与目标 | `name`（string，可选，名称模糊筛选） | 默认 `READ_ONLY_ANNOTATIONS` | 无；受 MCP 数据范围限制，不在范围内的目标被隐藏为 `hidden_count` |
| `send_message` | 向单个好友/群聊发送一条文本消息（写操作） | `chat`（string，**必填**：群 ID/群名/好友 wxid/昵称/备注）、`content`（string，**必填**，最长 2000 字）、`dry_run`（boolean，默认 `False`） | **显式覆盖**：`readOnlyHint:False, destructiveHint:True, idempotentHint:False, openWorldHint:True` | 机器人已启动、微信已登录且窗口可见、目标在 MCP 数据范围内；建议先 `dry_run=true` |
| `batch_send_messages` | 批量向多个好友/群聊发送同一条文本（写操作，串行） | `content`（string，**必填**）、`chats`（array of string，目标数组）、`group`（string，群发分组名）、`interval_ms`（integer，0–5000，默认 800）、`dry_run`（boolean，默认 `False`） | **显式覆盖**：同 `send_message` | 同 `send_message`；`chats` 与 `group` 至少给一个；单次最多 50 个目标；强烈建议先 `dry_run=true` |
| `list_wechat_labels` | 只读列出微信自带通讯录标签及各标签下好友（wxid + 昵称） | 无（`_object()`） | 默认 `READ_ONLY_ANNOTATIONS` | 无；底层优先解析 `contact.extra_buffer`，再回退动态探关联表；读不到时 `available=false` + `note`，标签成员为空 |

> `send_message` 与 `batch_send_messages` 是仅有的两个**显式写了非只读 annotations** 的工具，用于覆盖默认的 `READ_ONLY_ANNOTATIONS`；其余 16 个工具（含新增的 `list_broadcast_groups`、`list_wechat_labels`）沿用默认只读注解。

`initialize` 响应的 `instructions`（约 `server.py:945`）也补充了消息工具调用指引：先 `search_contacts` 确认目标再 `send_message` 单发；批量先 `list_broadcast_groups` 再用 `batch_send_messages` 传 `group` 或 `chats`；发送属写操作，要求机器人已启动且微信窗口可见，务必先 `dry_run=true` 预览、向用户确认后再真正发送，不要擅自群发；`list_wechat_labels` 为只读视图，与系统群发分组无关。

### 附录.4 前端新增/修改

| 文件 | 改动 |
|---|---|
| `ui/src/components/BroadcastGroupsPanel.jsx`（新增） | `export default function BroadcastGroupsPanel()`；「系统配置 → 群发分组」子标签面板；`load()` 用 `GET /api/broadcast/groups` 拿 `groups` + `options`，保存用 `POST /api/broadcast/groups`（`body: JSON.stringify({ groups })`）；候选目标由 `options.groups` / `options.friends` 映射出 `type/id/name` |
| `ui/src/components/WeChatLabelsPanel.jsx`（新增） | `export default function WeChatLabelsPanel()`；顶层「通讯录标签」标签面板；`load()` 用 `GET /api/wechat/labels`；状态条显示标签数 + 去重好友数（`totalFriends`），每个标签卡片列出成员（名称优先、无名称回退 wxid）；页面明确标注「微信通讯录标签（只读）」及 `contact.extra_buffer` 来源，与 WeChatBot 群发分组完全独立 |
| `ui/src/App.jsx`（修改） | `TABS`：`config.subs` 新增 `{ id: 'broadcast', label: '群发分组' }`；顶层新增 `{ id: 'wechat-labels', label: '通讯录标签', icon: Tag }`；新增 `WeChatLabelsPanel` 的 `lazy` import；渲染处新增 `activeTab === 'wechat-labels' && <WeChatLabelsPanel />`；`activeTab === 'config'` 仍交给 `ConfigPanel activeSection={configSection}` |
| `ui/src/components/ConfigPanel.jsx`（修改） | `import BroadcastGroupsPanel`；`sectionTitles`/`sectionAccents` 增加 `broadcast` 项；渲染处新增 `activeSection === 'broadcast' && <BroadcastGroupsPanel />`；主「保存配置」按钮条件改为 `activeSection !== 'sandbox' && activeSection !== 'broadcast'`，**在群发分组子标签隐藏**（该面板有独立保存逻辑，避免误把分组写进 `.env`） |

**前端 → API 调用链**

```
App.jsx TABS
  ├─ config / broadcast ─→ ConfigPanel(activeSection='broadcast')
  │      └─ BroadcastGroupsPanel
  │           ├─ GET  /api/broadcast/groups → groups + options
  │           └─ POST /api/broadcast/groups → JSON.stringify({ groups })
  │                └─ broadcast.save() → validate() → 原子写
  └─ wechat-labels ─→ WeChatLabelsPanel
         └─ GET /api/wechat/labels → read_contact_labels()
              └─ get_contact_labels() → contact_label_report()
```

### 附录.5 改名：品牌统一为 WeChatBot 与保持不变的内部标识符

项目已从上游 `webot` 二开为 **WeChatBot**，对外可见名称全部统一：

| 位置 | 改名后 |
|---|---|
| 窗口标题 | `desktop.py`：`"WeChatBot — 初始设置"` / `"WeChatBot — Dashboard"`；`desktop_mac.py`：`"WeChatBot — Dashboard"` |
| 页面 `<title>` | `ui/index.html`：`WeChatBot — Dashboard` |
| EXE 名 | `WeChatBot.exe`（`build.spec` `name='WeChatBot'`，输出 `dist/WeChatBot.exe`） |
| 安装包名 | `dist/WeChatBot-setup.exe`（`installer.nsi` `OutFile`） |
| 安装目录 | `$LOCALAPPDATA\WeChatBot`（`installer.nsi` `InstallDir`） |
| 注册表卸载键 | `Software\Microsoft\Windows\CurrentVersion\Uninstall\WeChatBot`（`REG_UNINSTALL_KEY`） |
| CI 产物名 | `dist/WeChatBot.exe` / `dist/WeChatBot-setup.exe` / `dist/WeChatBot-windows-x64.zip`（`.github/workflows/build-windows-release.yml`，仓库 `Otikes/WeChatBot`） |

**升级兼容**（`installer.nsi`）：
- 新增 `LEGACY_REG_UNINSTALL_KEY = "Software\Microsoft\Windows\CurrentVersion\Uninstall\webot"`（旧键 `\Uninstall\webot`）：`RestorePreviousInstallDir` / `RestorePreviousWebotDataDir` 在新键查不到时回读旧键，复用原安装目录与数据目录；卸载时 `DeleteRegKey` 一并清理新旧键，并删除旧 `webot.exe` 与旧快捷方式。
- `PrepareWebotExeForUpdate` 中 `taskkill /IM WeChatBot.exe /T /F` 之后**仍兼容旧 `webot.exe` 进程名**（再执行一次 `taskkill /IM webot.exe /T /F`），否则旧 EXE 会占用文件。

**以下内部标识符保持不变（刻意不随品牌改名，改名时切勿误改）**：

| 类别 | 保持不变的标识符 |
|---|---|
| 环境变量 | `WEBOT_DATA_DIR`、`WEBOT_ENV_FILE`（`src/config.py:find_env_file()`）、`WEBOT_UI_DIST`（`build.spec`） |
| 函数名 | `webot_data_path()`、`resolve_webot_data_dir()`、`get_webot_data_dir()`、`resolve_webot_storage_path()`、`_migrate_webot_data_dir()` 等 `webot_*` 名称 |
| MCP 服务器名 | `MCP_SERVER_NAME = "webot-mcp"`（`src/mcp_server/server.py`） |
| API Key 前缀 | `"webot_"`（`ensure_api_key()` / `update_settings(regenerate=True)` 生成 `webot_<token>`） |
| 飞书默认名 | `FEISHU_KNOWLEDGE_BASE_NAME` 默认值 `"webot 群聊沉淀"` |
| 数据目录 | `data/`（`BotConfig.webot_data_dir: str = "data"`，`WEBOT_DATA_DIR` 留空时为程序目录下 `data/`） |
| 图标路径 | `image/logo_assets/logo.ico`（`build.spec` `icon=`、`installer.nsi` `MUI_ICON`/`MUI_UNICON`） |

即：**对外展示名 → WeChatBot；内部代码/配置/协议标识 → 仍为 `webot`**。写进 `.env` 的键名 `WEBOT_DATA_DIR`、注册表值名 `WebotDataDir`、迁移列表 `_WEBOT_DATA_MIGRATION_ITEMS` 等也都保持原样，升级安装靠旧键兼容。

### 附录.6 智能体典型调用链示例

以下为外部 MCP 智能体使用新工具的推荐顺序（写操作务必先预览、向用户确认）：

**① 单发：`search_contacts → send_message`**

```
search_contacts({query: "张三"}) → 拿到 friends[].wxid / groups[].chat_id
  ├─ send_message({chat: <wxid>, content: "...", dry_run: true})  → 预览解析结果（ok/chat_id）
  └─ 用户确认后 send_message({chat: <wxid>, content: "..."})      → 真正发送
```

**② 按群发分组批量：`list_broadcast_groups → batch_send_messages(group)`**

```
list_broadcast_groups() → 分组名 + target_count / hidden_count / targets
  ├─ batch_send_messages({content: "...", group: "客户通知", dry_run: true})
  │     → 预览目标清单（results 逐条 chat_id、不真正发送、无间隔 sleep）
  └─ 用户确认后 batch_send_messages({content: "...", group: "客户通知"})
        → 串行发送，默认每条间隔 800ms
```

**③ `chats` 数组临时批量（不依赖预置分组）**

```
batch_send_messages({
  content: "会议提醒",
  chats: ["12345@chatroom", "wxid_abc", "产品群"],   // 群 ID / 好友 wxid / 群名混合
  interval_ms: 1000,
  dry_run: true
})
→ chats 逐项经 _resolve_chat 解析；与 group 同时传时合并去重；超过 50 个目标报错
```

**④ `dry_run` 预览语义**

```
dry_run=true
  ├─ 不调用 _running_backend()（backend=None），无需机器人启动 / 微信窗口
  ├─ 仅走 _resolve_chat → _require_chat_allowed → 记录 ok/chat_id
  ├─ 批量时不 sleep（不受 interval_ms 影响）
  └─ 返回值/日志均不含正文，只含目标清单与统计
```

`list_wechat_labels` 是独立的只读工具（`labels` 内 `members` 为 `[{"wxid","name"}]`），结果**不会**自动变成群发分组；如需按微信标签发送，智能体应把返回的 wxid 自行整理成 `chats` 数组或写入群发分组。
