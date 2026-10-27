# Release process / 发行流程

## One version, two platforms / 一个版本、两个平台

`VERSION` is the product-version source of truth. Both build scripts and the unified GitHub workflow read it. Release notes live at `docs/releases/<VERSION>.md`. Preview tags use `v<VERSION>-preview.<GITHUB_RUN_NUMBER>` and reference the exact source commit. The run number is not assumed in documentation.

产品版本统一读取 `VERSION`，两平台脚本与 GitHub 工作流使用同一来源。发行说明位于 `docs/releases/<VERSION>.md`。预览标签采用 `v<VERSION>-preview.<GITHUB_RUN_NUMBER>`，指向准确源码提交；文档不预设构建流水号。

## Before publishing / 发布前

1. Update the central version, release notes, user guide, and changelog together. Check supported client profiles against actual evidence; a connection check must not be described as live-control acceptance.
2. Run `python3 scripts/check_source.py` and the relevant isolated checks in [BUILDING.md](BUILDING.md). Review source and package contents for credentials, personal chat data, logs, and generated state.
3. Verify that rules, accent choices, filenames, and bundled runtimes match the source. Keep dependency licenses in the package. Do not silently replace a pinned runtime.
4. Record checks as passed, failed, or skipped. Publish interactive and live-control limitations with the release rather than inferring them from successful builds.

发布前同步更新中央版本、发行说明、使用指南和版本记录；检查兼容配置与实际证据一致。运行源码检查及相关隔离测试，确认不含凭据、个人聊天、日志或运行状态。核对规则、主题色、文件名、运行环境和许可证，并如实记录通过、失败及跳过项目。

## Unified workflow / 统一工作流

The [release workflow](../.github/workflows/release.yml) runs on selected changes pushed to `main`, or through **Run workflow** in GitHub Actions. It performs the following stages:

1. **Prepare:** validate `VERSION` and required documentation; derive the preview tag.
2. **macOS:** fetch the pinned runtime, run the full isolated backend/host suite and native contracts, build the app, check native marked-text handling, render fixture pages when a window server is available, then create and verify the DMG.
3. **Windows:** build the native app and current-user EXE, check payload integrity, run limited Windows platform/host smoke checks, native editor/lifecycle checks, and fixture renders. This is not full Windows acceptance testing.
4. **Publish:** require both platform jobs, verify version/commit metadata, combine artifacts and reports, generate and verify one `SHA256SUMS`, create a new immutable preview tag, and publish one GitHub prerelease with both platforms.

[统一工作流](../.github/workflows/release.yml) 在 `main` 的指定路径更新后或通过 GitHub Actions 手动触发。它先核验版本与文档，再分别构建 Mac 和 Windows，最后仅在两平台任务均成功时合并文件、校验来源和摘要、创建新标签并发布同一预发行。Mac 执行完整隔离后端／宿主测试；Windows 执行有限的平台／宿主冒烟测试，不能称为完整 Windows 验收。无窗口服务时，Mac 界面渲染应明确记录跳过。

Published tags and assets are not overwritten. Rerunning an already published run must not use forced tags, asset replacement, or checksum changes. A correction requires a new workflow run and a new preview tag; increase `VERSION` when the product version changes.

不覆盖已发布标签和文件。修正发行应创建新的工作流运行及预览标签；产品版本变化时再更新 `VERSION`，不要强制移动标签或替换同名发行文件。

## Release contents / 发行文件

For V0.3.1 the user-facing packages are:

- `Codex-Mission-Manager-0.3.1-arm64-preview.dmg`
- `Codex-Mission-Manager-0.3.1-windows-x64-setup.exe`
- `Codex-Mission-Manager-0.3.1-windows-x64-preview.zip`

The same release includes platform build manifests, verification/self-test receipts, `USER_GUIDE.md`, and `SHA256SUMS`. Manifests identify the version, architecture, bundled runtime, source commit, and signing state. Test receipts describe their own scope; packaging success does not prove live delivery.

同一发行附带平台构建清单、验证／自检回执、使用指南和统一校验摘要。清单记录版本、架构、运行环境、源码提交及签名状态；回执只证明其声明的验证范围。

On Mac, compare `shasum -a 256 <downloaded-file>` with `SHA256SUMS`. On Windows, use `Get-FileHash -Algorithm SHA256 <downloaded-file>`. Matching checksums verify the downloaded bytes against the published summary; they are not Developer ID, Apple notarization, or Authenticode signatures.

Mac 可用 `shasum -a 256 <下载文件>`，Windows 可用 `Get-FileHash -Algorithm SHA256 <下载文件>`，与发行中的摘要比较。摘要一致不代表具备正式发行签名或 Apple 公证。

Use the repository's [Releases page](https://github.com/Dddysun/Codex-Mission-Manager/releases) for preview downloads. GitHub's `/releases/latest` can exclude prereleases and must not be used as the preview download target.

预览下载指向 [Releases 页面](https://github.com/Dddysun/Codex-Mission-Manager/releases)；`/releases/latest` 可能排除预发布，不用作预览下载入口。

## Signing and manual acceptance / 签名与人工验收

Current preview builds are ad-hoc signed and unnotarized on Mac, and unsigned on Windows. Formal signing is a separate release capability. Do not describe a preview as signed, notarized, installed, or live-tested based on a successful CI build.

Manual acceptance must separately cover clean installation and upgrade, real client login and compatibility, Run now with a confirmed receipt, quota-triggered pause and recovery, one-time scheduling, manual input/approval/hold priority, notifications and login startup, real menu-bar/tray reopen, and sleep/display/lock/lid behavior. Include Chinese keyboard composition under repeated refresh on Mac. Record the exact OS and client version and redact private data from evidence.

当前 Mac 预览采用临时签名且未公证，Windows 预览未签名。正式签名、安装及实机控制验收各自独立。人工验收需覆盖首次安装／升级、真实客户端登录兼容、即时发送回执、额度暂停恢复、一次性预约、人工接管优先级、通知与登录启动、真实菜单栏／托盘重开，以及睡眠、熄屏、锁屏和合盖行为；Mac 还需复验真实中文键盘组合输入。记录准确系统和客户端版本，证据对外发布前脱敏。
