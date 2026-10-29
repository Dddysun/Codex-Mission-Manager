# Build from source / 从源码构建

Release packages include the native interface, Python backend, pinned Python runtime, and third-party notices. End users do not need development tools. Build on the target operating system; cross-compilation is not provided.

发行包包含原生界面、Python 后端、固定版本 Python 运行环境及第三方声明。使用者无需开发工具。请在目标操作系统构建，目前不提供交叉编译。

## Source and version / 源码与版本

Clone [Codex-Mission-Manager](https://github.com/Dddysun/Codex-Mission-Manager), then run the commands below from the repository root. For an existing release, check out its exact preview tag before building. `VERSION` is the common product version; `GITHUB_RUN_NUMBER` supplies the preview build number in CI. Local builds default to build 1.

克隆仓库后，在仓库根目录运行以下命令。重建已发行版本时先切换到对应预览标签。两平台产品版本统一读取 `VERSION`；CI 的预览构建号来自 `GITHUB_RUN_NUMBER`，本地默认构建号为 1。

```sh
git clone https://github.com/Dddysun/Codex-Mission-Manager.git
cd Codex-Mission-Manager
```

## macOS

Requirements: Apple Silicon Mac, macOS 14 or later, Apple Command Line Tools with Swift and the macOS SDK, and Python 3 for the build scripts. The packaged runtime is CPython 3.12.15 for arm64, pinned with SHA-256 in `packaging/python-runtime.lock.json`. Downloading the runtime requires network access. No pip packages are needed.

构建环境需要 Apple Silicon Mac、macOS 14 或更新版本、包含 Swift 与 macOS SDK 的 Apple Command Line Tools，以及用于运行构建脚本的 Python 3。随包运行环境为 arm64 CPython 3.12.15，版本与 SHA-256 固定于 `packaging/python-runtime.lock.json`。首次下载需要联网，不需要安装 pip 依赖。

Use new output directories for each build. / 每次构建使用新的输出目录。

```sh
python3 scripts/fetch_runtime.py --destination /tmp/tokenmax-python-040
python3 scripts/build.py --python-runtime /tmp/tokenmax-python-040/python --output /tmp/tokenmax-macos-040
python3 scripts/make_dmg.py --build /tmp/tokenmax-macos-040
python3 scripts/verify_dmg.py /tmp/tokenmax-macos-040/TokenMax-0.4.0-arm64-preview.dmg --report /tmp/tokenmax-macos-040/verification.json
```

The build produces `TokenMax.app`, the arm64 preview DMG, `build-manifest.json`, and `SHA256SUMS`. The interface is compiled from SwiftUI/AppKit sources. The runtime is copied into the application; global Python, user packages, and private runtime configuration are not included. The DMG check mounts read-only and runs isolated self-tests without installing the application or controlling live chats.

构建生成原生 `.app`、arm64 预览 DMG、构建清单及校验摘要。运行环境随应用复制，不包含系统 Python、用户扩展包或私人运行配置。DMG 检查采用只读挂载和隔离自检，不安装应用、不控制真实聊天。

Without signing configuration, the build uses ad-hoc signing and disables the privileged helper. For a Developer ID build, supply both `MISSION_TEAM_ID` and `MISSION_SIGN_IDENTITY` using a configured local keychain. Do not commit certificates or secrets. The build does not notarize automatically; notarization and stapling require a separate verified release process. The current public preview remains unnotarized.

未配置正式签名时，构建使用本机临时签名并停用管理员辅助服务。Developer ID 构建需通过已配置的本机钥匙串同时提供 `MISSION_TEAM_ID` 和 `MISSION_SIGN_IDENTITY`，不要提交证书或密钥。构建脚本不会自动公证；公证及装订需另行核验。当前公开预览未经过 Apple 公证。

## Windows

Requirements: Windows 10 build 19041 or later, x64, Windows PowerShell 5.1, and .NET Framework 4.8 or later with its x64 C# compiler and WPF assemblies. A .NET SDK, Visual Studio, Node.js, and a global Python installation are not required by the packaging script.

构建环境需要 Windows 10 build 19041 或更新版本、x64、Windows PowerShell 5.1，以及具备 x64 C# 编译器和 WPF 程序集的 .NET Framework 4.8 或更新版本。打包脚本不要求 .NET SDK、Visual Studio、Node.js 或全局 Python。

```powershell
.\windows\build.ps1 -OutputDirectory .\dist\windows-040
```

The script downloads the official CPython 3.13.17 x64 embeddable ZIP and verifies the SHA-256 in `windows/python-runtime.lock.json`. To use an already downloaded matching archive:

脚本下载官方 CPython 3.13.17 x64 嵌入式 ZIP，并核验锁文件中的 SHA-256。也可指定已下载且校验一致的归档：

```powershell
.\windows\build.ps1 -PythonArchive .\downloads\python-3.13.17-embed-amd64.zip -OutputDirectory .\dist\windows-040-offline
```

Outputs include the WPF application, a current-user setup EXE, a portable ZIP, `build-manifest.json`, and `SHA256SUMS`. WinForms is used for native tray integration and the installer; the main interface is WPF. Python is bundled; .NET Framework remains a Windows prerequisite. The current script creates an unsigned preview. The installer self-test verifies its embedded payload without installing it.

输出包括 WPF 应用、当前用户安装 EXE、便携 ZIP、构建清单及校验摘要。主界面使用 WPF；托盘集成和安装器使用 WinForms。Python 随包提供，.NET Framework 由 Windows 环境提供。当前脚本生成未签名预览；安装器自检仅校验内置载荷，不执行安装。

## Isolated checks / 隔离检查

Run checks against synthetic fixtures, outside an installed application's data directory. The test runner creates and removes a disposable sample configuration only when one does not already exist. Use a clean checkout for release validation.

检查使用示例数据，不应指向已安装应用的数据目录。测试运行器仅在不存在配置时创建并删除临时示例配置；发行验证应使用干净源码副本。

```sh
python3 scripts/check_source.py
python3 windows/run_tests.py --scope full --output /tmp/tokenmax-tests-040
swiftc -swift-version 5 -parse-as-library native/Localization.swift native/NativeState.swift tests/NativeContractTests.swift -o /tmp/tokenmax-native-contract-040
/tmp/tokenmax-native-contract-040 tests/fixtures/native-state.json
```

The first two commands are portable; the Swift contract check requires macOS. On Windows, use the packaged interpreter for the limited platform/packaging checks:

前两项可跨平台运行；Swift 契约检查需要 macOS。Windows 可使用刚打包的解释器执行有限的平台与宿主检查：

```powershell
& .\dist\windows-040\app\runtime\python\python.exe -X utf8 -I .\windows\run_tests.py --scope smoke --output .\dist\windows-040-checks
```

Native self-tests and fixture-render options are exercised by [the release workflow](../.github/workflows/release.yml). Fixture renders and editor/lifecycle checks start no live backend and send no chat messages. GUI rendering depends on an available desktop/window server; unavailable checks must be recorded as skipped. See [release validation](releases/0.4.0.md) for the distinction between offline checks and live acceptance.

原生自检、界面渲染和编辑器／窗口生命周期检查由 [发行工作流](../.github/workflows/release.yml) 执行。示例渲染不启动真实后台、不发送聊天消息。图形渲染依赖可用桌面或窗口服务，无法执行时须记录为跳过。离线检查与实机验收的区别见 [发行说明](releases/0.4.0.md)。
