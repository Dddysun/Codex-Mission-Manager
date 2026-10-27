# User guide / 使用指南

## 中文

### 首次使用

1. 安装并登录兼容的官方 Codex 桌面客户端，再打开任务管家。
2. 检查侧栏账号、额度信息以及聊天列表。未知、过期或连接异常的信息不能作为可发送依据。
3. 首次安装的全局自动控制默认暂停。需要接管某个聊天时，开启该聊天的“自动控制”，再启用全局自动控制。
4. 在操作记录中核对暂停、续接、预约和发送结果。当前执行阶段来自最近采集到的公开进度或结果，不是实时屏幕读取。

### 三种控制

- **聊天自动控制：**授予管家对该聊天按额度暂停和续接的许可。额度恢复后仅继续符合条件的原任务；人工输入、审批、手动保持和任务状态仍会阻止自动发送。
- **额度恢复后执行：**保存一次性指令并开启预约。该聊天不必由管家在本轮暂停。实际发送前仍检查账号、额度、连接与聊天状态；成功发送后关闭该次预约。
- **立刻执行：**发送当前指令，用于手动触发。点击后查看确认结果；“请求已提交”不等于“已确认送达”。发送结果不确定时，不自动重复发送。

关闭全局自动控制会停止自动暂停、续接和预约调度。取消某个聊天的许可或预约只影响对应项目。“暂停所有任务”只处理已授权、正在执行且无需人工输入或审批的受管任务；这是手动暂停，重新启用全局自动控制不会隐式恢复这些任务。闲置的“等待指令”聊天不会因此自动产生新任务。

### 额度与运行规则

侧栏和菜单面板显示服务实际返回的额度窗口、剩余量和刷新时间。不同订阅可能提供不同窗口；缺失数据不表示无限额度。刷新时间由服务决定，不能在应用中修改。

运行规则支持整数，保存后生效：

- **暂停阈值：**剩余 1–50%，默认 10%。
- **恢复阈值：**剩余 5–95%，默认 20%；至少比暂停阈值高 5 个百分点。
- **正常采集间隔：**10–300 秒，默认 30 秒。
- **临近阈值采集间隔：**5–60 秒，默认 10 秒；不能长于正常间隔。额度不足或存在待执行预约时也会使用较快采集。
- **恢复确认间隔：**3–60 秒，默认 5 秒；用于连续核验，不代表达到该秒数就一定发送。
- **界面刷新间隔：**2–30 秒，默认 5 秒；读取后台缓存，不会额外采集客户端。

采集间隔从上一轮结束后计时，每轮采集和处理耗时另计。连接异常还有独立重试退避，因此状态可能延迟更新。保存失败或发生设置冲突时保留草稿；使用“放弃修改”重新载入当前规则。

正常窗口刷新、余额提前恢复和服务许可恢复会分别记录。余额回升本身不能证明官方活动或人工重置；应用在原因未知时明确标为未知。如果账号返回重置权益，数量和详情仅供查看，不会自动兑换，也不会将未使用的权益视为额度已经恢复。

### 外观、通知与后台

设置和菜单面板可切换简体中文／English、跟随系统／浅色／深色，以及绿／蓝／紫／鹅蛋黄主题色。指令草稿在背景同步和外观切换时保留。

关闭主窗口后仍在菜单栏或系统托盘运行。“退出”停止管家自己的后台与防睡眠请求，不主动中断 Codex 中的工作。

- **登录时启动：**可选，状态以系统登记结果为准。
- **任务通知：**仅用于暂停、续接、发送失败和需处理异常；系统拒绝通知不影响任务执行。应用开关与系统权限分别管理。
- **保持后台运行：**可选，防止空闲睡眠，允许屏幕关闭。不能代替联网，也不保证手动睡眠、锁屏或合盖后的发送。
- **合盖：**当前 Mac 公开预览未开放合盖辅助服务；两平台均不保证无外屏合盖运行。合盖和电源行为由系统设置决定。

普通控制不要求辅助功能、屏幕录制或完全磁盘访问。若客户端的现有项目引用受保护目录，系统可能单独要求访问该目录；应用不会替用户授予权限。设置页提供真实状态检查和相应系统设置入口。

### 连接异常与数据

先查看设置中的客户端连接信息。客户端关闭、账号未登录、升级后版本未知或数据过期时，自动控制会受限。重新打开客户端并登录后使用“重新检查”；若提示版本未适配，请等待兼容更新，不把长期“连接中”视为正常运行。

Mac 运行数据在 `~/Library/Application Support/CodexMissionManager`；Windows 在 `%LOCALAPPDATA%\CodexMissionManager`。其中可能包含账号标识、指令、任务记录和日志，请勿直接作为公开问题附件。更新前从菜单栏／托盘退出管家。Windows 卸载器保留用户数据；Mac 移除应用也不会自动清除该数据目录。

## English

### Getting started

1. Install a compatible official Codex desktop client, sign in, and open Mission Manager.
2. Verify the account, quota, and chat list. Unknown, stale, or disconnected data does not authorize sending.
3. New installations start with global automatic control paused. Enable **Automatic control** for each intended chat, then enable global control.
4. Inspect activity records for pause, recovery, schedule, and delivery results. Execution stage reflects recently collected public progress or results, rather than a live screen feed.

### Three controls

- **Per-chat automatic control:** authorizes quota-aware pause and recovery for that chat. Resumption still requires an eligible original task; user input, approvals, manual holds, and chat state can block sending.
- **Run after quota recovery:** saves a one-time instruction. The chat need not have been paused by Mission Manager in this round. Account, quota, connection, and chat state are checked before sending. Confirmed sending disarms that schedule.
- **Run now:** manually sends the current instruction. Inspect its result: request submission is distinct from confirmed delivery. Uncertain results are not automatically retried.

Disabling global automatic control stops automatic pauses, resumptions, and scheduled dispatch. Revoking a chat's permission or schedule affects that item. **Pause all tasks** targets authorized, running chats that are not waiting for input or approval. These are manual holds; enabling global control does not implicitly resume them. An idle chat waiting for instructions does not automatically become a new task.

### Quota and operating rules

Quota windows, allowance, and reset times come from the service. Subscriptions may expose different windows. Missing data is never treated as unlimited. Official reset times cannot be edited.

The following integer settings take effect after saving:

- **Pause threshold:** 1–50% remaining; default 10%.
- **Resume threshold:** 5–95% remaining; default 20%, at least 5 percentage points above the pause threshold.
- **Normal collection interval:** 10–300 seconds; default 30.
- **Near-limit collection interval:** 5–60 seconds; default 10, no longer than the normal interval. Low quota or a pending schedule also activates faster collection.
- **Recovery confirmation interval:** 3–60 seconds; default 5. This spaces consecutive verification; it is not a guaranteed dispatch delay.
- **UI refresh interval:** 2–30 seconds; default 5. This reads the cache and does not collect client state again.

Collection intervals begin after the previous round finishes. Collection and processing time are additional, and connection retries have separate backoff. Failed or conflicting saves retain the draft; **Discard changes** reloads current rules.

Records distinguish a new quota window, early balance recovery, and restored service permission. A balance increase alone does not prove an official promotion or manual reset; an unknown cause stays unknown. Reset credits, when supplied, are read-only. They are never automatically redeemed, and unused credits are not evidence of recovered quota.

### Appearance and background operation

Settings and the menu panel offer Chinese/English, system/light/dark appearance, and green/blue/purple/egg-yellow accents. Background refresh and appearance changes preserve instruction drafts.

Closing the main window keeps the app in the menu bar or system tray. **Quit** stops its own background process and keep-awake request without intentionally interrupting work in Codex.

- **Start at sign-in:** optional, with status based on system registration.
- **Task notifications:** pauses, resumptions, failed deliveries, and actionable errors only. Denying notifications does not prevent task execution. App preference and system permission are separate.
- **Keep running in the background:** optionally prevents idle sleep while allowing the display to turn off. It cannot provide a network connection or guarantee delivery during manual sleep, lock, or lid closure.
- **Lid closure:** the Mac preview does not enable its closed-lid helper. Neither platform guarantees operation with the lid closed and no external display. System power policy still applies.

Ordinary control does not require Accessibility, Screen Recording, or Full Disk Access. An existing client project may separately trigger a system prompt for a protected directory; Mission Manager does not grant that permission on the user's behalf. Settings show available checks and links to the appropriate system settings.

### Connection and local data

Check client status in Settings. A closed client, missing sign-in, unknown client version, or stale data limits control. Open and sign in to the client, then select **Check again**. An unsupported version needs a compatibility update; a persistent connecting state is not proof of normal operation.

Mac data lives at `~/Library/Application Support/CodexMissionManager`; Windows data lives at `%LOCALAPPDATA%\CodexMissionManager`. It may contain account identifiers, instructions, task records, and logs. Review and redact it before reporting an issue. Quit Mission Manager before updating. Windows uninstall preserves user data; removing the Mac application does not automatically delete its data folder.
