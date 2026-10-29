# TokenMax · 内核放电 01 / Core-origin discharge 01

品牌动效提案 `1.3.0-proposal.1`。复用 1.2.0 的杯体、手柄、底座和状态符号；电弧从杯内金色闪电向外分叉，短促出现并衰减，少量尖端越过杯壁。暖白电芯与金色细丝参考真实放电的视觉特征，保留现有品牌配色。

This motion proposal reuses the 1.2.0 silhouette and state symbols. Branched, warm-white and gold discharges originate at the central bolt, grow outwards, and decay. A few tips briefly extend past the cup. The paths never form an orbit around the appliance.

打开 `index.html` 可切换外观、状态、暂停及减少动态。`core-discharge.js` 只包含视觉提案，不连接应用、账号或聊天；未替换正式 SVG、Mac 或 Windows 原生实现，也未修改产品版本和已安装应用。

Open `index.html` for theme, state, pause, and reduced-motion controls. This proposal contains no application, account or chat logic. Production SVG, native renderers, application version, and installed applications remain unchanged.

## 预览 / Preview

- [循环动图 / Animated preview](core-discharge.gif)
- [视频 / Video](core-discharge.mp4)
- [深色静帧 / Dark still](preview-dark.png)
- [浅色静帧 / Light still](preview-light.png)
- [透明静态 SVG / Transparent static SVG](core-discharge-static.svg)

一个循环 3.6 秒，六条以闪电符号为起点的主电弧分三组释放；分支从主电弧节点继续向外生长。停用及系统减少动态时保持清晰静态标识，暂停保留当前画面。动图和视频为同一矢量提案的实际浏览器渲染。

The 3.6-second cycle has six bolt-rooted trunks in three groups. Twigs start at trunk vertices. Pausing freezes the current frame; nonworking states and reduced motion remain static. GIF and video are actual browser renders of the vector proposal.
