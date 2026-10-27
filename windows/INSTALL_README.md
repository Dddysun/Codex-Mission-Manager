# Codex Mission Manager — Windows preview

The setup EXE installs the native WPF application, its Python backend and the pinned Python runtime for the current Windows user. Python, Node.js and a .NET SDK do not need to be installed separately. Windows must provide .NET Framework 4.8 or later.

安装 EXE 将原生 WPF 窗口、后端及固定版本 Python 运行环境安装到当前用户目录，无需另装 Python、Node.js 或 .NET SDK。Windows 需具备 .NET Framework 4.8 或更高版本。

## Install / 安装

Run `Codex-Mission-Manager-0.3.0-windows-x64-setup.exe`, select **Install**, then open **任务管家** from the desktop or Start menu. The default application directory is `%LOCALAPPDATA%\Programs\CodexMissionManager`.

运行安装 EXE，点击“安装”，然后从桌面或开始菜单打开“任务管家”。默认程序目录为 `%LOCALAPPDATA%\Programs\CodexMissionManager`。

Install and open the application normally with your Windows account. **Run as administrator** is not required. The backend checks that its data folder is writable before starting; it does not request elevation or automatically change folder permissions. If access is denied, check the current user's access to the displayed application data folder.

请使用当前 Windows 账户正常安装和打开，无需“以管理员身份运行”。后台启动前会检查应用数据目录是否可写，不会自动提权或重置目录权限。如提示无法访问，请检查当前用户对提示中应用数据目录的访问权限。

The application requires a compatible official Codex desktop client and the user's own sign-in. Credentials and chat histories are not included in the distribution. New installations start with global automatic control paused; check the displayed account and chats before enabling it.

应用需要兼容的官方 Codex 桌面客户端及用户本人登录。发行包不含凭据或聊天历史。首次安装默认暂停全局自动控制，请核对账号及聊天后再启用。

## Background behavior / 后台行为

Closing the main window keeps the app in the system tray. Use **Quit** in the tray menu to stop the app-owned background process. Quitting Mission Manager does not intentionally interrupt chats in the official client.

关闭主窗口后应用继续在托盘运行。通过托盘菜单“退出”停止应用自己的后台；退出管家不主动中断官方客户端中的聊天。

By default, the UI reads cached state every 5 seconds. Normal collection waits 30 seconds after each round; near-limit or pending-plan collection waits 10 seconds. These intervals and the pause/resume thresholds are editable in Operating Rules. Processing time is additional.

默认界面每 5 秒读取缓存；正常采集完成后等待 30 秒，临近阈值或存在待执行预约时等待 10 秒。以上间隔及暂停、恢复阈值可在运行规则中设置；每轮处理耗时另计。

## Data and upgrades / 数据与更新

Private configuration, ledger and native preferences live separately at `%LOCALAPPDATA%\CodexMissionManager`. The installer preserves this directory and retains the preceding application directory when updating. Quit Mission Manager before installing an update. The portable ZIP contains the same program files and runtime; extract it to a dedicated application folder before opening `CodexMissionManager.exe`.

私人配置、账本及界面偏好独立保存在 `%LOCALAPPDATA%\CodexMissionManager`。安装器保留此目录；更新时也保留上一版程序目录。更新前请先退出管家。便携 ZIP 包含相同程序及运行环境，解压到专用目录后打开 `CodexMissionManager.exe`。

## Uninstall / 卸载

Quit Mission Manager from its tray menu, then find **任务管家 · Codex Mission Manager** in Windows **Apps & features / Installed apps** and select **Uninstall**. The per-user uninstaller removes this installation and its matching shortcuts/startup entry. It preserves `%LOCALAPPDATA%\CodexMissionManager`, official Codex sign-in data, other applications and preceding application backups. A small cleanup program may remain in the Windows temporary folder after self-removal.

先从托盘菜单退出管家，再在 Windows“应用和功能／已安装的应用”中找到“任务管家 · Codex Mission Manager”并卸载。每用户卸载器仅移除此程序及目标匹配的快捷方式、启动项，保留 `%LOCALAPPDATA%\CodexMissionManager` 数据、官方 Codex 登录数据、其他应用和之前保留的程序备份。自删除后，Windows 临时目录中可能保留一个小型清理程序。

This is an unsigned preview. No installer step changes firewall rules, antivirus, execution policy, system PATH or system power settings. Refer to `USER_GUIDE.md`, when included, for verified capabilities and remaining limitations.

当前为未签名预览版。安装器不会修改防火墙、防病毒、执行策略、系统 PATH 或系统电源设置。已验证能力及剩余限制见随包提供的 `USER_GUIDE.md`。
