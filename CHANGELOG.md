# Changelog / 版本记录

## 0.3.2 — Windows text layout / Windows 输入框布局修复

- Removed duplicated padding from the shared Windows text-input template. / 修复 Windows 输入框模板重复扣除内边距的问题。
- Replaced the fixed-height numeric-field constraint with font-aware minimum sizing, preventing clipped values in Operating Rules. / 运行规则数值框按字体确定最小高度，避免固定高度裁切文字。
- Added native before/after geometry checks for numeric fields, search, and multiline instructions, with layout-scale and text-size stress cases. / 增加数值、搜索和多行指令框的原生修复前后测量，以及布局缩放和字号压力检查。
- Highlighted the corrected Windows Rules page in light and dark release previews. Mac UI behavior remains unchanged. / 发行预览重点展示 Windows 规则页浅深色；Mac 界面行为保持不变。

Logical rendering stress tests do not establish full coverage of actual monitor DPI or Windows accessibility text-size settings. See [0.3.2 release notes](docs/releases/0.3.2.md). / 逻辑渲染压力检查不代表已完整验收真实显示器 DPI 或 Windows 辅助功能文字缩放，详见 [0.3.2 发行说明](docs/releases/0.3.2.md)。

## 0.3.1 — Reliable quit / 退出修复

- Made Quit visible in a fixed menu-panel footer and retained the application-menu keyboard shortcut. / 菜单面板固定显示退出入口，保留应用菜单快捷键。
- Bounded shutdown work and made repeated quit requests idempotent on Mac and Windows. / Mac 与 Windows 使用有时限的停止流程，重复退出请求复用同一次操作。
- Isolated cleanup to application-owned background processes; existing client tasks are not interrupted on quit. / 清理仅针对应用自身的后台进程，退出不主动中断原客户端任务。
- Retained close-to-background behavior and all V0.3.0 features. / 保留关闭窗口驻后台行为及 V0.3.0 的全部功能。

See [0.3.1 release notes](docs/releases/0.3.1.md). / 详见 [0.3.1 发行说明](docs/releases/0.3.1.md)。

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
