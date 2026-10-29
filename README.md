# TokenMax · TOKEN榨汁机

额度不足时暂停，恢复后继续。面向 macOS 和 Windows 的原生 Codex 任务管理应用。

Pause when quota is low. Continue when it returns. A native Codex companion for macOS and Windows.

**源码版本 V0.4.2 / Source version V0.4.2** · [下载 / Downloads](https://github.com/Dddysun/Codex-Mission-Manager/releases) · [使用指南 / User guide](docs/USER_GUIDE.md) · [更新说明 / Release notes](docs/releases/0.4.2.md)

0.4.2 集成资源完整性、通信期限、并发许可和输入边界修复，以及十种内核放电与 2 秒呼吸 Logo。下载时核对发布标签、构建号和校验文件。 / 0.4.2 combines resource-integrity, deadline, permission-concurrency and input-boundary fixes with ten core-origin discharges and two-second bolt breathing. Verify the release tag, build number and checksums. [0.4.2 notes](docs/releases/0.4.2.md)

## 中文

- 按聊天授权暂停与续接，支持恢复后执行一次性指令及“立刻执行”。
- 显示额度、刷新时间、执行阶段和操作记录；规则可调整。
- “来一杯 / Juice Bar”集中管理聊天与指令。
- “开始榨汁”启用全局调度，“榨汁状态”开关选择需要管理的聊天。
- TOKEN榨汁机 Logo：停用时灰色静止，启用时金色闪电与轻量动画。支持减少动态效果。
- 中英文、深浅外观，以及绿、蓝、紫、鹅蛋黄主题色。

### 安装

从 [Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases) 选择已发布的预览标签，并核对 0.4.2 对应的构建号：

- **Mac：**`TokenMax-0.4.2-arm64-preview.dmg`。Apple Silicon，macOS 14+。
- **Windows：**`TokenMax-0.4.2-windows-x64-setup.exe`，另有便携 ZIP。Windows 10 build 19041+、x64、.NET Framework 4.8+。

安装包包含后端和 Python 环境。另需安装并登录兼容的官方 Codex 桌面客户端。首次使用先核对账号与聊天，再点击“开始榨汁”。关闭窗口后继续后台运行；“退出”停止应用。

原名为“任务管家 / Codex Mission Manager”。升级保留数据和设置。Mac 升级前退出旧版，将 `TokenMax.app` 拖入 Applications，再移除旧名应用，勿同时运行两份。Windows 安装器沿用原安装目录。

### 预览限制

Mac 预览为临时签名、未公证；Windows 预览未签名。客户端控制依赖版本敏感的本机适配；未知版本暂停控制。无外屏合盖运行不作保证。真实发送、锁屏和电源行为需单独实测，详见[发行说明](docs/releases/0.4.2.md)。

## English

- Authorize chats for quota-aware pause and resume. Schedule one-time instructions or use **Run now**.
- View quota, reset times, task progress, and activity. Adjust operating rules.
- **Juice Bar** brings chats and instructions together.
- **Start Juicing** enables scheduling; each chat's **Juicing** switch selects managed chats.
- The new juicer logo is gray and static while stopped, with a gold bolt and subtle motion while enabled. Reduced motion is supported.
- Chinese/English, light/dark/system appearance, and four accent colors.

### Install

Choose a published preview tag from [Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases). Check the build number associated with 0.4.2:

- **Mac:** `TokenMax-0.4.2-arm64-preview.dmg`. Apple Silicon, macOS 14+.
- **Windows:** `TokenMax-0.4.2-windows-x64-setup.exe`, or the portable ZIP. Windows 10 build 19041+, x64, .NET Framework 4.8+.

The backend and Python runtime are bundled. Install a compatible official Codex desktop client and sign in separately. Verify the account and chats before selecting **Start Juicing**. Closing the window keeps the app running; **Quit** stops it.

Previously named Codex Mission Manager. Settings and history are retained. On Mac, quit the old version, install `TokenMax.app`, then remove the old-named app; do not run both. The Windows installer retains the existing installation directory.

### Preview limits

Mac builds are ad-hoc signed and unnotarized; Windows builds are unsigned. Live control uses a version-sensitive local adapter; unknown versions block control. Closed-lid operation is not guaranteed. Live delivery, lock, and power behavior require separate testing; see [release notes](docs/releases/0.4.2.md).

## Project / 项目

[2026-10-29 架构审查与验收 / Architecture review and validation](docs/reviews/2026-10-29-architecture.md)

[正确性、可读性、错误处理、性能与安全审查 / Full code review](docs/reviews/2026-10-29-code-review.md)

[使用指南 / User guide](docs/USER_GUIDE.md) · [源码构建 / Build](docs/BUILDING.md) · [发行流程 / Releases](docs/RELEASE_PROCESS.md) · [版本记录 / Changelog](CHANGELOG.md)

Native SwiftUI/AppKit on Mac and WPF on Windows; no embedded web interface. Local SQLite state and configuration are excluded from releases. Internal identifiers retain the original name for upgrade compatibility.

Mac 使用 SwiftUI/AppKit，Windows 使用 WPF，不内嵌网页。数据保留在本机，不随发行包上传；内部标识沿用旧名以兼容升级。

Scheduling includes adaptations from [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor). [Third-party notices](third-party/) are retained. This independent project is not affiliated with OpenAI.
