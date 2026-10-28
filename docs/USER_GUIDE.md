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

既有任务恢复记录区分新额度窗口、余额提前恢复和服务许可恢复。如果账号返回重置权益，数量和详情仅供查看，不会自动兑换，也不会将未使用的权益视为额度已经恢复。

### 额度恢复记录

V0.3.3 起，管家从通过时效及身份校验的服务采样中独立记录观察到的额度恢复。没有受管任务、全局自动控制已暂停或通知已关闭时，仍会记录。应用需要运行并能够取得服务数据；离线期间的变化无法完整重建。

相同刷新截止时间下，余额至少回升 5 个百分点才触发记录；较小回升伴随可信的截止时间推进时也可记录，但来源可能仍待确认。采样跨越旧截止时间，且刷新时间推进约一个完整周期时，会记录新周期；即使新消耗使净余额从 98% 降至 97%，仍保留周期变化，并标明净余额未上涨。记录门槛与用于任务续接的恢复阈值分别生效。

操作记录将显示恢复前后各窗口的剩余百分比与刷新时间、重置权益可用数量、前后采样时间和来源判断依据。记录中的来源属于观察推断：

- **用户主动恢复：**同时观察到余额恢复，以及可核对的权益清单与数量变化，推断与权益使用相关；可用次数减少本身不足以确认用户操作。
- **官方正常周期重置：**观察到原窗口到期附近的周期推进，且可比的权益清单和数量保持稳定。
- **官方独立重置：**观察到原窗口截止前的显著余额回升，且可比的权益清单和数量保持稳定。该名称不确认某次官方活动。
- **未归因恢复：**余额或周期变化可见，但来源依据不足。权益字段缺失、无法区分权益过期与使用、清单不完整、采样间隔过长或窗口变化不明确时，保留不确定性。多个窗口的判断不同时，整体显示未归因，详情保留逐窗口结论。

权益的数量、清单、支持状态或字段发生变化后，有 120 秒的来源观察期，即使发生变化的当次采样没有余额回升也会生效。观察期内随后出现的余额回升会保留未归因，避免将延迟生效的权益使用误判为官方恢复；同一采样中具备完整、可核对的权益使用依据时，仍可标为推断的用户主动恢复。记录在检测到变化时立即写入，不等待观察期结束，也不根据稍后的权益变化追溯改写既有记录。

服务目前没有为这些记录提供直接的重置原因回执，`official_reason` 保持空值。首次安装或升级至此功能版本，以及切换账号、额度类别时先建立基线，不补写当天较早的历史；持久化基线与事件一起保存，应用重启不会重复记录同一已观察变化。

该记录独立于任务续接。满足既有条件的任务和一次性预约可在余额恢复后继续核验与执行；账号、额度、连续确认、人工接管、聊天授权及发送保护仍然适用。

### 外观、通知与后台

设置和菜单面板可切换简体中文／English、跟随系统／浅色／深色，以及绿／蓝／紫／鹅蛋黄主题色。指令草稿在背景同步和外观切换时保留。

关闭主窗口后仍在菜单栏或系统托盘运行。完整退出请点击菜单面板底部固定的“退出任务管家”（Windows 为“退出”），或在 Mac 应用菜单选择“退出任务管家”／按 ⌘Q。退出会停止管家自己的后台与防睡眠请求，不主动中断 Codex 中的工作；无需额外授予辅助功能、录屏或管理员权限。停止流程具有截止时间，重复点击退出不会启动多次清理。

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

Existing task-recovery records distinguish a new quota window, early balance recovery, and restored service permission. Reset credits, when supplied, are read-only. They are never automatically redeemed, and unused credits are not evidence of recovered quota.

### Quota recovery history

From V0.3.3, Mission Manager records observed quota restoration independently from service samples that pass freshness and identity checks. Recording continues with no managed tasks, global automatic control paused, or notifications disabled. The application must be running and able to obtain service data; changes during an offline period cannot be fully reconstructed.

A balance increase with the same reset deadline must reach 5 percentage points to create a record. Smaller increases accompanied by a credible deadline advance can also be recorded, with attribution left unresolved when evidence is insufficient. Samples crossing the prior deadline with an advance of approximately one full period record the new cycle, even if subsequent spending reduces the net balance from 98% to 97%; details identify that the net balance did not increase. The recording threshold is separate from the task-resumption threshold.

Activity shows each affected window's before/after remaining percentage and reset deadline, available reset-credit counts, both observation times, and attribution evidence. Source labels describe inferences from observations:

- **User-initiated reset:** balance restoration coincides with reconcilable credit-inventory and count changes suggesting credit use. A falling available count alone does not establish a user action.
- **Scheduled service reset:** the prior window rolls over near its deadline while comparable credit inventory and counts remain stable.
- **Independent service reset:** a substantial balance increase occurs before the prior deadline while comparable credit inventory and counts remain stable. The label does not confirm a particular service promotion.
- **Unattributed recovery:** restoration or rollover is visible, but attribution evidence is insufficient. Missing credit fields, expiry that cannot be distinguished from use, incomplete inventories, long observation gaps, and ambiguous window changes retain uncertainty. If windows receive different classifications, the overall record is unattributed and details preserve each window's conclusion.

A change in credit counts, inventory, support status, or fields starts a 120-second attribution observation period, even if the balance does not increase in that sample. A subsequent balance increase during that period remains unattributed, avoiding an official-reset inference for delayed credit use. Complete, reconcilable credit-use evidence in the same sample can still support an inferred user-initiated reset. Records are written immediately when a change is detected; they do not wait for the observation period or receive retrospective attribution changes from later credit observations.

The service does not supply a direct reset-cause receipt for these records; `official_reason` remains null. The first observation after installing or upgrading to this feature version, or changing accounts or quota buckets, establishes a baseline without reconstructing earlier activity that day. Baselines and events are persisted together, so restarting does not duplicate an already observed change.

These records are independent of task resumption. Eligible tasks and one-time schedules continue through the existing recovery checks when quota becomes available. Account matching, allowance, consecutive confirmation, manual intervention, chat authorization, and delivery safeguards still apply.

### Appearance and background operation

Settings and the menu panel offer Chinese/English, system/light/dark appearance, and green/blue/purple/egg-yellow accents. Background refresh and appearance changes preserve instruction drafts.

Closing the main window keeps the app in the menu bar or system tray. Use the fixed **Quit Mission Manager** action at the bottom of the menu panel (**Quit** on Windows), or the Mac application menu / ⌘Q. Quitting stops app-owned background processes and keep-awake requests without intentionally interrupting Codex work; no additional Accessibility, screen-recording, or administrator permission is needed. Shutdown has a deadline, and repeated quit requests share the same cleanup operation.

- **Start at sign-in:** optional, with status based on system registration.
- **Task notifications:** pauses, resumptions, failed deliveries, and actionable errors only. Denying notifications does not prevent task execution. App preference and system permission are separate.
- **Keep running in the background:** optionally prevents idle sleep while allowing the display to turn off. It cannot provide a network connection or guarantee delivery during manual sleep, lock, or lid closure.
- **Lid closure:** the Mac preview does not enable its closed-lid helper. Neither platform guarantees operation with the lid closed and no external display. System power policy still applies.

Ordinary control does not require Accessibility, Screen Recording, or Full Disk Access. An existing client project may separately trigger a system prompt for a protected directory; Mission Manager does not grant that permission on the user's behalf. Settings show available checks and links to the appropriate system settings.

### Connection and local data

Check client status in Settings. A closed client, missing sign-in, unknown client version, or stale data limits control. Open and sign in to the client, then select **Check again**. An unsupported version needs a compatibility update; a persistent connecting state is not proof of normal operation.

Mac data lives at `~/Library/Application Support/CodexMissionManager`; Windows data lives at `%LOCALAPPDATA%\CodexMissionManager`. It may contain account identifiers, instructions, task records, and logs. Review and redact it before reporting an issue. Quit Mission Manager before updating. Windows uninstall preserves user data; removing the Mac application does not automatically delete its data folder.
