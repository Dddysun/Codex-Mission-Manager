# 额度榨汁机 · 动态品牌组件 1.0.0

基于已选定的 B「实心几何」造型。此包是独立品牌组件，不包含任务控制、账号、额度读取或应用业务逻辑。

[Figma 品牌规范及五状态](https://www.figma.com/design/7wMwtHSiNjouhypR669J8P?node-id=7-1036) · [Figma 动画演示](https://www.figma.com/design/7wMwtHSiNjouhypR669J8P?node-id=7-1468)

## 查看

直接用浏览器打开 `index.html` 即可离线预览，无安装步骤和网络请求。默认深色、工作态。可切换五种状态、深浅色/跟随系统、播放暂停、减少动态效果和透明背景网格。

## 视觉与状态

| 状态 | 视觉与运动 |
| --- | --- |
| `idle` | 蓝色杯体，灰色闪电，静止 |
| `working` | 金黄色闪电；杯内旋涡每 2.4 秒转一圈；顶部旋钮指针每 3.2 秒转一圈；电弧以 2.8 秒周期缓慢变化 |
| `waiting` | 灰色闪电，金色暂停符号，静止 |
| `disconnected` | 杯体降低饱和度，断开符号，静止 |
| `error` | 灰色闪电，红色感叹号，静止 |

浅色杯体 `#2168D5`，闪电 `#E7AA16`；深色杯体 `#4878AF`，闪电 `#E7B43C`。深色使用柔和灰蓝而非高亮电蓝，没有发光、阴影滤镜和大范围金色背景。除工作态外，闪电均为灰色。

SVG 背景完全透明。推荐尺寸 32–256px；24px 可用于紧凑展示，但小型状态符号不能替代旁边的文字。16px 专用像素校正图标不在本次交付内。

## 可复用组件

```html
<script src="quota-juicer.js"></script>
<quota-juicer state="working" theme="auto" size="128" animated="true"></quota-juicer>
```

Web Component 无第三方运行依赖，Shadow DOM 隔离样式，适用于常规 HTML 和支持自定义元素的前端框架。`state`、`theme`、`animated` 同时提供 JavaScript 属性；其余选项使用 HTML 属性。

| 属性 | 默认 | 说明 |
| --- | --- | --- |
| `state` | `idle` | 上表五种状态；无效值回退 idle |
| `theme` | `auto` | light / dark / auto；auto 响应系统主题变化 |
| `size` | `256` | 像素，限制 16–2048 |
| `animated` | `true` | 设置字符串 `false` 暂停；切换状态仍保留暂停选择 |
| `reduced-motion` | `false` | true 强制减少动态；false 不会覆盖系统的减少动态偏好 |
| `label` | 品牌＋状态中文名称 | 自定义无障碍描述，如英文界面需要的标签 |
| `decorative` | `false` | true 时对辅助技术隐藏，适合旁边已有同义文字 |

```js
const logo = document.querySelector('quota-juicer');
logo.state = 'waiting';
logo.theme = 'dark';
logo.animated = false;
```

系统 `prefers-reduced-motion: reduce` 优先级最高：关闭全部循环动画，保留颜色和符号。手动暂停保留当前帧；减少动态切回静态姿态。状态文字不采用持续读屏播报，避免轮询造成打扰。

## 直接使用 SVG

`svg/` 有 10 份静态文件（两种主题 × 五状态，无动画规则）和 3 份工作态动画 SVG（light/dark/auto）。CSS 动画能在支持 SVG CSS 的浏览器中播放；原生图像加载器通常只呈现静态图，不能假定 SwiftUI/WPF 的图片控件会播放。

程序化生成：

```js
const markup = QuotaJuicer.renderSVG({
  state: 'working', theme: 'dark', size: 128,
  animated: true, reducedMotion: false, decorative: false
});
```

`renderSVG` 返回字符串，不自动插入页面。生成的每个实例拥有独立 clip/title ID 和样式作用域；自定义标签进行转义。`static: true` 完全省略动画规则。输出中的 `data-layer` 标记保留 handle、cup、vortex、lid、top-knob、base、control、lightning、arcs、status-badge，方便后续原生实现。

## 构建与验证

`node build.cjs` 使用 Node 标准库生成 SVG 与 Figma 导入数据，无构建依赖。运行浏览器检查需安装 Playwright 及其 Chromium：`npm install --no-save playwright`、`npx playwright install chromium`，然后 `node test.cjs`。可通过 `QJ_BROWSER_PATH` 指定独立测试浏览器。

已在 Chromium 实测：旋转推进、暂停冻结、换状态保留暂停、非工作态静止、系统与手动减少动态效果、系统深浅色切换、多实例颜色/ID 隔离、标签转义、静态 SVG 无动画，以及 390px 预览布局无横向溢出。尚未在 Windows、Safari 或原生应用容器中实测；本轮没有修改或部署应用。

Figma 包含 10 个 State × Theme 变体、8 个双主题颜色变量和独立的双主题动画演示画板。Figma 演示为 9.6 秒时间轴；交互预览和 SVG 组件使用无限循环，并实现减少动态效果偏好。`figma-motion.mp4` 为 Figma 导出的演示视频；无透明通道、无交互，不作为组件替代品。

## 版本说明

1.0.0：采用实心几何主标志；新增五状态、柔和深色调、金黄色工作态闪电、三项工作动效、动画暂停和减少动态适配。组件版本独立于任务管家应用版本，尚未接入应用状态机。
