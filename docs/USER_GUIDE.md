# TokenMax · 榨汁机 使用指南 / User guide

## 中文

### 开始使用

1. 打开并登录兼容的 Codex 桌面客户端。
2. 打开榨汁机，检查账号、额度和聊天列表。
3. 开启所需聊天的“榨汁状态”开关，再点“开始榨汁”。新安装默认停用。
4. 在操作记录中查看暂停、续接和发送结果。

### 来一杯

- **榨汁状态：**允许按额度暂停、续接该聊天。等待用户输入、审批或已被手动保持的任务不会自动续接。
- **恢复后执行：**保存一次性指令，额度恢复并通过检查后发送；送达后关闭预约。
- **立刻执行：**发送当前指令。提交不等于送达；结果不确定时不会自动重复发送。
- **暂停榨汁：**停止自动暂停、续接和预约调度，不中断正在运行的任务。
- **暂停所有任务：**手动暂停符合条件的受管任务。重新“开始榨汁”不会解除这些手动保持。

启用榨汁只代表调度已开启，不代表每个聊天都在执行。聊天状态和操作记录反映实际结果。Logo 停用时灰色静止，启用时金色闪电呼吸、细线电弧绕杯；等待、断连和错误各有杯内符号。系统开启“减少动态效果”时保持静态。

### 操作记录

下拉框可选“全部记录／用户操作／自动进程”，筛选最近载入的 200 条总记录，不删除历史。刷新与切换外观会保留筛选。

额度恢复记录默认显示来源及余额变化，详细采样信息可展开查看。来源为推断：权益使用、正常周期、提前恢复或来源未明；不是官方原因回执。权益数据仅供查看，不会自动兑换。首次采样建立基线，不补写此前历史。完整判定边界见 [0.3.3 说明](releases/0.3.3.md)。

### 运行规则

| 设置 | 默认 | 范围 |
| --- | --- | --- |
| 暂停阈值 | 10% | 1–50% |
| 恢复阈值 | 20% | 5–95%，至少高于暂停值 5 个百分点 |
| 正常采集 | 30 秒 | 10–300 秒 |
| 临近阈值采集 | 10 秒 | 5–60 秒，不长于正常间隔 |
| 恢复复核 | 5 秒 | 3–60 秒 |
| 界面刷新 | 5 秒 | 2–30 秒 |

保存后生效。采集耗时另计，连接失败有重试间隔。界面刷新读取缓存；服务提供的额度和刷新时间不可编辑。保存冲突时保留草稿，可重新载入。

### 设置与退出

支持中英文、跟随系统／浅色／深色及四种主题色。通知仅用于暂停、续接、发送失败及需处理异常；关闭通知不影响执行。

关闭窗口后驻留菜单栏或托盘。选择“退出榨汁机”（Windows 为“退出”），或 Mac 按 ⌘Q，停止应用后台；不会主动中断 Codex 工作。

“保持后台运行”可防止空闲睡眠，不保证手动睡眠或合盖后的联网与发送。Mac 预览未开放合盖辅助服务。普通控制不要求辅助功能、录屏或完全磁盘访问；项目所在受保护目录仍可能触发系统授权提示。

### 升级与排查

升级前退出旧版。Mac 新应用为 `TokenMax.app`；旧版 `Codex Mission Manager.app` 可在退出后移除，勿同时运行。Windows 安装器沿用原安装位置。设置、任务和记录保留。

连接异常时，在设置中检查客户端状态，确认已登录并重新检查。未知客户端版本需要兼容更新。持续“连接中”不代表工作正常。

运行数据仍在 `~/Library/Application Support/CodexMissionManager`（Mac）或 `%LOCALAPPDATA%\CodexMissionManager`（Windows）。可能包含账号和聊天信息，勿直接公开上传。卸载应用默认保留这些数据。

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

Enabled juicing means scheduling is on, not that every chat is running. Chat status and Activity report actual outcomes. The logo is gray and static while stopped; while enabled, its gold bolt breathes and fine arcs orbit the cup. Waiting, disconnected, and error states have distinct symbols inside the cup. System reduced-motion settings keep it static.

### Activity

Filter the latest 200 loaded records by **All records / User actions / Automated processes**. Filtering preserves history and remains selected across refresh and appearance changes.

Quota recovery entries show attribution and balance changes; expand details for sample evidence. Attribution is inferred: credit use, scheduled reset, early recovery, or unknown source. It is not an official cause receipt. Credits are read-only and never redeemed automatically. The first sample establishes a baseline without reconstructing prior history. See [0.3.3 notes](releases/0.3.3.md) for attribution limits.

### Operating rules

| Setting | Default | Range |
| --- | --- | --- |
| Pause threshold | 10% | 1–50% |
| Resume threshold | 20% | 5–95%, at least 5 points above pause |
| Normal collection | 30 s | 10–300 s |
| Near-limit collection | 10 s | 5–60 s, no longer than normal |
| Recovery confirmation | 5 s | 3–60 s |
| UI refresh | 5 s | 2–30 s |

Changes apply after saving. Collection time is additional; connection failures use retry delays. UI refresh reads the cache. Service quota and reset times are read-only. Conflicting saves retain drafts for review or reload.

### Settings and quitting

Choose Chinese/English, system/light/dark appearance, and four accent colors. Notifications cover pause, resume, failed delivery, and actionable errors. Turning them off does not stop execution.

Closing the window keeps the app in the menu bar or tray. Use **Quit TokenMax** (**Quit** on Windows), or ⌘Q on Mac, to stop its background work. Quitting does not intentionally interrupt Codex tasks.

Keep-awake prevents idle sleep, not manual sleep or guaranteed operation with the lid closed. The Mac preview does not enable the closed-lid helper. Ordinary control needs no Accessibility, Screen Recording, or Full Disk Access; protected project folders may still require system consent.

### Upgrade and troubleshoot

Quit the previous version before upgrading. On Mac, install `TokenMax.app`, then remove the old `Codex Mission Manager.app`; do not run both. Windows retains the existing installation location. Settings, tasks, and history are preserved.

For connection issues, inspect client status in Settings, confirm sign-in, and check again. Unknown client versions need a compatibility update. A persistent connecting state is not normal operation.

Data remains in `~/Library/Application Support/CodexMissionManager` on Mac and `%LOCALAPPDATA%\CodexMissionManager` on Windows. It may contain account and chat information; do not upload it publicly without review. Uninstalling preserves this data by default.
