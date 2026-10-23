# Codex Mission Manager · 任务管家

Mac 本机聊天任务管家：按额度暂停和续接，安排下个五小时窗口的一次性指令，以及即时发送。产品基线见 [V0.1 总蓝图](docs/PRODUCT_BLUEPRINT_V0.1.md)。

[下载原生窗口预览 DMG](https://github.com/Dddysun/Codex-Mission-Manager/releases/tag/v0.1.0-preview.3) · [打包验证记录](docs/validation.json)

## V0.1 架构

- SwiftUI / AppKit 原生主窗口和设置页、固定菜单栏 Logo。
- 原生聊天列表、公开执行阶段、状态、自动控制开关、TextEditor 指令框、预约、立刻执行与回执；不使用 WKWebView，也不依赖浏览器。
- 原生 URLSession 通过本机 JSON API 连接现有 Python 调度服务；界面每 5 秒同步，编辑中的草稿不随刷新丢失。
- Python 标准库后端、SQLite 本机账本、版本锁定的原桌面客户端 IPC。
- 应用捆绑精简 CPython，不需要系统 Python、Node 或 Homebrew。
- 独立受限的管理员电源辅助服务，使用 SMAppService 登记及签名身份校验；本机临时签名预览中禁止启用。

安装包不分发原 ChatGPT/Codex 客户端。当前执行通道只适配已验证的 ChatGPT 桌面 build 20770；升级版本时先停止控制、重新适配。普通 ChatGPT 聊天保持只读目录，且客户端近期目录快照需要用户提供的连接渠道更新；本包不附带个人聊天快照。

## 构建

需要 Apple Silicon Mac、macOS 14+、Apple Command Line Tools，以及可重定位的 CPython 3.12 发行目录。应用使用者不需要这些构建工具。

```sh
python3 scripts/build.py --python-runtime /path/to/relocatable-python --output dist/0.1.0-preview
python3 scripts/make_dmg.py --build dist/0.1.0-preview
```

正式签名构建同时提供 `MISSION_TEAM_ID` 和 `MISSION_SIGN_IDENTITY` 环境变量。变量只标识代码签名身份，不包含密码。公证采用已在 Keychain 配置的 notarytool profile，参见发行说明。未提供签名身份时，构建仅生成临时签名本机预览，不会开放管理员合盖服务。

## 运行行为

关闭窗口继续后台运行；菜单栏提供打开窗口、暂停/恢复自动控制、退出。主窗口左侧有应用设置入口，也可按 Command–逗号。退出会停止应用管理的服务及电源保持，不向原聊天发送中断指令。

若检测到旧网页版后台正在运行，优先连接旧服务，不启动第二套执行器。当前不会自动迁移或覆盖旧账本。需要迁移时先停止旧服务，再使用 `backend/app_host.py --migrate` 显式复制账本；目标已有数据时拒绝覆盖。新安装的独立账本默认全局暂停自动控制，用户确认后启用。

## 后台权限与限制

设置分别显示登录启动、通知、普通防睡眠、管理员合盖服务、客户端兼容及电源条件。未知状态显示待确认，授权不等于实机验收通过。

无外屏合盖的正式服务只接受同团队、指定应用身份的 XPC 客户端，只执行固定睡眠覆盖开关。默认需接电；电池模式截止20%，严重热压力或45秒失联恢复。启用前需要手动 Control–Command–Q 锁屏并接收到系统锁屏事件；解锁撤销增强保持，不通过模拟键鼠或私有锁屏调用工作。锁屏通知的可靠性、真实合盖、窗口恢复后的发送仍必须实机验收。

**当前预览包没有 Developer ID 签名与 Apple 公证，管理员合盖能力不可启用；不能将本包视为完整合盖能力验收版。** 不提供绕过 Gatekeeper 的脚本，也不修改 sudoers。

## 数据与来源

运行数据保存在用户 Application Support；连接旧服务时沿用旧本机目录。仓库和 DMG 不包含账号、令牌、聊天或用户账本。

调度规则部分改编自 MIT [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor)，许可证见 third-party。电源架构调研参考 [Amped](https://github.com/gustaferiksson/amped) 和 [Sleepless](https://github.com/Aboudjem/Sleepless)，当前电源代码独立实现，未复制这两个仓库的源码。CPython 运行环境保留 PSF 及内置第三方许可证。

## 检查

```sh
python3 -m unittest discover -s backend/tests -v
PYTHONPATH=backend python3 -m unittest discover -s tests -v
node backend/tests/test_sidebar.cjs
```

构建和测试不安装管理员服务、不改变电源设置、不向真实聊天发送测试指令。所有未完成的实机与发行检查记录在 `docs/RELEASE_STATUS.md`。
