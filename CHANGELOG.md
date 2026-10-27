# Changelog / 版本记录

## 0.3.0 — Public preview / 公开预览

- Reworked native task cards into two columns, moved status beside the task title, and placed automatic control in the instruction header. / 任务卡片改为两列，状态移至标题旁，自动控制移至指令区顶部。
- Focused the interface on Codex chats. / 界面统一展示 Codex 聊天。
- Added six validated, revisioned operating rules, including UI refresh and normal/near-limit collection intervals. / 增加六项带校验和保存冲突保护的运行规则。
- Added green, blue, purple, and egg-yellow accents across light and dark appearance. / 增加绿、蓝、紫、鹅蛋黄主题色，适配浅色和深色。
- Preserved Chinese composition, selection, and unsaved instruction drafts across background refreshes in the Mac native editor. / 修复 Mac 指令编辑器后台刷新时可能覆盖中文组合输入、光标和草稿的问题。
- Distinguished new quota windows, verified balance recovery, and restored service permission in recovery records. An unknown reset cause remains unknown. / 恢复记录区分新额度窗口、余额恢复和服务许可恢复，不将未知原因描述为官方重置。
- Added read-only reset-credit details when available. Credits are not automatically consumed. / 支持展示服务返回的重置权益数量和详情，不自动消耗。
- Unified version metadata through `VERSION` and documented bundled-runtime builds for both platforms. / 两平台统一读取 `VERSION`，补充完整运行环境构建和发行流程。

See [0.3.0 release notes](docs/releases/0.3.0.md) for validation boundaries and manual acceptance checks. / 验证范围和人工验收项目见 [0.3.0 发行说明](docs/releases/0.3.0.md)。

## 0.2.1

Adapted quota handling to service-provided subscription windows and permissions. Added the Windows native preview and refined connection, delivery, and tray behavior. / 按服务实际返回的额度窗口及许可适配订阅，增加 Windows 原生预览，改进连接、发送回执和托盘行为。

## 0.2.0

Added native settings, Chinese/English interfaces, system/light/dark appearance, and quota controls in the menu panel. / 增加原生设置、中英文、系统／浅色／深色外观及菜单面板额度控制。

## 0.1.0

Initial macOS native preview with quota-aware pause/recovery, one-time instructions, and activity records. / 首个 Mac 原生预览，提供额度暂停续接、一次性指令和操作记录。

Historical preview assets and their individual acceptance scope remain on [GitHub Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases). / 历史预览文件及各自验收范围见 [GitHub Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases)。
