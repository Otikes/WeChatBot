# WeChatBot

> 桌面微信 AI 助手：总结聊天、管理待办、回答问题，并可通过 MCP 让智能体在受控范围内代发消息。基于 Python + React + PyWebView，运行于 Windows / macOS 桌面。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11%20%7C%20macOS%20%28experimental%29-blue?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.13%2B-green?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/AI-Chat%20Completions%20%7C%20Messages-purple?style=flat-square" alt="AI Protocols" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License" />
</p>

> **二次开发声明 · 请先阅读**
>
> 本项目 **WeChatBot** 是基于 [**GuMu599/webot**](https://github.com/GuMu599/webot.git) 的**二次开发版本**，并非原项目的官方分支。
>
> - 原作者：**cancelGuMu（孤舟99）**；上游仓库：https://github.com/GuMu599/webot.git
> - 原项目采用 **MIT 协议**。本项目遵守该协议，`LICENSE` 中原有的版权行**原样保留、未作修改**，谨此感谢原作者的开源工作。
> - 当前维护仓库：**https://github.com/Otikes/WeChatBot.git** ，问题反馈与版本更新请到该仓库。
>
> 二次开发范围远不止"小修小补"：上游是一个**只处理群聊**的机器人；本项目保留其群聊核心，但**重写了数据库读取层，并全新实现了好友私聊、群聊配置、MCP 服务、媒体消息、Token 统计、生图、群发分组等模块**。逐项对照见 [与上游项目的差异](#与上游项目的差异)。

> **使用声明**
>
> 本项目**仅供学习与技术交流**，严禁用于发送垃圾广告、骚扰他人、诈骗钓鱼、批量刷屏等任何违法违规或侵扰他人的行为。
>
> 尤其注意：本项目新增了**主动群发 / 批量发送**能力，请仅在已获得接收方同意的合法场景中使用，务必控制发送频率与条数。微信对高频、重复、内容高度相似的主动发送设有风控策略，可能导致功能受限或账号被封，相关后果由使用者**自行承担**。本项目**不提供任何规避平台风控的能力**。
>
> 使用即表示你已理解并接受上述风险，原作者与二次开发维护者不承担任何责任。

---

## 它是什么

把 WeChatBot 加入微信群，它能帮忙总结聊天、管理待办、回答问题，也能在需要时主动发言。所有配置都在一个本地网页控制台完成，Windows 下双击安装包即可使用。此外，它把采集到的会话数据通过 MCP 协议开放给智能体；在二次开发版本中，还允许智能体在严格约束下代发消息。

---

## 与上游项目的差异

> 对比基准：[GuMu599/webot](https://github.com/GuMu599/webot.git) `main` 分支 `19b82a2`
> —— 这也是本仓库 git 历史中 `origin/main` 指向的上游最后一次提交。以下内容来自两棵源码树的**实际文件对比**，而非功能描述上的推测。

**一句话结论**：上游是**只处理群聊**的微信群机器人。本项目的群聊核心（消息读取、总结、待办、问答、抽签、主动发言、欢迎、飞书沉淀、群友昵称）来自上游；**其余绝大部分模块是二次开发中重新设计并实现的**，包括好友私聊、群聊配置、整套 MCP 服务、微信数据库读取层、媒体消息、Token 统计、生图，以及本次加入的群发分组与消息发送能力。

### 量化对比

| 指标 | 上游 webot | WeChatBot（二开） |
| --- | --- | --- |
| 相对上游的提交 | — | 31 次二开提交 |
| 代码改动规模 | — | 109 个文件，+27,690 / -2,127 行 |
| 新增源文件 | — | 36 个（含整套 `src/mcp_server/`、纯 Python WCDB 读取器、6 个新前端面板） |
| 前端面板组件 | 11 个 | 16 个 |
| MCP 工具 | **无** | 18 个（14 个只读查询 + 3 个消息/分组 + 1 个标签只读） |
| 微信数据库读取 | `wcdb_client.py`，依赖 `wcdb_api.dll` | `local_wcdb_client.py` + `wxdb_reader.py`，纯 Python SQLCipher 解密直读，无原生 DLL |
| 会话范围 | 仅群聊 | 群聊 + 好友私聊 |
| 主动发送 | 仅群内回复 | 群内回复 + 单发 / 批量 / 按分组群发 |

### 模块级对照

| 模块 | 上游 webot | WeChatBot | 性质 |
| --- | --- | --- | --- |
| 群聊消息读取、总结、待办、问答、抽签、主动发言、欢迎新人、飞书沉淀 | 有 | 沿用并增强 | 继承 |
| 群友昵称 | `NicknameEditor.jsx` | `GroupChatPanel.jsx` | **重写**（上游组件已删除） |
| 好友私聊（读取 / 自动回复 / 好友勾选 / 面板） | **无** | `FriendChatPanel.jsx` + 路由与选择逻辑 | **全新** |
| MCP 服务（协议、鉴权、数据范围、历史直读、工具集） | **无** | `src/mcp_server/` 全套 | **全新** |
| 微信 4.x 本地库读取 | `wcdb_api.dll` 封装 | 内存取密钥 + 逐页解密，纯 Python 只读 | **重写** |
| 媒体消息（图片 / 语音 / 转发 / 引用解密） | **无** | `media.py` / `dat2img.py` / `forward.py` | **全新** |
| 生图（文生图模型 + 意图识别） | **无** | `src/imagegen/` | **全新** |
| Token 用量统计 | **无** | `token_stats.py` + `TokenStats.jsx` | **全新** |
| AI 后端 | DeepSeek / Claude 固定后端 | 增加 Chat Completions / Messages 通用协议 | 扩展 |
| 群发分组 + MCP 消息发送工具 | **无** | 系统分组 + `send_message` / `batch_send_messages` / `list_broadcast_groups` | **全新** |
| 微信通讯录标签（只读） | **无** | `contact.extra_buffer` protobuf 解析标签归属 + 成员昵称 + 只读视图 | **全新**，与群发分组互不联动 |
| 品牌 / 图标 / 安装包 / CI 产物名 | webot | WeChatBot | 全链路改名，保留旧版升级兼容 |

### 控制台菜单对照

| 上游 webot | WeChatBot |
| --- | --- |
| 运行状态、系统配置、功能开关、群聊待办、群友昵称、运行日志 | 运行状态、**Token 统计**、**MCP 服务**、系统配置（含**群发分组**）、功能开关、**好友私聊**、**通讯录标签**、**群聊配置**、群聊待办、运行日志 |

## 能做什么

### 群聊核心功能（来自上游）

1. **群聊待办**：@机器人 说 `记一下 周五聚餐` 新建待办，全群共享、按群独立；支持 `查看待办`、`搞定 3`、`删掉 2`、`恢复待办 1`（恢复仅管理员）。控制台可开关功能、选择启用群、修改触发词、设置条数上限与自动清理。
2. **聊天总结**：说 `总结一下`（也支持 `前面说了什么`、`发生了什么`、`summarize`），机器人整理指定时间窗内的聊天要点，默认回看 8 小时，触发词与时间窗均可自定义。
3. **对话问答**：@机器人 提问，结合最近群聊上下文作答，而不是凭空猜测。
4. **群友昵称**：控制台「群友昵称」按群列出成员并取易认的别名；管理员也可在群里发送 `@机器人 改名 wxid_xxx = 张三`。
5. **趣味抽签**：说 `抽签` 随机抽一支运势签；签文、等级、概率、表情在「功能开关 → 趣味抽签」自定义。
6. **主动发言**：群聊达到一定热度时机器人自行插话，活跃阈值在「功能开关 → 主动发言」调整。
7. **欢迎新人**：有人入群时自动发送欢迎词，可配置多条模板、按群套用。
8. **飞书沉淀**：把讨论按摘要 / 待办 / 需求 / 日常记录整理进飞书表格；填入 App ID 与 App Secret 开启自动同步，也可在群里说 `同步到飞书` 立即沉淀。

### 二次开发功能（重写或全新实现）

- **好友私聊**：上游完全不处理好友会话，本项目的私聊读取、自动回复、好友勾选与 `FriendChatPanel.jsx` 为全新实现。
- **群聊配置**：用 `GroupChatPanel.jsx` 重写了上游的 `NicknameEditor.jsx`。
- **MCP 服务**：上游没有 MCP；本项目的 `src/mcp_server/` 为全新实现，以标准 MCP 协议把群聊、群成员、好友与消息开放给智能体，详见 [MCP 服务](#mcp-服务)。
- **数据库直读 / 媒体消息 / Token 统计 / 生图**：均为上游不存在的模块，详见对比表。
- [群发分组](#群发分组)：系统自定义、好友与群聊可混编的发送分组。
- [MCP 消息发送](#mcp-消息发送)：三个受控写工具，让智能体单发 / 批量发消息。
- [微信通讯录标签（只读）](#微信通讯录标签只读)：只读查看微信自带通讯录标签及成员。

---

## 群发分组

WeChatBot 提供一套**系统内自定义分组**，用于组织消息发送目标。

- 同一个分组可以**同时包含好友和群聊**，不区分会话类型。
- 分组保存在数据目录的 `broadcast_groups.json`，随 WeChatBot 自身数据一起存放，**不会写入微信**。
- 在控制台 **「系统配置 → 群发分组」** 中增删改查、为分组添加或移除目标。
- 分组名可作为 MCP 工具 `batch_send_messages` 的 `group` 参数，配合 `list_broadcast_groups` 查询。

> **与微信通讯录标签完全独立**
> 这是 WeChatBot **自己的分组**，与微信自带的「通讯录标签」是两套互不相干的数据：**互不导入、互不联动、互不覆盖**。在这里新建或修改分组不会改变微信里的任何标签；微信里标签的变化也不会同步到这里。微信标签仅提供只读查看（见下节），不会自动变成群发分组。

---

## MCP 消息发送

二次开发版本在原有只读工具之外，新增三个**写工具**，让智能体能够代发消息。三者共同的前提与约束：

- **机器人已启动**，且**微信窗口可见**（发送依赖界面操作，微信最小化时无法发送）；
- **受 MCP 数据范围约束**：目标会话必须在「MCP 服务 → 数据范围」允许范围内，范围外目标会被拒绝；
- **串行发送**：逐条依次发送、不并发，避免短时间集中操作。

### 工具一览

| 工具 | 作用 | 参数 |
| --- | --- | --- |
| `send_message` | 单发一条 | `chat`：群名 / 群 ID / 好友昵称 / 备注 / wxid；`content`：消息正文 |
| `batch_send_messages` | 批量发送 | `content`：消息正文；`chats`：目标数组（临时列表）**或** `group`：分组名（二选一）；`dry_run`：可选，为 `true` 时只预览与校验、不实际发送；返回**逐条结果** |
| `list_broadcast_groups` | 列出系统内所有群发分组及其成员 | 无 |

`chat` 支持上述多种标识；智能体可先用 `search_contacts` 把昵称解析成可用目标，再传入 `chat`。

### 调用示例（JSON 参数）

以下为 MCP `tools/call` 的 `name` + `arguments` 形式，块内均为合法 JSON。

**1) 单发**

```json
{
  "name": "send_message",
  "arguments": { "chat": "产品讨论群", "content": "周会改到今天下午三点，记得参加。" }
}
```

**2) 按分组批量（先 dry_run 预览，确认后再正式发送）**

```json
{
  "name": "batch_send_messages",
  "arguments": { "group": "客户通知", "content": "系统将于今晚 23:00 维护。", "dry_run": true }
}
```

**3) 临时目标数组批量**

```json
{
  "name": "batch_send_messages",
  "arguments": {
    "chats": ["产品讨论群", "张三", "wxid_abc123"],
    "content": "本周五聚餐，能来的回个 1。"
  }
}
```

**4) 列出可用分组**

```json
{
  "name": "list_broadcast_groups",
  "arguments": {}
}
```

### 典型调用链

| 场景 | 调用链 |
| --- | --- |
| 给标识尚不明确的人 / 群发一条 | `search_contacts`（按关键词找目标）→ 取回 `chat` → `send_message` |
| 按预设分组群发 | `list_broadcast_groups` → 选定分组 → `batch_send_messages(group=..., dry_run=true)` 预览 → 去掉 `dry_run` 正式发送 |
| 临时凑一批目标群发 | 直接 `batch_send_messages(chats=[...])`（同样建议先 `dry_run`） |

建议智能体在**任何实际发送前**，先用 `dry_run` 给出将要发送的目标与条数，并向用户确认。

### 安全约束

| 约束 | 说明 |
| --- | --- |
| 条数上限 | 单次批量的目标数量有上限，超限直接拒绝，防止误操作扩散 |
| 内容长度 | 单条 `content` 有长度上限，超长内容会被拒绝 |
| 不记录正文 | 运行日志只记录目标、时间与成功 / 失败，**不落盘消息正文**，避免敏感内容留存 |
| 写操作需确认 | 发送属于写操作，智能体应先展示计划并取得用户确认；`dry_run` 用于预演，不应被自动跳过 |
| 范围与鉴权 | 目标必须在 MCP 数据范围内；服务仅监听本机、需 API Key 鉴权（见 [MCP 服务](#mcp-服务)） |

---

## 微信通讯录标签（只读）

WeChatBot 可以**读取微信自带的通讯录标签及其成员**，方便盘点，但与群发分组彼此独立。

- 底层读取 `contact.db` 的 `contact_label` 标签定义，并从 `contact.extra_buffer`（protobuf）里解析每位好友的标签归属。**微信 4.x 没有独立的「标签 ↔ 联系人」关联表**，标签 id 以逗号串存在该 protobuf 的 field 30；解析不写死字段号，会按已知标签 id 自动识别，旧版本则回退到关联表探测。成员昵称来自 `contact` 表的备注/昵称，并与本地好友昵称缓存合并。
- 当未登录、密钥失效或库不可读时**静默降级**——返回空结果或提示，不报错、不影响机器人主流程。
- 查询方式：`GET /api/wechat/labels`，或 MCP 工具 `list_wechat_labels`。返回的每个标签带 `member_count` 与 `members: [{"wxid", "name"}]`。
- **只读**：仅用于查看，**不会导入到群发分组**，也不会把微信标签同步成系统分组；两者互不联动（见 [群发分组](#群发分组)）。
- **局限**：微信 PC 端的通讯录标签主要针对好友，**群标签通常没有对应数据**，因此这里一般只能读到好友标签。

---

## MCP 服务

WeChatBot 把已采集的群聊、群成员、好友与消息，通过标准 [MCP](https://modelcontextprotocol.io) 协议暴露给 Codex、Trae、Claude Code 等智能体，可用于写周报、群活跃分析、联系人盘点、客户跟进等。二次开发版本另提供上文 [MCP 消息发送](#mcp-消息发送) 的三个写工具。

### 接入

1. 打开控制台左侧 **「MCP 服务」**，点「一键复制全部配置」，可拿到请求地址（默认 `http://127.0.0.1:7327/mcp`）、API Key 与各客户端配置。
2. 粘贴到 Trae / Codex / Claude Code 等智能体的 MCP 配置中；仅支持 stdio 的客户端（如 Claude Desktop）用面板里的 `mcp-remote` 桥接配置。
3. 让智能体先调用 `get_data_overview` 了解数据范围，再用 `find_new_senders` 追踪新成员、`get_contact_profile` 查看联系人画像，配合 `list_groups`、`list_group_members`、`list_friends`、`search_contacts`、`search_messages`、`get_group_activity` 等工具做分析。

只要控制台程序在运行，**不启动微信机器人**也能查询数据。

### 历史消息来源

`get_messages`、`search_messages`（指定 `chat` 时）和 `get_member_activity` 默认优先读取**微信本地数据库的完整历史**，翻页可一直读到微信保留的最早消息；当微信未登录、密钥失效或本地库不可用时，自动回退到机器人采集的 `messages.db`，返回中的 `source` / `note` 会标明实际数据源。可用环境变量 `MCP_HISTORY_SOURCE=messages` 强制只用采集库。面板里可「测试连接」，并提供 Trae / 通用 JSON、Claude Desktop、Codex TOML、旧版 SSE 和 curl 五种配置示例。

### 数据范围

在 **「MCP 服务 → 数据范围」** 中可分别按「群聊 / 好友」Tab 勾选允许智能体读取的会话，默认全部可见；关闭「全部可见」后，未勾选的群聊 / 好友不会出现在**任何**工具结果中（搜索、统计、总览同样被过滤），保存后智能体下次调用立即生效。对应 `.env` 的 `MCP_GROUPS` / `MCP_FRIENDS`，留空或 `*` 为全部，`none` 为全部禁止。该范围同样约束上文的消息发送工具。

### 安全与密钥

- MCP 只监听本机、只接受回环 Host / Origin，请求需 **API Key** 鉴权（`Authorization: Bearer`、`X-API-Key`，或旧版 SSE 的 `?key=`）；外部网页无法读取控制台里的密钥。
- 若密钥泄露，在「MCP 服务」面板点「轮换密钥」即可立即生成一组新随机密钥，旧密钥马上失效，新密钥自动复制到剪贴板。
- 通过隧道 / 反向代理访问时，需在 `.env` 配置 `MCP_ALLOWED_HOSTS` 追加可信主机名。

---

## 控制台一览

打开 EXE 后自动弹出网页控制台，左侧菜单：

| 菜单 | 用途 |
| --- | --- |
| 运行状态 | 查看机器人在线状态、消息处理量 |
| 系统配置 | AI 协议、请求地址、Key、机器人名字、数据目录、测试提示词、**群发分组** |
| 功能开关 | 各项功能的开关与参数 |
| 群聊待办 | 待办配置 + 所有群的待办列表 |
| 群友昵称 | 给群成员取别名 |
| 运行日志 | 查看运行记录 |
| MCP 服务 | 查看请求地址与密钥、数据范围、接入智能体 |

所有配置改完点「保存配置」，重启机器人生效。

---

## 安装

### Windows（推荐）

1. 从 [Releases](https://github.com/Otikes/WeChatBot/releases) 下载 `WeChatBot-setup.exe`，双击安装。
2. 安装向导可分别选择「安装目录」和「WeChatBot 数据目录」；数据目录只保存 WeChatBot 自生成的数据库、日志、缓存与模板，**不会移动微信聊天记录**。
3. 或下载 `WeChatBot.exe` 免安装直接运行。
4. 首次打开会弹出配置向导，按提示完成即可。

前提：电脑已登录微信；需要机器人进入的群，请先在群聊右上角 `···` 开启「添加到通讯录」。

### macOS（实验）

```bash
git clone https://github.com/Otikes/WeChatBot.git
cd WeChatBot
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-macos.txt
cd ui && npm install && npm run build && cd ..
python desktop_mac.py
```

需在「系统设置 → 隐私与安全性」给终端授权「辅助功能」权限。

两个实验后端可选：`WECHAT_BACKEND=mac_ui`（界面自动化）、`WECHAT_BACKEND=mac_hybrid`（WeFlow 直读，**不需要额外启动消息读取服务**）。可用 `tools/macos/weflow_setup.py diagnose` 做环境检查；密钥通过 `tools/macos/weflow_setup.py extract-keys` 提取、`tools/macos/weflow_setup.py extract-keys-restart-hook` 通过重启 Hook 提取，或用 `tools/macos/weflow_setup.py import-keys` 导入，写入 `all_keys.json`。

### 从源码运行（Windows）

```bash
git clone https://github.com/Otikes/WeChatBot.git
cd WeChatBot
pip install -r requirements.txt
cd ui && npm install && npm run build && cd ..
python desktop.py
```

环境要求：Python **3.13+**，以及用于构建前端的 Node.js / npm。

---

## 配置

所有设置都在控制台里直接改，不需要手动编辑文件，保存后重启机器人生效。

在「系统配置 → AI 协议配置」选择协议并填写请求地址与 Key，点「获取模型」后从列表选一个当前模型。Chat Completions 协议请求 `/v1/models`、聊天走 `/v1/chat/completions`；Messages 协议请求 `/v1/models`、聊天走 `/v1/messages`。本地无鉴权的 Chat Completions 兼容服务可不填 Key，请求地址可粘 `.../v1`、`.../v1/chat/completions` 或 `.../v1/models`，保存时会自动纠正。

> 数据目录对应的环境变量键名为 `WEBOT_DATA_DIR`（历史遗留的**内部键名**，非品牌名，沿用上游未改动）；在控制台「系统配置」里设置即可，一般无需手动配置。

---

## 常见问题

**需要装什么？**
下载 EXE 双击即可，无需额外环境。

**会被封号吗？**
正常使用目前没有已知案例，但请自行评估风险。

**群发会被封号吗？**（新增能力相关）
群发属于高频主动发送，微信对**批量、重复、内容高度相似**的消息有风控策略，存在功能受限乃至封号的风险。请只向已获同意的对象发送、控制频率与单次条数、避免短时间大量重复内容，并先用 `dry_run` 预览。本项目**不提供任何规避风控的能力**，也不对由此产生的后果负责，请谨慎使用、风险自负。

**支持哪些 AI？费用多少？**
支持 Chat Completions 与 Messages 两类协议。只要服务能通过请求地址与 Key 返回模型列表即可选用；费用取决于你接入的模型服务。

**微信能最小化吗？**
读消息不受影响；**发消息时微信窗口需要可见**（含 MCP 消息发送工具）。

**支持多群吗？**
支持，默认监控所有群，也可指定。

---

## 许可证与致谢

本项目基于 [**GuMu599/webot**](https://github.com/GuMu599/webot.git) 二次开发，采用 **MIT 协议**。

- 原作者 **cancelGuMu（孤舟99）** 的版权声明保留于 `LICENSE`，**原样未改**，谨此致谢其开源工作。
- 二次开发部分及后续维护：**[Otikes/WeChatBot](https://github.com/Otikes/WeChatBot.git)**。
- 完整许可文本见仓库 `LICENSE`。

---

<p align="center">
  <sub>基于 <a href="https://github.com/GuMu599/webot.git">webot</a>（原作者 <a href="https://github.com/cancelGuMu">cancelGuMu / 孤舟99</a>）二次开发 · 由 <a href="https://github.com/Otikes/WeChatBot.git">Otikes/WeChatBot</a> 维护 · MIT</sub>
</p>
