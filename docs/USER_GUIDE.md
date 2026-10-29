# TokenMax · TOKEN榨汁机 使用指南 / User guide

## 中文

### 开始使用

1. 打开并登录兼容的 Codex 桌面客户端。
2. 打开 TOKEN榨汁机，检查账号、额度和聊天列表。
3. 开启所需聊天的“榨汁状态”开关，再点“开始榨汁”。新安装默认停用。
4. 在操作记录中查看暂停、续接和发送结果。

### 来一杯

- **榨汁状态：**允许按额度暂停、续接该聊天。等待用户输入、审批或已被手动保持的任务不会自动续接。
- **恢复后执行：**保存一次性指令，额度恢复并通过检查后发送；送达后关闭预约。
- **立刻执行：**发送当前指令。提交不等于送达；结果不确定时不会自动重复发送。
- **暂停榨汁：**停止自动暂停、续接和预约调度，不中断正在运行的任务。
- **暂停所有任务：**手动暂停符合条件的受管任务。重新“开始榨汁”不会解除这些手动保持。

“未打开”表示当前没有客户端加载该聊天；榨汁许可仍保留。你在 Codex 中打开聊天后，后续状态采集会重新核对。此检查不会自动打开聊天或发送指令；“连接待恢复”保留给实际通信异常。

启用榨汁只代表调度已开启，不代表每个聊天都在执行。聊天状态和操作记录反映实际结果。Logo 停用时灰色静止，启用时金色闪电每 2 秒渐强渐弱，十种随机分叉电流从符号向外发出；等待、断连和错误各有杯内符号。系统开启“减少动态效果”时保持静态。Mac 菜单栏使用单独的彩色小图标。

界面读取后台缓存；默认每 5 秒刷新。任务状态通常每 30 秒采集，临近额度或有预约时每 10 秒采集，另加处理耗时。连接中断时显示待恢复，并自动重连；不会把旧状态当作已执行回执。

### 操作记录

下拉框可选“全部记录／用户操作／自动进程”，筛选最近载入的 200 条总记录，不删除历史。刷新与切换外观会保留筛选。

额度恢复记录默认显示来源及余额变化，详细采样信息可展开查看。来源为推断：权益使用、正常周期、提前恢复或来源未明；不是官方原因回执。权益数据仅供查看，不会自动兑换。首次采样建立基线，不补写此前历史。完整判定边界见 [0.3.3 说明](releases/0.3.3.md)。

### 运行规则

**监控窗口：**可选五小时额度或周额度。Plus 可选择账号实际返回的窗口；Pro 默认周额度，五小时选项置灰。首次使用和旧设置自动选择：优先五小时，Pro 或仅有周额度时选周。缺失或未核验的窗口不可选择；手动选定的窗口消失后会暂缓自动续接，需重新选择或等待核验。

下面的暂停和恢复阈值用于所选窗口。例如选择周额度后，剩余不高于 10% 时暂停，至少恢复到 20% 并通过复核后才续接。其他窗口虽不使用该百分比保留值，但用尽或服务禁止使用仍会暂停。官方未提供固定窗口而仅明确许可使用时，百分比阈值不适用。

新建预约使用所选监控窗口；已保存的预约保留原窗口。保存规则不会开启已暂停的全局榨汁，也不会解除手动保持。

| 设置 | 默认 | 范围 |
| --- | --- | --- |
| 暂停阈值 | 10% | 1–50% |
| 恢复阈值 | 20% | 5–95%，至少高于暂停值 5 个百分点 |
| 正常采集 | 30 秒 | 10–300 秒 |
| 临近阈值采集 | 10 秒 | 5–60 秒，不长于正常间隔 |
| 恢复复核 | 5 秒 | 3–60 秒 |
| 界面刷新 | 5 秒 | 2–30 秒 |

保存后生效。恢复复核是最短等待时间，仍需下一次有效采样；处理耗时另计，不能保证恰好 5 秒续接。连接失败有重试间隔。界面刷新读取缓存；服务提供的额度和刷新时间不可编辑。保存冲突时保留草稿，可重新载入。

### 设置与退出

支持中英文、跟随系统／浅色／深色及四种主题色。通知仅用于暂停、续接、发送失败及需处理异常；关闭通知不影响执行。

关闭窗口后驻留菜单栏或托盘。选择“退出TOKEN榨汁机”（Windows 为“退出”），或 Mac 按 ⌘Q，停止应用后台；不会主动中断 Codex 工作。

“保持后台运行”可防止空闲睡眠，不保证手动睡眠或合盖后的联网与发送。Mac 预览未开放合盖辅助服务。普通控制不要求辅助功能、录屏或完全磁盘访问；项目所在受保护目录仍可能触发系统授权提示。

### 升级与排查

0.4.4 修复超长聊天状态触发接收上限后导致的连接中断，并在采样完成后释放本工具的订阅，减少闲置期间的重复推送。仍保留有限接收上限；超过上限会明确报错，不把旧状态当成当前状态。

0.4.3 增加监控窗口选择。旧设置自动适配：仅周额度的账号现在同样使用已设置的暂停／恢复阈值，不再仅等周额度用尽。请在运行规则中核对选择。

例行检查不会关闭全局榨汁，也不会仅因核验提示中断正在运行的聊天。新额度在聊天采集前更新，时间戳取实际采样时间；真正过期或通信失败时仍暂缓自动续接并提示重试。Logo 仍反映连接、额度和调度状态；灰色不一定代表用户按下了暂停。界面区分“已停止”和“待核验”。

升级前退出旧版。Mac 新应用为 `TokenMax.app`；旧版 `Codex Mission Manager.app` 可在退出后移除，勿同时运行。Windows 安装器沿用原安装位置。设置、任务和记录保留。

连接异常时，在设置中检查客户端状态，确认已登录并重新检查。未知客户端版本需要兼容更新。持续“连接中”不代表工作正常。

运行数据仍在 `~/Library/Application Support/CodexMissionManager`（Mac）或 `%LOCALAPPDATA%\CodexMissionManager`（Windows）。可能包含账号和聊天信息，勿直接公开上传。卸载应用默认保留这些数据。

这些记录目前没有应用层加密，文件权限不等于加密。仅绑定本机地址的界面服务也不构成不同本机程序或系统用户间的身份隔离。

## English

### Get started

1. Open a compatible Codex desktop client and sign in.
2. Open TokenMax and verify the account, quota, and chats.
3. Enable **Juicing** for the intended chats, then select **Start Juicing**. New installations start disabled.
4. Check Activity for pause, resume, and delivery results.

### Juice Bar

- **Juicing:** permits quota-aware pause and resume for that chat. Input requests, approvals, and manual holds prevent automatic resumption.
- **Run after recovery:** saves a one-time instruction. It is sent after quota and eligibility checks, then disarmed on confirmed delivery.
- **Run now:** sends the current instruction. Submission is not confirmed delivery; uncertain results are not automatically retried.
- **Pause Juicing:** stops automatic pause, resume, and scheduling without interrupting currently running tasks.
- **Pause all tasks:** manually holds eligible managed tasks. **Start Juicing** does not release those holds.

“Not open” means no client currently owns the chat. Its juicing permission stays saved. Opening it in Codex allows subsequent collection to recheck it; collection does not open chats or send instructions. “Connection unavailable” remains reserved for actual communication errors.

Enabled juicing means scheduling is on, not that every chat is running. Chat status and Activity report actual outcomes. The logo is gray and static while stopped; while enabled, its gold bolt breathes every two seconds and ten varied branching discharges emerge from the symbol. Waiting, disconnected, and error states have distinct symbols inside the cup. System reduced-motion settings keep it static.

### Activity

Filter the latest 200 loaded records by **All records / User actions / Automated processes**. Filtering preserves history and remains selected across refresh and appearance changes.

Quota recovery entries show attribution and balance changes; expand details for sample evidence. Attribution is inferred: credit use, scheduled reset, early recovery, or unknown source. It is not an official cause receipt. Credits are read-only and never redeemed automatically. The first sample establishes a baseline without reconstructing prior history. See [0.3.3 notes](releases/0.3.3.md) for attribution limits.

### Operating rules

**Monitoring window:** choose five-hour or weekly quota. Plus can select windows actually returned for the account. Pro defaults to weekly, with five-hour disabled. New and legacy settings select automatically: five-hour first, or weekly for Pro and weekly-only accounts. Missing or unverified windows cannot be selected. If an explicitly selected window disappears, automatic resumption waits for verification or a new selection.

The thresholds below apply to the selected window. For weekly monitoring, the default pauses at 10% or less and resumes only at 20% or more after confirmation. Other windows do not use this reserve threshold, but exhaustion or a service block still pauses eligible tasks. Percentage thresholds do not apply when the service explicitly permits use without fixed windows.

New schedules use the selected window. Existing schedules retain their original window. Saving rules does not enable globally paused juicing or clear manual holds.

| Setting | Default | Range |
| --- | --- | --- |
| Pause threshold | 10% | 1–50% |
| Resume threshold | 20% | 5–95%, at least 5 points above pause |
| Normal collection | 30 s | 10–300 s |
| Near-limit collection | 10 s | 5–60 s, no longer than normal |
| Recovery confirmation | 5 s | 3–60 s |
| UI refresh | 5 s | 2–30 s |

Changes apply after saving. Recovery confirmation is a minimum wait and still requires a subsequent valid sample; processing adds time, so a five-second setting does not guarantee resumption at exactly five seconds. Connection failures use retry delays. UI refresh reads the cache. Service quota and reset times are read-only. Conflicting saves retain drafts for review or reload.

### Settings and quitting

Choose Chinese/English, system/light/dark appearance, and four accent colors. Notifications cover pause, resume, failed delivery, and actionable errors. Turning them off does not stop execution.

Closing the window keeps the app in the menu bar or tray. Use **Quit TokenMax** (**Quit** on Windows), or ⌘Q on Mac, to stop its background work. Quitting does not intentionally interrupt Codex tasks.

Keep-awake prevents idle sleep, not manual sleep or guaranteed operation with the lid closed. The Mac preview does not enable the closed-lid helper. Ordinary control needs no Accessibility, Screen Recording, or Full Disk Access; protected project folders may still require system consent.

### Upgrade and troubleshoot

0.4.4 fixes disconnections from long chat snapshots exceeding the receive limit and releases this tool’s subscription after sampling, reducing unnecessary background pushes. A finite limit remains; larger frames fail explicitly rather than presenting old state as current.

0.4.3 adds monitoring-window selection. Legacy settings adapt automatically: weekly-only accounts now use the configured pause/resume thresholds instead of waiting for weekly exhaustion. Review the selection in Operating rules.

Routine checking does not turn off global juicing or interrupt a running chat solely because verification is pending. Fresh quota is published before chat collection, with its actual observation timestamp. Genuine stale data or connection failures still withhold automatic resumption and show a retry notice. The logo reflects connection, quota, and scheduling state; gray does not necessarily mean the user pressed Pause. The interface distinguishes Stopped from Awaiting verification.

Quit the previous version before upgrading. On Mac, install `TokenMax.app`, then remove the old `Codex Mission Manager.app`; do not run both. Windows retains the existing installation location. Settings, tasks, and history are preserved.

For connection issues, inspect client status in Settings, confirm sign-in, and check again. Unknown client versions need a compatibility update. A persistent connecting state is not normal operation.

Data remains in `~/Library/Application Support/CodexMissionManager` on Mac and `%LOCALAPPDATA%\CodexMissionManager` on Windows. It may contain account and chat information; do not upload it publicly without review. Uninstalling preserves this data by default.

These records currently have no application-level encryption; file permissions are not encryption. Binding the interface service to loopback also does not authenticate different local programs or operating-system users.
