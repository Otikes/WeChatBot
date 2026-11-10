# webot

> 微信群的 AI 助手 —— 帮你总结聊天、管理待办、回答问题，像多了一个会做笔记的群友。

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11%20%7C%20macOS-blue?style=flat-square&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/python-3.13%2B-green?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/AI-Chat%20Completions%20%7C%20Messages-purple?style=flat-square" alt="AI Protocols" />
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License" />
</p>

> ## 使用声明
> 
> 本项目仅供学习交流使用。严禁用于发送垃圾信息、骚扰他人、诈骗钓鱼等违法违规行为。使用者自行承担一切后果与风险。

---

## 它是什么

把 webot 加入你的微信群，它会：

- **总结聊天记录**：说一句「总结一下」，立刻告诉你在忙的时候群里聊了什么。
- **管理待办事项**：@机器人 说「记一下 周五聚餐」，全群共享的待办清单就多了一条。完成了就「搞定」它，不想看了就「删掉」。
- **回答你的问题**：@机器人 问任何问题，它会结合群聊上下文回答你。
- **偶尔自己冒泡**：群聊热闹的时候，它也会插话接梗，像个普通群友。

所有操作都在一个网页控制台里完成，双击 EXE 就能用。

---

## 能做什么

### 1. 群聊待办

@机器人 说句话就能新建一条待办，全群都能看到。每个群独立管理，互不影响。

**怎么用**

群里直接 @机器人 说：
- `记一下 周五聚餐` —— 添加一条待办
- `查看待办` —— 看看还有哪些没做
- `搞定 3` —— 把第 3 项标记完成
- `删掉 2` —— 把第 2 项放进回收站
- `恢复待办 1` —— 从回收站捞回来（仅群管理员）

打开控制台的「群聊待办」页面，可以：
- 开关这个功能、选择哪些群启用
- 修改触发词（比如把「记一下」改成「备忘」）
- 设置每个群最多存多少条、多久后自动清理
- 查看所有群的待办列表，搜索、筛选、操作

### 2. 聊天总结

忙了几个小时没看群？直接说一句「总结一下」，机器人把刚才的聊天整理好发给你：谁说了什么、讨论了什么话题。

**怎么用**

群里直接说 `总结一下` 就行。也可以说 `前面说了什么`、`发生了什么`、`summarize`。触发词可以在控制台自定义。

控制台里可以调整：总结往前看多久（默认 8 小时）、用哪些词触发。

### 3. 对话问答

@机器人 然后问问题，它会结合最近的群聊内容来回答，而不是凭空瞎猜。

**怎么用**

- `@机器人 这几个模型协议怎么选？`
- `@机器人 刚才他们说的那个餐厅地址是什么？`

### 4. 群友昵称

群里的人默认显示的是微信号（wxid 开头的一串），很难认。控制台的「群友昵称」页面列出了每个群的全部成员，你可以给每个人取一个容易认的名字。

**怎么用**

打开控制台 → 群友昵称 → 选择群聊 → 在对应的人旁边填上你想叫的名字。

也可以在群里直接发送命令（仅管理员）：`@机器人 改名 wxid_xxx = 张三`

### 5. 趣味抽签

群里说「抽签」，机器人随机抽一支运势签（大吉到凶），配一句吐槽。

**怎么用**

群里直接说 `抽签`。签文内容、等级、概率、emoji 都可以在控制台的「功能开关 → 趣味抽签」里自定义。

### 6. 主动发言

不用 @它，群聊热闹到一定程度时，机器人会自己插话。

**怎么用**

在控制台的「功能开关 → 主动发言」里打开。可以调整它在多热闹的群里才开口（安静时闭嘴，热闹时活跃）。

### 7. 欢迎新人

有人刚进群，机器人会自动发一条欢迎消息。

**怎么用**

在控制台的「功能开关 → 欢迎新人」里打开。可以写多条欢迎词模板，不同的群用不同的模板。

### 8. 飞书沉淀

把群聊里的讨论自动整理到飞书表格里，按摘要、待办、需求、日常记录分类存好。

**怎么用**

在控制台的「功能开关 → 飞书同步」里填入飞书应用的 App ID 和 App Secret，开启后群聊内容会自动同步。也可以手动在群里说 `同步到飞书` 立即沉淀。

---

### 9. MCP 服务

把已采集的群聊、群成员、好友与消息通过标准 [MCP](https://modelcontextprotocol.io) 协议暴露给 Codex、Trae 等智能体，可用于写周报、群活跃分析、联系人盘点、客户跟进等。

**怎么用**

1. 打开控制台左侧「MCP 服务」，点「一键复制全部配置」，即可拿到请求地址（默认 `http://127.0.0.1:7327/mcp`）、API Key 和各客户端配置
2. 直接粘贴到 Trae / Codex / Claude Code 等智能体的 MCP 配置中；仅支持 stdio 的客户端（如 Claude Desktop）用面板里的 `mcp-remote` 桥接配置
3. 让智能体先调用 `get_data_overview` 了解数据范围，再用 `find_new_senders` 追踪新成员、`get_contact_profile` 查看联系人画像，配合 `list_groups`、`list_group_members`、`list_friends`、`search_messages`、`get_group_activity` 等工具做周报汇总、运营复盘或客户跟进

只要控制台程序在运行，**不需要启动微信机器人**也能查询数据。`get_messages`、`search_messages`（指定 `chat` 时）和 `get_member_activity` 默认优先读取**微信本地数据库的完整历史**，翻页可以一直读到微信保留的最早消息；当微信未登录、密钥失效或本地库不可用时，会自动回退到机器人采集的 `messages.db`，返回里的 `source` / `note` 会标明实际数据源。可用环境变量 `MCP_HISTORY_SOURCE=messages` 强制只用采集库。面板里可以直接「测试连接」，也提供 Trae / 通用 JSON、Claude Desktop、Codex TOML、旧版 SSE 和 curl 五种配置示例。

**数据范围**：在「MCP 服务 → 数据范围」中可分别按「群聊 / 好友」Tab 勾选允许智能体读取的会话，默认全部可见；关闭「全部可见」后，未勾选的群聊/好友不会出现在任何工具结果中（搜索、统计、总览同样会被过滤），保存后智能体下次调用立即生效。对应 `.env` 的 `MCP_GROUPS` / `MCP_FRIENDS`，留空或 `*` 为全部，`none` 为全部禁止。

安全默认值：MCP 只监听本机、只接受回环 Host/Origin，请求需 API Key；外部网页无法读取控制台里的密钥。若密钥泄露，在「MCP 服务」面板点「轮换密钥」即可立即生成一组新的随机密钥，旧密钥马上失效，新密钥会自动复制到剪贴板。通过隧道/反向代理访问时，需要在 `.env` 配置 `MCP_ALLOWED_HOSTS`。

---

## 控制台一览

打开 EXE 后会自动弹出网页控制台，左侧菜单依次是：

- **运行状态**：看机器人在不在线、处理了多少消息
- **系统配置**：设置 AI 协议、请求地址、Key、机器人名字、数据目录、测试提示词
- **功能开关**：各项功能的开关和参数调整
- **群聊待办**：待办功能配置 + 所有群的待办列表
- **群友昵称**：给群成员取别名
- **运行日志**：查看机器人运行记录
- **MCP 服务**：查看请求地址与密钥，接入 Codex、Trae 等智能体

所有配置改完后点「保存配置」，重启机器人就生效。

---

## 安装

### Windows（推荐）

1. 从 [Releases](https://github.com/cancelGuMu/webot/releases) 下载 `webot-setup.exe`，双击安装
2. 安装向导里可以分别选择「安装目录」和「webot 数据目录」；后者只保存 webot 自己生成的数据库、日志、缓存和模板，不会移动微信聊天记录
3. 或者下载 `webot.exe`，免安装直接双击运行
4. 首次打开会弹出配置向导，跟着走完就行

前提：电脑上已登录微信，想让机器人进的群需要先添加到通讯录（群聊右上角 `···` → 开启「添加到通讯录」）。

### macOS（实验）

```bash
git clone https://github.com/cancelGuMu/webot.git
cd webot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-macos.txt
cd ui && npm install && npm run build && cd ..
python desktop_mac.py
```

需要在系统设置中给终端授权「辅助功能」权限。

macOS 有两个实验后端可选：`WECHAT_BACKEND=mac_ui` 使用界面自动化；`WECHAT_BACKEND=mac_hybrid` 使用 WeFlow 直读，不需要额外启动消息读取服务。可用 `tools/macos/weflow_setup.py diagnose` 做环境检查，密钥可通过 `tools/macos/weflow_setup.py extract-keys`、`tools/macos/weflow_setup.py extract-keys-restart-hook` 提取并写入 `all_keys.json`，也可用 `tools/macos/weflow_setup.py import-keys` 导入。

### 从源码运行（Windows）

```bash
git clone https://github.com/cancelGuMu/webot.git
cd webot
pip install -r requirements.txt
cd ui && npm install && npm run build && cd ..
python desktop.py
```

---

## 配置

所有设置都在控制台里直接改，不需要手动编辑文件。保存后重启机器人即可生效。

在「系统配置 → AI 协议配置」选择接口协议，填写请求地址和 Key 后点击「获取模型」，再从返回列表里选择一个模型作为当前使用模型。Chat Completions 协议会请求 `/v1/models`，实际聊天走 `/v1/chat/completions`；Messages 协议会请求 `/v1/models`，实际聊天走 `/v1/messages`。本地无鉴权的 Chat Completions 兼容服务可以不填 Key，请求地址可粘 `.../v1`、`.../v1/chat/completions` 或 `.../v1/models`，保存时会自动纠正。

---

## 常见问题

**需要装什么？**
下载 EXE 双击就行，什么都不用装。

**会被封号吗？**
目前没有已知案例，但请自行评估风险。

**支持哪些 AI？费用多少？**
支持 Chat Completions 和 Messages 两类主流协议。只要服务能通过请求地址和 Key 获取模型列表，就可以选择返回的模型来使用；费用取决于你接入的模型服务。

**微信能最小化吗？**
读消息不受影响，发消息时微信窗口需要可见。

**支持多群吗？**
支持，默认监控所有群，也可以指定。

---

## 许可证

MIT © [cancelGuMu](https://github.com/cancelGuMu)

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/cancelGuMu">孤舟99</a></sub>
</p>
