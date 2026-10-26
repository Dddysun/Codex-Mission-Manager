# Windows 本机 agent 交接 · 任务管家 V0.2.1

更新时间：2026-10-26。本文是 Windows 构建工作的接续说明，不代表真实任务控制已经通过验收。用户最新要求是在 Windows 本机继续；Mac 侧停止后续构建与远程变更。

## 1. 接手目标和产品约束

继续完成 Codex Mission Manager 的 Windows 原生移植、客户端连接与真实控制验收，最后交付 EXE 安装包，并逐项说明剩余缺失功能。已有实现应优先复用，避免从头重写。

- 使用真正的 Windows 原生窗口；当前实现是 C# WPF，禁止改回网页或 WebView 包壳。
- 主窗口保留聊天目录、来源分类、执行阶段、当前状态、自动控制许可、自定义指令、保存并预约、立刻执行和操作记录。自动控制放在当前状态下面。
- 额度不足时暂停符合条件的已授权任务，额度可靠恢复后核对原会话再续接。手动安排的一次性指令可以针对并非本轮额度中断的聊天；发送需有回执和防重复校验。
- 额度按服务实际返回的五小时、周或其他窗口显示；不能按 Free/Plus/Pro 名称猜测配额，未知数据禁止发送。
- 界面读缓存每 5 秒；正常采集结束后等 30 秒，临近阈值或有待执行预约等 10 秒；采集耗时另计。当前策略暂停阈值剩余 ≤10%，恢复阈值 ≥20%，恢复需再次核验。
- 中英文、跟随系统/浅色/深色、托盘、关闭窗口后后台运行。面向公众的界面使用正式产品用语，不保留对开发者或特定用户说的话。
- 普通 ChatGPT/云端聊天目前只显示可用目录，不启用自动执行；用户已经明确接受这一边界。
- **安装只限当前账户。** 保留私人配置、账本和登录；不系统级预配、不改防火墙/Defender/执行策略/系统 PATH/系统电源计划，不从 Mac 搬认证信息。
- 应用相关源码、文档和发行产物同步到现有仓库，不能上传真实聊天、账号认证、SSH 资料或原始私人账本。

## 2. 仓库、版本与发行

- 仓库：<https://github.com/Dddysun/Codex-Mission-Manager>
- 当前程序源码基线：`6a995ff9dc3f4b48dd5603ff5518b7ae9736def8`。
- 先前交付文档提交：`fb5a0adb690371eee6e97399dfc6d1bca4e99c0a`；本次交接更新也是文档变更，未修正 CLI 或放开控制。
- Windows 公开发行：<https://github.com/Dddysun/Codex-Mission-Manager/releases/tag/v0.2.1-windows-preview.1>
- EXE：<https://github.com/Dddysun/Codex-Mission-Manager/releases/download/v0.2.1-windows-preview.1/Codex-Mission-Manager-0.2.1-windows-x64-setup.exe>
- 同页有便携 ZIP、`SHA256SUMS`、`build-manifest.json`。公开 EXE SHA-256：`c5460c264c79f137aebec1ee476f22304f9c97257d593443d5dc980c9d38af58`。
- 公开包由 GitHub 独立生成；目标电脑装的是相同代码的 Windows 本机构建 R3，构建摘要不同是已记录的事实，不能混用摘要。
- Windows 构建成功：<https://github.com/Dddysun/Codex-Mission-Manager/actions/runs/40244230683>。
- 共享后端的 Mac 回归构建成功：<https://github.com/Dddysun/Codex-Mission-Manager/actions/runs/40244230714>。不要修改或重装用户 Mac 上现有部署。

## 3. Windows 已有环境与位置

已核验环境为 Windows 10 Pro x64 build 19045、PowerShell 5.1、.NET Framework 4.8.1。原生编译器为 `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`。此前没有独立 Git、Node、.NET SDK 或真正的全局 Python；Python 商店别名不算运行环境。应用自带官方 Python 3.13.17 x64 embeddable，无需先安装这些开发工具。

- **程序：**`%LOCALAPPDATA%\Programs\CodexMissionManager\CodexMissionManager.exe`
- **自带 Python：**`%LOCALAPPDATA%\Programs\CodexMissionManager\runtime\python\python.exe`
- **已安装后端：**`%LOCALAPPDATA%\Programs\CodexMissionManager\backend`
- **私人数据：**`%LOCALAPPDATA%\CodexMissionManager`，含 `config.json`、`state\guardian.sqlite3`、日志和界面偏好。不要删除或发布。
- **已验证源码快照：**`%LOCALAPPDATA%\CodexMissionManagerBuild\source-r3`，仅供本次构建；不是完整 Git 工作树。正式开发请获取 GitHub 最新 main，先核对差异。
- **已有构建：**`%LOCALAPPDATA%\CodexMissionManagerBuild\build-r3`，含 `app`、EXE、ZIP、`build-work` 自检回执、`test-results` 和五个模拟原生渲染。
- **当前账户卸载登记：**`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexMissionManager`。
- 桌面已有 `任务管家.lnk`、Windows EXE 安装包，以及 `ChatGPT - Official Store.url`。开始菜单也有任务管家快捷方式。
- **本机检查证据：**`%LOCALAPPDATA%\CodexMissionManagerSetup\installed-host-check.json` 和 `readonly-client-probe.json`。前者是客户端安装前的历史启动检查，后者是本次最新只读探针。
- 只读探针脚本位于 `%USERPROFILE%\CodexMissionManager-readonly-client-probe.py`；脚本不能被当作已完成控制验收的证明。

此前安装器成功安装 75 个程序文件；桌面/开始菜单快捷方式及 HKCU 卸载入口均已核对。后台单次启动检查成功且已退出，没有留下本次新增的计划任务。最新客户端检查时没有运行中的任务管家进程；不要据此保证之后仍无进程，接手需重新核对。

## 4. 最新客户端状态：安装阻塞已经解除

用户已明确回复“已安装 ChatGPT 并登录”。随后只读核验确认：

- 当前用户已安装 `OpenAI.Codex` **26.1021.3705.0**，包状态正常，官方 ChatGPT 进程正在桌面 Session 1 运行。
- 发行者为 `CN=50BDFD77-8903-4850-9FFE-6E8522F64D5B`，包族 `OpenAI.Codex_2p2nqsd0c76g0`。
- 包目录为 `%ProgramFiles%\WindowsApps\OpenAI.Codex_26.1021.3705.0_x64__2p2nqsd0c76g0`。
- `%USERPROFILE%\.codex\auth.json` 存在。登录由用户确认；由于下述 CLI 启动失败，后台尚未成功读取账号和实时额度，不能冒称后端登录验证已过。
- `\\.\pipe\codex-ipc` 存在。从 SSH Session 0 进行 `DesktopIPC.start()` 成功，包括 `initialize` 响应及服务端程序位于已注册官方包、与当前用户 SID 相同的检查。
- 本次 `.codex\state_5.sqlite` 查询到的未归档会话样本为 0，管道候选会话为 0，因此**没有验证到真实会话快照**。已请用户在 Windows 打开一个已有 Codex/Work 聊天，无需发新消息；交接时尚无回复。普通 ChatGPT 聊天不能代替这个验收对象。
- 临时管道已关闭；本次未发送聊天、未中断回合、未修改生产代码或开启自动控制。

旧文档中的 `0x80073CF9 / 0x80070490` 是此前直接安装 MSIX 的历史错误，**不再是当前主卡点**。不要重复安装、重做商店条款确认或系统级预配。

## 5. 当前需要修复的实际问题：CLI 启动被拒绝

`compatibility.windows_client()` 目前选择包内 `app/resources/codex.exe`。本次通过该路径启动 `Rpc([cli, 'app-server'])` 时直接报 **PermissionError / WinError 5：拒绝访问**，尚未完成 App Server initialize，因此账号和额度读取也未通过。这是本次新增的实测问题，尚未修复。

同时观察到官方客户端正在运行自己释放的 CLI：

`%LOCALAPPDATA%\OpenAI\Codex\bin\2993767bd1dfb009\codex.exe`

这个缓存目录编号会随客户端变化，**不可硬编码为适配条件，也不能只凭文件名或目录可信就执行**。下一步建议：

1. 核对当前已注册包身份、版本和发行者。只读计算包内 CLI 与客户端释放副本的 SHA-256；目前两者摘要是否一致**尚未验证**。
2. 若摘要一致，设计受限的 CLI 定位回退：固定客户端缓存根，规范化路径，拒绝目录逃逸、任意 PATH 命中和摘要不符项；重新核对时不能静默使用过期版本。路径或摘要证据不足就保持不可用。
3. 此回退仅用于 stdio 账号/额度/历史读取子进程，**不得把缓存目录加入命名管道服务端白名单**。管道服务端仍必须来自已注册包且 SID 相同。
4. 用 `guardian.server_command(config)` 的隔离 `sqlite_home` 和 `log_dir` 启动读取进程，避免额外 App Server 干扰客户端已有数据库。先测 `--version`、initialize、`account/read(refreshToken=False)`、`account/rateLimits/read`；只在本机使用认证，不输出令牌或账号标识。
5. 检查任务管家是否读取到了正确账号和实际额度窗口；错误、数据过期和未登录必须明确显示。

不要通过修改 WindowsApps ACL、接管目录所有权、关闭安全检查或修改官方 EXE 解决执行拒绝。先用当前 Windows 本机 agent 的正常桌面执行环境复核，也要区分 SSH Session 0 限制与应用本身的问题。

## 6. 代码入口和兼容门禁

- `windows/MissionManager.cs`：原生 WPF、托盘、中英文与外观、聊天/阶段/预约/即时发送、界面缓存刷新及应用偏好。
- `windows/Installer.cs`、`build.ps1`、`app.manifest`、`python-runtime.lock.json`：当前用户 EXE/ZIP、安装与保留数据的卸载器。
- `backend/compatibility.py`：Windows 包与 CLI 发现、版本兼容配置。**当前 `WINDOWS_PROFILES = {}`**，因此已安装客户端仍显示 `update_required` 是预期门禁，不要把它当成安装失败。
- `backend/platform_support.py`：Windows 文件锁、进程存活检查、只读 SQLite URI、命名管道服务端 PID/路径/SID 校验。Windows 存活检查不能使用 `os.kill(pid, 0)`。
- `backend/desktop.py`：长度前缀 JSON 管道、初始化、owner/follow/snapshot、原生控制适配。
- `backend/rpc.py`：官方 Codex App Server stdio；`guardian.server_command()` 选择命令并隔离运行目录。
- `backend/guardian.py`、`control_policy.py`、`plans.py`、`immediate.py`：额度策略、持久化、一次性预约和发送防重复。
- `backend/ui.py`：仅本机 JSON 接口、后端控制门禁；不能只改界面解除禁用。`app_host.py` 管理独占后台实例及退出。
- `backend/catalog.py`、`stages.py`：目录和公开执行阶段，不是模型私有推理。

控制依赖**版本敏感的内部通信适配，并非 OpenAI 公开的客户端任务控制 API**。设计参考 MIT `cat2mao/codex-quota-monitor`，许可证已保留。候选协议为 initialize 0、owner 1、follow 1、snapshot 11、start-turn 2、interrupt-turn 4，Goal interrupt 3；当前 Windows 只实测 initialize，不能宣称其他版本均已验证。

在已打开的、用户拥有的 Codex/Work 会话上只读验证 owner、follow、snapshot、当前回合和公开阶段，并补有意义的 Windows 管道/控制回归后，才能考虑加入 exact `26.1021.3705.0` 配置。不能复用 Mac 的 build `20770/21828` 或以 initialize 成功放开任意 Windows 版本。

真实暂停、续接、立刻执行和一次性预约仍未实测。做会改变聊天的验收前，向用户说明具体测试会话和动作并获得明确测试授权；当前用户确认安装/登录不等于要求向任意会话发送测试消息。保留人工输入、审批、账号变化、回合变化和重复发送保护。

## 7. 已通过的测试与不要夸大的部分

- Windows 10 实机：后端总 204 项，**190 通过、14 项 Mac/Unix 专属测试跳过**，0 失败/错误；宿主 4 项通过。
- 原生、内置 Python、EXE 安装器自检通过；安装器 footer/内嵌 ZIP/CRC/摘要/运行时/许可证核验通过，未发现私人数据。
- 五个 WPF Content 模拟数据渲染通过，1420×960，与桌面分辨率无关；中文浅色和英文深色已经目视检查。没有采集真实桌面截图。
- 安装后后台接口启动通过，默认全局暂停，正常/临界采集 30/10 秒；结束后本次进程全部退出。
- 实机交互式打开主窗口、实际卸载、开机登录启动、锁屏/熄屏/合盖发送仍未验证。
- 新增证据见 [windows-handoff-validation.json](windows-handoff-validation.json)；此前测试/安装证据见 [windows-validation.json](windows-validation.json)。后者保留了**客户端安装前**的 `client_missing` 状态，不能当作最新事实。

## 8. 构建与交付方法

先在新的开发目录获取仓库，使用现有已安装 Python 运行测试，不需要全局 Python：

```powershell
$py = Join-Path $env:LOCALAPPDATA 'Programs\CodexMissionManager\runtime\python\python.exe'
& $py -X utf8 -I .\windows\run_tests.py --output .\test-output-windows
```

标准构建入口：

```powershell
.\windows\build.ps1 -OutputDirectory "$env:LOCALAPPDATA\CodexMissionManagerBuild\build-next"
```

构建脚本读取锁定的 Python 下载地址和摘要，使用系统 C#5 编译器生成原生程序、便携 ZIP、EXE、manifest 和校验清单。无需引入 Electron、WebView、Node 或 NuGet。已有输出请保留，优先新目录；`-Replace` 只允许标记过的本项目生成目录。

此前 `.ps1` 文件执行受本机 Restricted 策略限制；没有修改策略，也没有使用 `ExecutionPolicy Bypass`。Mac 侧通过已审阅脚本内容在获准 PowerShell 命令会话内执行构建，替换 `$PSScriptRoot` 为实际源码目录。接手者先遵守本机 agent 的命令审批方式，不要为构建降低系统执行策略。

后端/宿主通过后再进行 native `--self-test`、模拟渲染和安装器 `--self-test`；离线自检不应启动真实任务。打包时只包含代码、模板、运行时及许可证，不能包含 `backend/config.json`、auth、私人 ledger 或真实 UI 数据。

更新前核对运行中的任务管家和文件修改，正常退出自己的后台，再使用当前用户安装器更新并确认私人数据仍在。Windows 流水线为 `.github/workflows/build-windows.yml`；共享后端也需 Mac 回归。现有 Mac 工作流通过提交消息中的 `[windows-port]` 跳过 Mac 发行步骤而保留回归构建，Windows 专项代码提交应沿用此前缀，避免连带发布 Mac 包；纯文档提交可用 `[skip ci]`。源码与发行同步已有仓库，不另建仓库，不改写历史。

## 9. 仍须如实列出的产品缺口

1. CLI 拒绝访问待修复；真实账号额度读取、会话快照及 Windows 控制配置待验收。
2. 自动暂停/续接、即时发送、预约真实送达及自然额度恢复闭环未通过实机测试。
3. 普通 ChatGPT/云端聊天仅目录，不提供自动执行或完整云端历史同步。
4. 当前为托盘气泡通知，尚无现代 Windows Toast/通知中心集成及真实投递许可验收。
5. 可选保活只防空闲睡眠，没有 Windows 特权合盖服务，不保证合盖或手动睡眠后执行，不修改系统电源策略。
6. 未签名预览，无自动升级；外部原始错误和任务内容可能保留其来源语言。
7. Windows 11、ARM64、多用户并行、登录启动、交互窗口打开及锁屏/熄屏/合盖送达仍需单独验收。

**接手第一轮：核对源码和进程 → 复核 CLI 执行环境与摘要 → 修复受限定位并测账号/额度 → 在已有 Work 会话只读验 snapshot → 再安排明确授权的控制验收。不要从重装 ChatGPT 开始。**
