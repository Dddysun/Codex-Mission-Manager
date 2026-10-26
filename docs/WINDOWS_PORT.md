# Windows 原生移植与验收范围

V0.2.1 Windows 使用原生 WPF 窗口和共享 Python 后台，不使用 WebView。安装 EXE 携带固定版本 Python；系统要求为 Windows 10 x64 build 19041+、.NET Framework 4.8+。安装与私人数据均限当前用户。

[Windows 发行文件](https://github.com/Dddysun/Codex-Mission-Manager/releases) · [安装与卸载](../windows/INSTALL_README.md) · [界面还原说明](WINDOWS_UI_PARITY.md)

## 本轮更新

Windows 内容界面按当前 Mac 原生应用重新实现，包括深绿侧栏、品牌图标、底部账号与设置入口、面包屑、四项统计、来源与状态筛选、搜索、三列聊天列表、执行阶段、状态徽章、自动控制和一次性预约。设置为独立原生窗口，托盘为原生面板；浅色、深色、中英文共用同一套视觉层级。保留 Windows 的窗口装饰和系统字体，未分发 Apple 字体。

修复了复用聊天行时重复挂载到 WPF 逻辑树的异常、后台退出后无法重新连接的问题，并增加后台退出原因记录。应用图标复用项目现有 Mac 盾牌资产，替代此前的系统 UAC 图标。

官方客户端在 WindowsApps 目录的 CLI 直接启动可能被拒绝。本轮增加受限的定位方式：只允许注册包内文件，或与其 SHA-256 完全相同的客户端释放副本。每次后端重新解析命令时重新校验，默认不执行任意 PATH 候选；此改变没有放宽管道服务端 PID、包安装位置和用户 SID 校验。

## 程序功能

- 聊天目录、来源分类、搜索与状态筛选、当前状态和公开执行阶段。
- 服务实际返回的五小时、周或其他额度窗口、账号与订阅信息；未知额度和无固定窗口分别处理，不按套餐名称推断限额。
- 自动控制许可、额度恢复后的一次性预约、自定义指令、立刻执行及回执界面；保留原回合、账号、人工保持和防重复校验。
- 中英文、系统/浅色/深色、原生开关、操作记录和规则页。
- 托盘、关窗后后台运行、打开窗口、全局自动控制、暂停受管任务和退出。
- 可选的当前用户登录启动、托盘通知及防空闲睡眠；新安装默认关闭可选项并暂停全局自动控制。
- 每用户 EXE 安装器、便携 ZIP、桌面/开始菜单入口和卸载登记；更新保留上一版程序和私人数据，卸载默认保留配置与账本。

程序目录为 `%LOCALAPPDATA%\Programs\CodexMissionManager`，私人数据目录为 `%LOCALAPPDATA%\CodexMissionManager`。发行包不包含官方 ChatGPT、账号凭据或聊天历史。

界面每 5 秒读缓存；正常采集完成后等待 30 秒，临近阈值或有待执行预约时等待 10 秒。每轮采集、控制处理和异常退避耗时另计。

## 当前客户端适配与实机证据

官方客户端 `OpenAI.Codex 26.1021.3705.0` 已完成安装，用户确认登录。已只读核验官方包身份、版本、发行者，以及管道服务端同用户 SID 和安装位置。

本轮实机已完成 App Server 初始化、账号与五小时/周额度读取；对两个已有 Codex 聊天完成 owner 发现、版本 11 快照、公开执行阶段及模型设置读取。隔离账本下连续采集和停止后重启检查通过，均保持全局暂停，没有发送或中断真实聊天。

当前仅为 exact `26.1021.3705.0` 提供 Windows 兼容配置，后续版本不会自动继承。准入证据包括实际只读路径、Windows 假命名管道的控制 frame 回归，以及当前官方包内对应版本的消息结构。**兼容配置不等于真实暂停、续接或发送已通过验收；`live_control_tested` 仍为 false。** 未核验版本停止新的控制与发送，已有本地许可和预约仍可撤销。

最终 Windows 实机回归为 219 项，其中 215 项通过、4 项 Mac plist 专属测试跳过；6 项宿主测试通过。此前跳过的 10 项控制通信测试已改为 Windows 唯一假命名管道执行，不连接真实客户端。最终发行的具体测试数量、源提交和资产摘要以验收记录与构建结果为准。

界面离屏验收覆盖主窗口、设置、操作记录、规则、托盘和额度变体；主窗口为 1380×900 逻辑尺寸，2倍渲染与 Mac 同数据基准比对。所有公开预览仅含示例数据。

## 仍须单独验收或尚未提供的功能

- **真实动作：**真实暂停、续接、Goal 控制、立刻执行、预约送达和自然额度恢复闭环尚未完成实机动作验收；不能把离线 frame 测试计为真实发送通过。
- **普通 ChatGPT/云端聊天：**仅显示可用目录，没有普通聊天自动执行或完整云端历史同步。
- **通知：**使用托盘通知，尚未接入现代 Windows Toast/通知中心，也未声称系统通知投递授权已核验。
- **后台与合盖：**保活只防空闲睡眠，不修改系统电源计划，不保证合盖或手动睡眠后执行；未提供 Windows 特权合盖辅助服务。
- **发行：**未签名预览，无可信发布者签名或自动升级；外部错误与任务内容可保留其来源语言。
- **其他环境：**Windows 11、ARM64、多用户并行、登录启动，以及锁屏/熄屏/合盖下的完整发送流程仍需分别验收。卸载入口与数据保留契约已检查，未对用户当前安装副本执行破坏性卸载测试。

## 构建与历史记录

使用 `windows/build.ps1` 构建，脚本验证 `windows/python-runtime.lock.json` 中的官方 Python 摘要，调用系统 C# 编译器并生成 EXE、ZIP、manifest 和 `SHA256SUMS`。用户无需安装 Python、Node、.NET SDK 或修改系统执行策略。

`windows/run_tests.py` 使用隔离测试账本。`--self-test` 和 `--ui-self-test` 不启动真实任务；界面自检支持 `--view home|settings|activity|rules|tray`、`--language zh|en`、`--theme system|light|dark` 和 `--scale 1|2`。

[首发验证](windows-validation.json) 和 [此前交接时的只读记录](windows-handoff-validation.json) 保留历史时点：其中安装失败、CLI 拒绝访问或控制未开放的状态不代表本轮修复后的状态。当前构建和部署证据见 [本轮验收记录](windows-parity-validation.json)。

控制设计参考 MIT [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor)，许可证随包保留。此控制依赖客户端内部版本适配，不是 OpenAI 公开的客户端任务控制 API。安装参考 [OpenAI Windows 文档](https://learn.chatgpt.com/docs/app/windows)，运行环境参考 [Python 官方说明](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)。
