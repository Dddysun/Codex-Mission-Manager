# TokenMax · 随机放电 02 / Irregular discharge 02

品牌动效提案 `1.3.0-proposal.2`，保留 1.2.0 机身和杯内符号。针对上一版固定方向轮换、长短接近和旋转感的反馈，重新绘制十种独立放电结构。

Ten distinct branching structures replace the first proposal's alternating directional pairs. The existing 1.2.0 appliance silhouette and state symbols are reused.

## 观看 / View

- [十种交错动图 / Combined animation](core-discharge.gif)
- [视频 / Video](core-discharge.mp4)
- [十种动态总览 / Animated gallery](gallery.gif)
- [十种静帧总览 / Still contact sheet](contact-sheet.png)
- [深色 / Dark](preview-dark.png) · [浅色 / Light](preview-light.png)
- `index.html`：可单选形态、换一组、切换主题、暂停和减少动态。

## 十种形态 / Ten shapes

1. [短枝碎闪 / Short fragments](clips/01.gif)
2. [折返分叉 / Folded fork](clips/02.gif)
3. [长短错落 / Unequal twins](clips/03.gif)
4. [内核裂纹 / Core fractures](clips/04.gif)
5. [侧向游走 / Lateral crawl](clips/05.gif)
6. [下探裂枝 / Descending branches](clips/06.gif)
7. [弯折越壁 / Bent overshoot](clips/07.gif)
8. [一长两短 / Long and short](clips/08.gif)
9. [偏侧树冠 / Asymmetric canopy](clips/09.gif)
10. [散簇微爆 / Clustered sparks](clips/10.gif)

[下载十个独立动图 / Download ten GIFs](ten-discharge-clips.zip)

## 动效原则 / Motion

- 主电弧从杯内闪电出发；分支连接到主电弧或已有分支，形成多级树状放电。
- 粗路径有侧向折返和弯折，再叠加细碎电痕，不使用同一路径旋转生成形态。
- 不等长、不同分支数、不同强弱与持续时间；连续预览每轮重新打乱顺序和停顿，轻微改变各条路径。
- 多数电弧留在杯内，部分尖端短暂越过杯壁。没有外围环绕轨迹或杯内旋涡。
- 暂停冻结当前画面；非工作状态及减少动态保持静止。

Main trunks originate within the bolt. Twigs attach to existing trunk or branch vertices. Bent macro paths and fine fractures form ten independently drawn topologies; none is made by rotating another. Length, brightness, branch count, timing and pauses vary. The live preview reshuffles and perturbs each cycle. GIF/video are fixed recordings and repeat when looped.

本目录为独立视觉提案。未修改正式 SVG、Mac／Windows 原生 Logo、产品版本或已安装应用；不启动后台，不读取账号和聊天。参考素材没有复制到仓库。

This is a standalone visual proposal. Production assets, native renderers, application version and installed applications are unchanged. It starts no backend and reads no account/chat data. The reference image is not included.

## 重新导出 / Render

提供 Playwright、Chromium、ffmpeg 和用于 ZIP 导出的 Python 3 后，运行 `node render.cjs /tmp/tokenmax-discharge-v2-frames`。可以通过 `QJ_BROWSER_PATH` 指定 Chromium，通过 `FFMPEG` 指定 ffmpeg，通过 `QJ_PYTHON` 指定 Python。

With Playwright, Chromium, ffmpeg and Python 3 for ZIP export available, run `node render.cjs /tmp/tokenmax-discharge-v2-frames`. Temporary PNG frames stay in the supplied directory; deliverables and verification are written here. `QJ_PYTHON` may select the Python executable.
