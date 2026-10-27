# Codex Mission Manager · 任务管家

面向 macOS 和 Windows 的原生 Codex 任务管理应用。在额度不足时暂停已授权任务，核验额度恢复后续接，并支持一次性预约指令、即时发送及操作记录。

A native macOS and Windows companion for Codex. Pause authorized tasks when quota runs low, resume after verified recovery, schedule one-time instructions, and inspect delivery records.

**V0.3.0 公开预览 / Public preview.** [发行下载 / Downloads](https://github.com/Dddysun/Codex-Mission-Manager/releases) · [使用指南 / User guide](docs/USER_GUIDE.md) · [V0.3.0 发行说明 / Release notes](docs/releases/0.3.0.md)

## 中文

### 能做什么

- 原生聊天列表显示 Codex 聊天、当前状态和最近执行阶段；两列卡片集中呈现任务信息、自动控制和预约指令。
- 为指定聊天启用自动控制，在可用额度不足时暂停符合条件的任务，恢复后核对账号、原会话和人工接管状态再续做。
- 安排一次性“额度恢复后执行”指令，或使用“立刻执行”发送当前指令；发送结果单独记录。
- 按服务实际返回的数据展示额度窗口、剩余额度、刷新时间和账号信息，不根据订阅名称推断固定额度。
- 编辑六项运行规则，选择绿、蓝、紫、鹅蛋黄主题色，使用中英文及跟随系统、浅色、深色外观。
- 若服务提供重置权益，展示数量和详情；权益仅供查看，不自动兑换。

### 下载与安装

在 [Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases) 选择 V0.3.0 预览发行。预览标签形式为 `v0.3.0-preview.N`；请以该发行页的文件和说明为准。

- **Mac：**Apple Silicon、macOS 14 或更新版本。下载 `Codex-Mission-Manager-0.3.0-arm64-preview.dmg`，将应用拖到 Applications。
- **Windows：**Windows 10 build 19041 或更新版本、x64、.NET Framework 4.8 或更新版本。下载 `Codex-Mission-Manager-0.3.0-windows-x64-setup.exe`，安装到当前用户；另提供便携 ZIP。
- 两种安装包都包含后端和独立 Python 运行环境，使用者无需另装 Python、Node.js 或开发工具。
- 需要自行安装、登录兼容的官方 Codex 桌面客户端。发行包不包含原客户端、凭据或个人聊天数据。

新安装默认暂停全局自动控制。先核对账号和聊天，再开启全局及所需聊天的自动控制。关闭主窗口后继续在菜单栏或系统托盘运行；通过“退出”停止管家后台。

### 预览版边界

客户端控制依赖版本敏感的本机通信适配，并非稳定公开的客户端控制 API。未知客户端版本会停止控制；连接成功也不代表完整暂停、恢复和发送流程已通过验收。

当前 Mac 预览为本机临时签名、未经过 Apple 公证；Windows 预览未签名。系统可能阻止打开。预览版不提供无外屏合盖运行保证，Mac 合盖辅助服务暂未开放；防止空闲睡眠不等于阻止手动睡眠或合盖睡眠。完整实机验收及待验证项目见 [发行说明](docs/releases/0.3.0.md)。

## English

### Features

- Native Codex chat list with current status and recent execution stage. Two-column cards group task details, automatic control, and scheduled instructions.
- Per-chat authorization for automatic pause and recovery. Resumption rechecks quota, account, the original chat, and manual intervention.
- One-time instructions after quota recovery, plus **Run now** with separate delivery records.
- Quota windows, remaining allowance, reset times, and account details from service data. Subscription names do not determine assumed limits.
- Six editable operating rules; green, blue, purple, and egg-yellow accents; Chinese and English; system, light, and dark appearance.
- Read-only reset-credit counts and details when supplied by the service. Credits are never redeemed automatically.

### Install

Choose a V0.3.0 preview from [Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases). Preview tags use `v0.3.0-preview.N`; the selected release page is the source of truth for its files and limitations.

- **Mac:** Apple Silicon, macOS 14 or later. Download `Codex-Mission-Manager-0.3.0-arm64-preview.dmg` and drag the app to Applications.
- **Windows:** Windows 10 build 19041 or later, x64, .NET Framework 4.8 or later. Use `Codex-Mission-Manager-0.3.0-windows-x64-setup.exe` for a current-user installation, or extract the portable ZIP.
- Both distributions bundle the backend and an isolated Python runtime. Users do not need Python, Node.js, or development tools.
- Install a compatible official Codex desktop client and sign in separately. Client software, credentials, and personal chat data are not included.

Global automatic control starts paused on a new installation. Verify the account and chats before enabling global and per-chat control. Closing the main window leaves Mission Manager running in the menu bar or system tray. **Quit** stops its background process.

### Preview limitations

Live-client control uses a version-sensitive local adapter, rather than a stable public client-control API. Unknown client versions block control. A successful connection does not establish that live pause, recovery, and delivery have passed acceptance testing.

The Mac preview is ad-hoc signed and not Apple-notarized; the Windows preview is unsigned. The operating system may block opening it. Closed-lid operation without an external display is not guaranteed; the Mac closed-lid helper is unavailable in this preview. Idle-sleep prevention does not prevent manual sleep or guarantee operation with the lid closed. See [release notes](docs/releases/0.3.0.md) for verified scope and outstanding checks.

## Project information / 项目信息

- [User guide / 使用指南](docs/USER_GUIDE.md)
- [Build from source / 从源码构建](docs/BUILDING.md)
- [Release process / 发行流程](docs/RELEASE_PROCESS.md)
- [Changelog / 版本记录](CHANGELOG.md)

The Mac interface uses SwiftUI and AppKit; Windows uses WPF with a native system tray. Neither embeds a web interface. The backend uses the Python standard library and stores local state in SQLite. Configuration and task records stay in the user's application-data directory and are excluded from source and release packages.

Mac 界面使用 SwiftUI / AppKit，Windows 使用 WPF 和原生托盘，均不内嵌网页。后端使用 Python 标准库和 SQLite；用户配置及任务记录位于本机应用数据目录，不随源码或安装包分发。

Scheduling rules include adaptations from [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor). Notices and bundled-runtime licenses are retained in [third-party](third-party/). This is an independent project and is not affiliated with OpenAI.

部分调度规则改编自 [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor)，相关声明与运行环境许可证保留于 [third-party](third-party/)。本项目独立开发，与 OpenAI 无隶属关系。
