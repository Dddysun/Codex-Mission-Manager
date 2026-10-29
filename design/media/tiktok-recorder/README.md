# TokenMax 原生界面短视频素材

为 0.4.2 preview.13 / 品牌组件 1.3.0 制作的十九组按台本排序的中文介绍镜头。直接复用 Mac 的 SwiftUI / AppKit 视图；没有重画一套网页界面。上方项目名称统一为“TokenMax / Token榨汁机”。每组导出横屏 2560×1600 和竖屏 1080×1920，30 fps、H.264、静音。竖屏附标题、重点区域缓慢放大和演示标识；横屏保留完整界面，附小型演示标识。TokenMax 画面不含桌面、其他应用、真实账号或聊天内容。四组 Codex 补充镜头来自 OpenAI 官方公开截图，带来源标识与镜头运动，不是用户电脑上的 Codex 实时录屏。

这些是隔离进程中渲染的原生界面演示，不是从已安装应用采集的真实运行录像，也不能作为真实暂停、恢复或官方额度事件的验收证据。余额、时间、任务、预约和结果全部来自静态模拟数据，等待过程已压缩。恢复原因在原生界面中仍标注“推断”。不生成音轨，不提供会员价格或额度比例的事实证明。

## 使用

需要 Apple Silicon Mac、Xcode Command Line Tools、Python 3、FFmpeg（含 libx264）与 ffprobe。在仓库根目录执行：

```sh
python3 -B design/media/tiktok-recorder/build.py --build /tmp/tokenmax-media-build
python3 -B design/media/tiktok-recorder/fetch_codex_assets.py /tmp/tokenmax-codex-public
python3 -B design/media/tiktok-recorder/scenes.py /tmp/tokenmax-media-plan.json --assets /tmp/tokenmax-codex-public
/tmp/tokenmax-media-build/TokenMaxMediaRecorder /tmp/tokenmax-media-plan.json /tmp/tokenmax-media-output
python3 -B design/media/tiktok-recorder/finalize.py /tmp/tokenmax-media-plan.json /tmp/tokenmax-media-output
```

使用新的输出目录；已有视频不会被覆盖。可以传 `--scene 04` 只生成预约镜头，或增加 `--preview` 仅生成该镜头的原生检查帧。完整收尾检查需要十九组视频齐全。`finalize.py` 将视频索引移至文件头、生成 76 秒总览和 190 秒完整串联、逐帧解码检查全部视频，并写出 SHA-256 与机器可读清单。

## 镜头

01–02：Codex 桌面与代码修改的官方公开示例。

03–05：五小时 / 周额度、晚上十点到凌晨三点、Codex 等待下一步。

06：TokenMax / Token榨汁机登场。

07–11：额度监控、低额度暂停、恢复续接、逐字输入预约、已保存的一次性预约。

12–14：后台运行条件、次日查看进展、Codex 测试结果公开示例。

15–18：恢复历史、调度边界、官方只读余额、日夜外观。

19：高斯模糊背景渐入，居中出现 Token榨汁机 / TokenMax 和动态 Logo。

唯一镜头共 190 秒；每组均导出两种画幅。具体台词对应关系写在场景计划的 `script_cue`，并进入导出清单。总览每组取四秒，完整串联保留所有镜头时长。

片尾对原生背景执行显式 Core Image `CIGaussianBlur`，再叠加原生动态 Logo 和文字，保留十种分叉放电与独立两秒呼吸。没有依赖离屏缓存可能丢失的窗口层模糊。

## 隔离方式与边界

`scenes.py` 只读仓库中的公开测试 fixture，替换为虚构任务和保留域名 `example.invalid`。不读已安装应用的数据目录、Codex 历史、账户或钥匙串。

`build.py` 在临时构建目录复制原生源文件，禁用应用入口与后台启动方法，启用原有中文测试模式，使用模拟时钟，给视图增加初始导航 / 筛选参数。不会修改产品源码、安装包、已安装应用或系统时间。Logo 几何、状态、分叉和两秒呼吸仍使用生产实现，只替换时间输入。界面的开关使用原生绘制；离屏视图可能采用非活动窗口的控件外观。

`Recorder.swift` 的窗口不展示、不激活，不请求屏幕录制权限，不发送全局键鼠事件。输入动画只编辑演示进程自己的 `NSTextView`；每帧检查没有后台进程、服务地址或状态目录。没有调用暂停、续接或发送聊天指令的方法。

工具仅用于此处生成的可信演示计划。官方截图仅在下载后参与本地剪辑，来源为 https://developers.openai.com/blog/run-long-horizon-tasks-with-codex 。截图镜头与原生模拟镜头分别注明性质。生成视频和构建缓存应留在仓库外；不要将真实数据、用户下载目录或整个工作区上传。产品版本与发布流程保持独立，修改本目录不触发安装包发布。
