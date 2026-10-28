# 额度榨汁机 · 品牌方向提案

状态：静态方向待选定。当前三种设计均为提案，不替换应用图标或业务逻辑。

[Figma 可编辑对比画板](https://www.figma.com/design/7wMwtHSiNjouhypR669J8P?node-id=2-303)

打开 `index.html` 可离线比较三个方向。每个方向提供浅色/深色及 idle/working 静态 SVG，共 12 个文件。working 文件仅展示金色闪电和电弧的静态配色，不包含动画。

- A / outline：线性轮廓，适合轻量工具界面。
- B / geometric：实心几何，适合品牌主标志。
- C / app：圆角应用图标，B 的桌面图标延伸。

SVG 的画布为 256 × 256。A/B 的背景透明；C 的外部透明，蓝色圆角底板为图标自身的一层，可独立移除。文件保留 `handle`、`cup`、`lid`、`top-knob`、`vortex`、`base`、`control`、`lightning`、`arcs` 等层标识。C 另外提供 `app-tile` 和 `mark` 层。Figma 中每个版本为独立主组件，评审画板使用实例。

`generate.py` 使用 Python 标准库重新生成静态 SVG 和离线对比页面，无额外依赖。尚未做 16px 光学校正版本，小尺寸展示用于方向比较。

## 选定方向后的动态组件计划（尚未实现）

组件接口：`state: idle | working | waiting | disconnected | error`、`theme: light | dark | auto`、`animated: boolean`、`size`，以及独立的装饰/无障碍标签选项。

| 状态 | 视觉计划 | 动效计划 |
| --- | --- | --- |
| idle | 蓝色杯体、灰色闪电 | 完全静止 |
| working | 金色闪电、少量电弧 | 杯内旋涡与顶部旋钮持续转动，电弧低频变化 |
| waiting | 灰色闪电、小型琥珀色暂停标记 | 停止机械旋转，避免与 working 混淆 |
| disconnected | 降低饱和度、断开标记 | 完全静止 |
| error | 灰色闪电、红色错误标记 | 完全静止，不采用警报闪烁 |

以上为待选定造型后的实现基线，尚非已交付的动画能力。

工作态旋涡需要限制在杯体内；顶部旋钮单独设置中心锚点，闪电保持固定，确保小尺寸可辨识。正常建议旋涡周期约 2.4 秒、旋钮约 3.2 秒，避免高频闪烁。

动态组件须响应 `prefers-reduced-motion: reduce`：停止旋转、电弧闪烁与其他循环，保留状态颜色和图形。`animated=false` 同样冻结动效，且不能被状态变更隐式重新开启。五种状态均应有静态 SVG；状态文字由组件可访问名称表达，不能只依赖颜色。

下一阶段交付：选定方向的可复用 SVG 组件、五状态静态文件、深浅主题和可交互动画预览。当前阶段不接入应用状态机。
