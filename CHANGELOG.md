# Changelog / 版本记录

## 0.4.4 — Long snapshot reception / 超长状态接收

- Accept bounded snapshots up to 256 MiB after a live 197 MiB frame exceeded the prior cap. / 接收上限改为有界的 256 MiB，覆盖实际 197 MiB 状态帧。
- Release this tool’s subscription after each snapshot attempt, with a bounded cleanup write. / 每次快照采样后取消本工具的订阅，清理写入有时间上限。
- Exercise a 200 MiB synthetic history and preserve oversized-header rejection and reconnection checks. / 使用 200 MiB 模拟历史验证，保留超限拒绝与重连检查。

See [0.4.4 release notes](docs/releases/0.4.4.md). / 详见 [0.4.4 发行说明](docs/releases/0.4.4.md)。

## 0.4.3 — Monitoring window and collection status / 监控窗口与采集状态

- Choose five-hour or weekly thresholds in native Operating rules; Pro defaults to weekly with five-hour disabled. / 原生运行规则可选五小时或周额度，Pro 默认周额度，五小时置灰。
- Save window and numeric rules atomically, preserve existing schedule windows, and cancel control from an obsolete rule cycle. / 窗口与数值规则原子保存，保留已有预约窗口，旧规则轮次停止控制。
- Publish verified quota before collecting chats, retain actual timestamps, reuse discovery, and honor confirmation deadlines. / 先更新已核验额度，保留真实采样时间，复用目录发现并考虑恢复复核期限。
- Distinguish awaiting verification from a global pause; retain working motion during healthy collection. / 区分待核验与全局暂停，正常采集保留工作动画。

See [0.4.3 release notes](docs/releases/0.4.3.md). / 详见 [0.4.3 发行说明](docs/releases/0.4.3.md)。

## 0.4.2 — Runtime fixes and core discharge / 运行修复与内核放电

- Distinguish an explicitly unloaded monitored chat from real connection failure; preserve unresolved-action alerts and task permissions. / 区分明确未加载的监测聊天与真实连接故障，保留未确认动作的告警和任务许可。

- Brand 1.3.0: ten irregular core-origin discharges and independent two-second bolt breathing in native Mac, Windows and SVG. / 品牌 1.3.0：两端原生及 SVG 同步十种随机内核放电，保留独立 2 秒呼吸。

- Disable Python bytecode writes explicitly in both native launchers and owned subprocesses. / 两平台原生启动器和后台子进程显式禁止生成 Python 字节码缓存。
- Verify cold imports on a writable application copy, then recheck unchanged resources and the Mac signature. / 在可写应用副本中验证冷导入，再核对资源未变及 Mac 签名完整性。
- Bound transport writes, full request exchanges and desktop connection shutdown. / 为通信写入、完整请求与桌面连接关闭设置超时边界。
- Keep user revocations, task revisions, preferences and adoption intents consistent in one write transaction. / 用写事务保护用户撤销、任务修订号、偏好与接管意图的一致性。
- Use direct catalog lookups for sorting, reject overflowing quota numbers, and bound local HTTP workers and idle sockets. / 排序直接查询目录字典，拒绝额度数值溢出，并限制本机 HTTP 工作线程及空闲连接。
- Honor the configured snapshot budget for large frames and preserve rejected-request errors on Windows. / 大帧快照采用配置的等待预算，Windows 拒绝请求时保留可读错误回执。
- Preserve native interfaces, existing settings, tasks, and history. / 保留原生界面、已有设置、任务和记录。

See [0.4.2 release notes](docs/releases/0.4.2.md). / 详见 [0.4.2 发行说明](docs/releases/0.4.2.md)。

## 0.4.1

- 修复大型会话快照导致状态同步断开的问题，并补上 Mac 自动重连与断线状态报告。

- 中文品牌名更新为 TOKEN榨汁机；英文名保留 TokenMax。
- Mac 菜单栏使用更清晰的彩色小尺寸图标。
- 闪电下移，工作态改为分叉电流、暖色亮芯和流动拖尾；支持深色与减少动态效果。
- Mac、Windows 和可复用 SVG 组件同步更新，保留配置、任务与记录。



## 0.4.0 — TokenMax · 榨汁机

- Fixed chat-list loading with structured connection errors. / 修复连接错误记录导致聊天列表无法载入。
- Fixed Chinese shortcut creation on English Windows. / 修复英文 Windows 下创建中文快捷方式失败。
- Renamed both apps and packages, retaining existing data. / 两平台更名并保留现有数据。
- Added the geometric juicer logo, native running animation, dark colors, and reduced-motion support. / 接入几何榨汁机 Logo、原生动效、深色及减少动态适配。
- Introduced Start Juicing and clean per-chat Juicing switches. / 启动改为“开始榨汁”，精简聊天开关。
- Shortened Chinese/English copy and collapsed quota-event evidence. / 精简中英文提示，额度记录详情按需展开。

See [0.4.0 release notes](docs/releases/0.4.0.md). / 详见 [0.4.0 发行说明](docs/releases/0.4.0.md)。

## 0.3.4 — Activity source filters / 操作记录来源筛选

- Added All records, User actions, and Automatic processes to both native Activity pages. / 两平台原生操作记录增加“全部记录／用户操作／自动进程”下拉筛选。
- Assigned event origins consistently in the backend, with compatible classification of older records at read time. / 后台统一标注事件来源，旧记录在读取时兼容分类。
- Kept the selected filter across refresh, language, and appearance changes, with a clear empty-result message. / 刷新、语言及外观切换时保留当前筛选，无匹配结果时显示提示。
- Limited filtering to the latest 200 loaded records in total; existing records and task controls remain unchanged. / 筛选作用于最近载入的 200 条总记录，保留原记录及任务控制行为。

See [0.3.4 release notes](docs/releases/0.3.4.md). / 详见 [0.3.4 发行说明](docs/releases/0.3.4.md)。

## 0.3.3 — Quota recovery history / 额度恢复记录

- Record observed quota restoration independently of task activity, automatic-control settings, and notification permission. / 独立记录观察到的额度恢复，不依赖任务活动、自动控制开关或通知权限。
- Show before/after allowance, reset deadlines, credit counts, and observation times in the native Activity pages on both platforms. / 两平台原生操作记录展示恢复前后余额、刷新时间、权益数量及采样时间。
- Distinguish inferred user resets, scheduled service resets, independent service resets, and unattributed recovery; retain per-window evidence when sources differ. / 区分推断的用户主动恢复、官方正常周期重置、官方独立重置及未归因恢复，多个窗口结论不同时保留逐窗口依据。
- Keep attribution unresolved for 120 seconds after credit changes, and record credible new cycles even when fresh consumption masks a balance increase. / 权益变化后保留 120 秒来源观察期；新消耗掩盖余额回升时，仍记录可信的新周期。
- Persist account-and-bucket baselines and events atomically to avoid duplicate records after restart; the first observation establishes a baseline without reconstructing earlier activity. / 按账号与额度类别原子保存基线和事件，避免重启重复记录；首次观察只建立基线，不补写此前历史。
- Keep reset credits read-only and preserve existing pause, recovery, consent, and delivery safeguards. / 重置权益保持只读，保留既有暂停、恢复、授权和发送保护。

Attribution is inferred from comparable observations; there is no direct official reset receipt. Missing or ambiguous evidence remains unattributed. See [0.3.3 release notes](docs/releases/0.3.3.md). / 来源依据可比采样推断，未获得官方直接重置回执；证据缺失或含糊时保留未归因状态。详见 [0.3.3 发行说明](docs/releases/0.3.3.md)。

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
