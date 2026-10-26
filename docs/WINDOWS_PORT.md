# Windows 原生移植与验收范围

V0.2.1 Windows 预览使用原生 WPF 窗口和共享 Python 后台，不使用 WebView。安装 EXE 携带固定版本的 Python 运行环境；Windows 10 x64（build 19041+）和 .NET Framework 4.8+ 是系统要求。安装与数据均限当前用户。

[下载 EXE 安装器](https://github.com/Dddysun/Codex-Mission-Manager/releases/download/v0.2.1-windows-preview.1/Codex-Mission-Manager-0.2.1-windows-x64-setup.exe) · [完整发行文件和 SHA-256](https://github.com/Dddysun/Codex-Mission-Manager/releases/tag/v0.2.1-windows-preview.1) · [可复核验收记录](windows-validation.json)

**2026-10-26 最新接续状态：**用户已完成官方客户端安装并确认登录。`26.1021.3705.0` 在桌面运行，只读管道 initialize 及同用户/官方包位置校验成功。包内 CLI 直接启动报 `WinError 5`，真实账号额度读取和会话快照仍待验收，控制尚未开放。详见 [Windows 本机 agent 交接](WINDOWS_HANDOFF.md) 与 [最新只读证据](windows-handoff-validation.json)；下文客户端安装失败和 `client_missing` 为此前历史检查。

## 已移植的程序功能

- 聊天列表、来源筛选、搜索分页、当前状态和公开执行阶段。
- 五小时、周及服务实际返回的其他额度窗口，账号和订阅信息；保留无固定窗口和未知额度的区别。
- 自动控制许可、一次性预约、自定义指令、立刻执行及回执界面。共享后台保留原回合、账号、人工保持和防重复发送校验。
- 中英文界面、系统/浅色/深色外观、左右滑块、操作记录和运行规则。
- 系统托盘、关窗后继续运行、打开窗口、全局自动控制、暂停已授权任务和退出入口。
- 用户自行开启的登录启动、动作通知和防空闲睡眠选项；新安装默认关闭可选设置并暂停自动控制。
- 当前用户 EXE 安装器、便携 ZIP、桌面与开始菜单入口、应用和功能中的卸载入口。更新保留旧程序备份；卸载默认保留私人配置和账本。

程序位于 `%LOCALAPPDATA%\Programs\CodexMissionManager`，私人数据位于 `%LOCALAPPDATA%\CodexMissionManager`。官方 ChatGPT、登录凭据和聊天历史不随包分发，不从其他电脑复制账号认证。

## 实现与真实可用性的区别

Windows 控制使用本机命名管道，连接前检查服务端程序位置和用户身份。兼容配置与 macOS 分开；未经核验的 Windows 客户端版本只允许只读采集，不开放新的控制许可或发送。已有自动许可可关闭，已有预约可在同账号缓存可核实时取消；不能借撤销操作获得发送权限。

当前 Windows 兼容表尚无已实机核验的客户端版本，因此这个首发预览不会启用真实任务控制。下面列出的控制界面和共享后台逻辑均已移植；在官方客户端安装、登录及协议验收完成后，仍需更新兼容配置才能开放。

首轮验收时，目标电脑的官方 ChatGPT 当前用户安装遇到 Windows 包注册错误。用户随后完成安装并确认登录，管道初始化已通过；Windows 的真实账号额度读取、会话快照、自动暂停/续接、即时发送及预约送达仍未通过实机验收。对应程序逻辑已移植，但不能将离线回归或界面渲染当作这些路径已实际可用。

## 与 macOS 的差异和未完成项

- **真实控制验收待完成：**官方 Windows ChatGPT 安装与用户确认登录已完成；仍需解决 CLI 读取启动问题，并验证当前版本会话状态和控制能力。未验证时程序停止发送。
- **普通 ChatGPT/云端聊天：**保留只读目录能力，不提供自动执行；也未新增完整云端目录同步。这是共享后端原有边界。
- **通知：**当前采用原生托盘通知，未实现现代 Windows Toast/通知中心集成；应用通知开关不等于已自动核验系统通知投递许可。
- **后台与合盖：**保活选项只防空闲睡眠，不修改系统电源计划，也不保证合盖或手动睡眠后执行。macOS 管理员合盖辅助服务不适用于 Windows；没有新增对应 Windows 特权服务。
- **发行：**当前 EXE 为未签名预览，未提供可信发布者签名或自动更新。主界面有中英文；外部错误、任务内容和后端原始说明可能保留来源语言。
- **验收环境：**目前针对 Windows 10 x64；Windows 11、ARM64、多用户并行运行、登录启动、锁屏/熄屏/合盖发送完整流程仍需分别验证。
- **桌面操作与卸载：**已验证安装后后台启动和接口访问，原生窗口已完成模拟数据渲染；交互式窗口打开尚未实测。每用户卸载入口已注册，安装器的数据保留契约已检查，尚未对当前安装副本执行实际卸载。

## 构建与验证

在 Windows 使用仓库的 `windows/build.ps1` 构建。脚本调用系统 .NET Framework C# 编译器，验证 `windows/python-runtime.lock.json` 中的 Python 官方摘要，然后生成原生程序、便携 ZIP、EXE 安装器及 `SHA256SUMS`。

`windows/run_tests.py` 使用隔离账本执行共享后端与宿主回归，记录测试总数、失败和平台跳过情况。Unix 套接字和 Mac plist 专属测试在 Windows 跳过，不能计作 Windows 通过。原生 `--self-test`、四种模拟订阅的 `--ui-self-test` 以及安装器 `--self-test` 均不启动真实任务或发送聊天。

2026-10-26 的 Windows 10 x64 实机验收：后端总计 204 项，其中 190 项通过、14 项平台专属测试跳过；4 项宿主测试通过。原生应用、嵌入 Python 和安装器自检通过；5 个原生界面模拟数据渲染通过，已检查中文浅色和英文深色布局。

任务管家已按当前用户安装成功，桌面安装包、程序快捷方式、开始菜单和 HKCU 卸载入口均已核对。安装后的单次后台检查确认接口可访问、采集间隔 30/10 秒、自动控制默认暂停；因客户端缺失，`healthy=false`、`control_available=false`。检查结束后本次进程退出，没有留下新增的计划任务，也没有发送真实聊天指令。

源码提交 `6a995ff9dc3f4b48dd5603ff5518b7ae9736def8` 已完成 [Windows 独立构建](https://github.com/Dddysun/Codex-Mission-Manager/actions/runs/40244230683) 与 [Mac 回归构建](https://github.com/Dddysun/Codex-Mission-Manager/actions/runs/40244230714)。公开 EXE/ZIP 的下载摘要、安装器嵌入载荷和文件完整性核验通过。实机安装使用同一代码的本机构建；公开资产由 GitHub 独立生成，两者摘要分别记录，不能混用。

完整结果见 [windows-validation.json](windows-validation.json)。Mac 的历史验收记录不作为 Windows 实机证据。

## 官方客户端安装的历史阻塞

官方签名包 `26.1021.3705.0` 在目标设备按当前用户安装失败，错误为 `0x80073CF9`，扩展错误为 `0x80070490`。未发现可直接注册的已暂存安装。其最低 Windows 版本符合设备，不能仅据此判定 Windows 10 不受支持，唯一根因尚未确认。

此前已提供 Microsoft Store 路径，由用户本人处理条款、安装和登录。用户现已确认安装并登录，包安装和运行已只读核实；本次未独立确认用户最终使用的安装路径或此前错误的根因。此项目未执行系统级预配、修改或重新签名官方包，也未关闭安全校验。后续仍需完成额度读取与会话协议核验，再发布明确适配的 Windows 兼容配置；安装成功本身不等于自动控制已通过验收。

控制协议设计参考 MIT [cat2mao/codex-quota-monitor](https://github.com/cat2mao/codex-quota-monitor)，许可证随包保留。客户端安装参考 [OpenAI Windows 文档](https://learn.chatgpt.com/docs/app/windows)，嵌入运行环境参考 [Python 官方说明](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)。
