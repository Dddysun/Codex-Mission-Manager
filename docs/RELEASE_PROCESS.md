# Release process / 发行流程

## One version, two platforms / 一个版本、两个平台

`VERSION` is the product-version source of truth. Both build scripts and the unified GitHub workflow read it. Release notes live at `docs/releases/<VERSION>.md`. Preview tags use `v<VERSION>-preview.<GITHUB_RUN_NUMBER>` and reference the exact source commit. The run number is not assumed in documentation.

产品版本统一读取 `VERSION`，两平台脚本与 GitHub 工作流使用同一来源。发行说明位于 `docs/releases/<VERSION>.md`。预览标签采用 `v<VERSION>-preview.<GITHUB_RUN_NUMBER>`，指向准确源码提交；文档不预设构建流水号。

## Before publishing / 发布前

1. Update the central version, release notes, user guide, and changelog together. Check supported client profiles against actual evidence; a connection check must not be described as live-control acceptance.
2. Run `python3 scripts/check_source.py` and the relevant isolated checks in [BUILDING.md](BUILDING.md). Review source and package contents for credentials, personal chat data, logs, and generated state.
3. Verify that rules, accent choices, filenames, and bundled runtimes match the source. Keep dependency licenses in the package. Do not silently replace a pinned runtime.
4. Record checks as passed, failed, or skipped. Publish interactive and live-control limitations with the release rather than inferring them from successful builds.
5. Add an explicit entry for this `VERSION` in `docs/release-gallery.json`, with selected native-render filenames, receipts, dimensions, bilingual captions, and at least one release highlight. Run `python3 -m unittest discover -s tests -p test_release_gallery.py -v`. A new version cannot silently inherit the previous gallery.

发布前同步更新中央版本、发行说明、使用指南和版本记录；检查兼容配置与实际证据一致。运行源码检查及相关隔离测试，确认不含凭据、个人聊天、日志或运行状态。核对规则、主题色、文件名、运行环境和许可证，并如实记录通过、失败及跳过项目。

每个新 `VERSION` 还必须在 `docs/release-gallery.json` 显式配置预览图、回执、尺寸、中英文说明及本次重点，并通过图库测试；不能自动沿用上一版重点。

## Unified workflow / 统一工作流

The [release workflow](../.github/workflows/release.yml) runs on selected changes pushed to `main`, or through **Run workflow** in GitHub Actions. It performs the following stages:

1. **Prepare:** validate `VERSION` and required documentation; derive the preview tag.
2. **macOS:** fetch the pinned runtime, run the full isolated backend/host suite and native contracts, build the app, check native marked-text handling, render fixture pages when a window server is available, then create and verify the DMG.
3. **Windows:** build the native app and current-user EXE, check payload integrity, run the full isolated backend and packaging-host suites, native brand parity checks, native editor/lifecycle checks, and fixture renders. Offline coverage does not replace live Windows acceptance testing.
4. **Gallery:** each platform stages only its configured PNGs and offline-render receipts. The publisher checks both build manifests, validates the selected images and receipts, and generates the gallery assets and release-note section.
5. **Publish:** require both platform jobs and every selected gallery image, combine packages, reports, images, and gallery metadata into one verified `SHA256SUMS`, create a new immutable preview tag, upload to a draft, verify every asset, then publish one GitHub prerelease with both platforms and illustrated notes.

[统一工作流](../.github/workflows/release.yml) 在 `main` 的指定路径更新后或通过 GitHub Actions 手动触发。它先核验版本、文档和图库配置，再分别构建 Mac 和 Windows，最后仅在两平台任务及所有必选预览图均成功时合并文件、校验来源和摘要、创建新标签并发布附图说明。Mac 执行完整隔离后端／宿主测试；Windows 执行完整隔离后端／宿主测试；离线结果不能称为完整 Windows 实机验收。无窗口服务或缺少必选图时如实记录，并阻止该次发行。

Assets are uploaded to a draft first. Missing, incomplete, or mismatched uploads leave the draft unpublished, rather than exposing notes with unavailable images.

所有文件先上传到发行草稿，逐项核对后才公开；上传失败或不匹配时保留未公开草稿，避免发布缺图说明。

Published tags and existing assets are not overwritten. Product corrections require a new workflow run and a new preview tag; increase `VERSION` when the product version changes. Adding validated gallery assets and updating only the managed gallery section of existing notes is permitted through the separate workflow below. It must preserve the original packages, tag, and `SHA256SUMS`.

不覆盖已发布标签和文件。产品修正应创建新的工作流运行及预览标签；产品版本变化时更新 `VERSION`。允许通过下述专用流程追加已验证图库，并仅编辑说明中的图库标记段，原安装包、标签及 `SHA256SUMS` 必须保留。

## Release previews / 发行预览图

Starting with V0.3.1, illustrated release notes cover both platforms and at least four page types, with this release's changes shown first. The V0.3.1 selection contains six images: Mac menu Quit, Windows tray Quit, both main windows, Mac operating rules, and Windows settings. The two Quit panels are prominent; routine pages are collapsible. The activity page is not part of this selection, and repeated accent variants are omitted.

从 V0.3.1 起，每次发行说明均展示两平台、至少四类页面的预览图，并优先显示本次新增内容。V0.3.1 选用六图：Mac 菜单退出、Windows 托盘退出、两平台主窗、Mac 运行规则及 Windows 设置。两个退出面板突出展示，常规页面可折叠；本次不宣称覆盖操作记录页，也不重复堆放配色变体。

V0.3.4 highlights the Activity source dropdown on both platforms: Chinese/light on Mac and English/dark on Windows. The six-image selection also includes both main windows, Windows Settings, and the Mac menu, covering four page types. Activity uses the same synthetic quota-recovery fixture, with source labels and no live-client connection.

V0.3.4 重点展示两平台操作记录来源下拉筛选：Mac 中文浅色与 Windows 英文深色。六图还包括两平台主窗、Windows 设置及 Mac 菜单，共四类页面。操作记录继续使用带来源字段的模拟额度恢复数据，不连接真实客户端。

V0.4.0 highlights TokenMax branding, native juicer controls, and concise Activity summaries on both platforms. The six-image selection covers Home, Activity, Settings, and the menu. The pictures use the same release build and synthetic data.

V0.4.0 重点展示两平台榨汁机品牌、原生开关及简洁的操作记录；六图覆盖主窗、操作记录、设置和菜单，均使用同版构建与模拟数据。

Images come from the release build's native fixture-render mode, using repository demo data. They do not show a real account or establish live-client acceptance. PNGs stay out of source control. `release-gallery.json` records the tag, source commit, original run, build manifests, image hashes, dimensions, and allowlisted receipt metadata. Older render receipts do not cryptographically bind an individual PNG to a commit; that limitation is stated in the gallery manifest.

图片来自同版原生应用的示例渲染，不展示真实账号，也不代表真实客户端控制已通过验收。PNG 不提交源码仓库。`release-gallery.json` 保存标签、源码提交、原构建运行、清单、图片摘要、尺寸及允许公开的回执信息；旧回执不能为单张 PNG 提供源码提交的密码学绑定，此限制在清单中明确说明。

New releases include gallery PNGs, `release-gallery.json`, and `GALLERY_SHA256SUMS` in the unified `SHA256SUMS`. The independent gallery summary covers only the selected PNGs and gallery manifest. Release-body and Markdown-fragment working files are not uploaded as assets.

新发行的统一 `SHA256SUMS` 包含预览 PNG、图库清单和独立 `GALLERY_SHA256SUMS`。独立摘要仅列预览图及图库清单，不包含说明正文和 Markdown 片段工作文件。

## Backfill an existing gallery / 为现有发行补图

The [gallery backfill workflow](../.github/workflows/release-gallery-backfill.yml) adds images without rebuilding or reinstalling the app. Its initial automatic target is `v0.3.1-preview.2`, from original run `40467782526`. **Run workflow** also accepts an existing preview tag and original run ID. Only V0.3.1 or later is supported; it must not be used to relabel historical V0.2 images.

[专用补图工作流](../.github/workflows/release-gallery-backfill.yml) 不重新构建或安装应用。首次自动目标为 `v0.3.1-preview.2`，原运行号为 `40467782526`；手动运行也可填写既有预览标签及原构建运行号。仅支持 V0.3.1 及后续版本，不能用于给 V0.2 历史图重新标注。

For a gallery-only change pushed to the workflow's selected paths on `main`, include `[release-gallery-only]` in the commit message. This skips the normal package-release preparation and runs only the backfill workflow. Manual dispatch of the normal release workflow still performs a complete build. Backfill uses GitHub Actions' repository-scoped `GITHUB_TOKEN`; no personal token or local GitHub CLI sign-in is required.

仅修改图库时，在 `main` 的相关路径提交说明中包含 `[release-gallery-only]`，即可跳过正常安装包发行，只运行补图流程。手动触发正常发行仍会完整构建。补图使用 Actions 的仓库令牌，不要求个人令牌或本机 GitHub CLI 登录。

The workflow verifies that the existing tag, original successful workflow run, and both released build manifests agree on version, preview number, and source commit. It downloads only the original run's `macos-offline-validation` and `windows-offline-validation` artifacts, then selects the configured images and receipts. Missing, expired, duplicate, invalid, or mismatched inputs fail the operation.

补图先核对既有标签、原成功运行及两平台已发行构建清单的版本、预览号和源码提交一致，再下载原运行的两份离线验证产物，只选取配置中的图片和回执。输入缺失、过期、重复、损坏或不匹配时必须失败。

Before uploading, every existing same-name asset is downloaded and compared: identical hashes are skipped; a different hash fails without replacement. Only new gallery PNGs, `release-gallery.json`, and `GALLERY_SHA256SUMS` may be added. After all assets are uploaded and hash-verified, the workflow updates only `<!-- release-gallery:start -->` through `<!-- release-gallery:end -->` in the release body. Concurrent note edits cause a safe failure and require a rerun. Original packages, their checksum file, and the tag are never modified.

上传前逐一下载比对已有同名文件：摘要相同则跳过，不同则失败，不覆盖。仅允许追加预览 PNG、图库清单及独立摘要。全部上传并核验后，才更新发行说明的图库标记段；若期间说明被编辑则安全失败，重新运行即可保留最新正文。原安装包、原校验文件及标签始终不变。

## Release contents / 发行文件

For V0.4.0 the user-facing packages are:

- `TokenMax-0.4.0-arm64-preview.dmg`
- `TokenMax-0.4.0-windows-x64-setup.exe`
- `TokenMax-0.4.0-windows-x64-preview.zip`

The same release includes platform build manifests, verification/self-test receipts, `USER_GUIDE.md`, and `SHA256SUMS`. Manifests identify the version, architecture, bundled runtime, source commit, and signing state. Test receipts describe their own scope; packaging success does not prove live delivery.

同一发行附带平台构建清单、验证／自检回执、使用指南和统一校验摘要。清单记录版本、架构、运行环境、源码提交及签名状态；回执只证明其声明的验证范围。

On Mac, compare `shasum -a 256 <downloaded-file>` with `SHA256SUMS`. On Windows, use `Get-FileHash -Algorithm SHA256 <downloaded-file>`. Matching checksums verify the downloaded bytes against the published summary; they are not Developer ID, Apple notarization, or Authenticode signatures.

Mac 可用 `shasum -a 256 <下载文件>`，Windows 可用 `Get-FileHash -Algorithm SHA256 <下载文件>`，与发行中的摘要比较。摘要一致不代表具备正式发行签名或 Apple 公证。

## Latest release / 最新发行入口

The [promotion workflow](../.github/workflows/promote-release.yml) verifies the existing tag, both platform manifests, all assets and their checksums before removing the prerelease flag and selecting that release as GitHub Latest. It changes release metadata only. Existing packages, notes and tags retain their identity. Run it manually with an explicit tag; a newer unpublished preview does not automatically replace Latest.

[提升流程](../.github/workflows/promote-release.yml) 先验证既有标签、两平台构建清单、全部资产和校验值，再取消该发行的预发布标记并设为 GitHub Latest。只修改发行元数据，保留原安装包、说明与标签。后续手动运行时明确选择标签；新的预发布不会自动替换 Latest。

The initial `[promote-latest]` commit promotes `v0.4.2-preview.13`. The tag and installed build number remain unchanged. GitHub Latest selection does not add Apple notarization, Developer ID, Authenticode signing or further live acceptance.

首次 `[promote-latest]` 提交提升 `v0.4.2-preview.13`；标签及已安装构建号保持不变。GitHub Latest 标记不代表新增了公证、正式签名或其他实机验收。

Use [/releases/latest](https://github.com/Dddysun/Codex-Mission-Manager/releases/latest) for the selected release. For preview builds, use [all Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases) or an explicit tag. The Latest API excludes releases still marked as prereleases.

使用 [/releases/latest](https://github.com/Dddysun/Codex-Mission-Manager/releases/latest) 获取已选定的最新发行；仍为预发布的版本通过 [全部 Releases](https://github.com/Dddysun/Codex-Mission-Manager/releases) 或明确标签获取。

## Signing and manual acceptance / 签名与人工验收

Current preview builds are ad-hoc signed and unnotarized on Mac, and unsigned on Windows. Formal signing is a separate release capability. Do not describe a preview as signed, notarized, installed, or live-tested based on a successful CI build.

Manual acceptance must separately cover clean installation and upgrade, real client login and compatibility, Run now with a confirmed receipt, quota-triggered pause and recovery, one-time scheduling, manual input/approval/hold priority, notifications and login startup, real menu-bar/tray reopen, and sleep/display/lock/lid behavior. Include Chinese keyboard composition under repeated refresh on Mac. Record the exact OS and client version and redact private data from evidence.

当前 Mac 预览采用临时签名且未公证，Windows 预览未签名。正式签名、安装及实机控制验收各自独立。人工验收需覆盖首次安装／升级、真实客户端登录兼容、即时发送回执、额度暂停恢复、一次性预约、人工接管优先级、通知与登录启动、真实菜单栏／托盘重开，以及睡眠、熄屏、锁屏和合盖行为；Mac 还需复验真实中文键盘组合输入。记录准确系统和客户端版本，证据对外发布前脱敏。
