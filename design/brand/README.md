# TOKEN榨汁机 / TokenMax · 品牌组件 1.3.0

透明背景的分层 SVG 和无依赖 Web Component。打开 `index.html` 查看双主题、五状态、暂停和减少动态效果。

| 状态 | 杯内符号 | 动效 |
| --- | --- | --- |
| idle | 灰色闪电，灰色杯体 | 静止 |
| working | 金黄色闪电 | 2 秒闪电呼吸、十种随机分叉放电 |
| waiting | 金色暂停符号 | 静止 |
| disconnected | 灰色断开符号 | 静止 |
| error | 红色感叹号 | 静止 |

非工作状态的符号直接替换杯内闪电，不附加角标。深色模式使用柔和灰蓝和金黄色，低强度的暖色描边光晕。所有状态支持透明背景。

## 使用

```html
<script src="quota-juicer.js"></script>
<quota-juicer state="working" theme="auto" size="128" animated="true"></quota-juicer>
```

属性：`state` 为上表五状态；`theme` 为 light / dark / auto；`size` 为 16–2048 像素；`animated="false"` 暂停；`reduced-motion="true"` 减少动态；`label` 自定义无障碍名称；`decorative="true"` 隐藏重复读屏内容。

系统减少动态效果优先，保留静态颜色和符号。手动暂停冻结当前帧，切换状态后仍保留暂停。默认标签为中文，英文界面可传入英文 `label`。

```js
const logo = document.querySelector('quota-juicer');
logo.state = 'waiting';
logo.theme = 'dark';
logo.animated = false;
```

`QuotaJuicer.renderSVG({state:'working', theme:'dark', animated:true})` 返回独立作用域 SVG；`static:true` 去掉动画规则。分层：handle、cup、lid、top-knob、base、control、discharge-1…10、status-symbol。

## 动效与颜色

中心金色闪电以 2 秒为一周期：1 秒渐强、1 秒渐弱，不透明度 0.58–1，不旋转或缩放。十种独立的弯折、多级分叉结构从闪电符号内部发出，部分末端略微越过杯壁。每轮重新随机顺序、长度、强弱、持续时间和间隔；放电不打断呼吸。

The central gold bolt brightens for one second and dims for one second, with opacity 0.58–1. Ten independent bent, branching structures originate inside the bolt. Each cycle varies order, length, intensity, duration and spacing. There is no orbital or rotating motion.

`svg/` 包含双主题共 10 份静态 SVG，以及 light / dark / auto 三份工作态动画 SVG。原生图片控件不保证播放 SVG 动画；应用在 SwiftUI / WPF 中单独实现同一套造型与时序。

## 构建与验证

运行 `node build.cjs` 重建 SVG、Web Component、原生路径常量和四组校验样本。`juicer-motion.js` 是路径与随机模型的唯一编辑入口；Swift 和 C# 实现按样本校验坐标、分支关系、顺序和时序。浏览器测试需 Playwright 与 Chromium：`npm install --no-save playwright`、`npx playwright install chromium`、`node test.cjs`。可用 `QJ_BROWSER_PATH` 指定浏览器。

测试覆盖五状态、闪电呼吸、暂停冻结、换状态保留暂停、非工作态静止、减少动态效果、系统主题、多实例隔离、标签转义和窄屏布局。

## 1.3.0

十种内核放电和 2 秒呼吸同步接入 SVG、SwiftUI 和 WPF。原生界面直接绘制，不使用 WebView；每轮生成一次路径。菜单栏小图标保持静态。

## 1.2.0

闪电向下留出杯盖间距；电弧改为有分叉的连续流光；菜单栏使用独立的小尺寸彩色图标。应用中文名改为 TOKEN榨汁机。

## 1.1.0

状态符号移入杯内；取消旋涡；闪电改为呼吸；电弧改为环绕细线；idle 改为灰色；品牌名改为TOKEN榨汁机 / TokenMax。

[Figma 品牌组件](https://www.figma.com/design/7wMwtHSiNjouhypR669J8P?node-id=7-1036) · [动效画板](https://www.figma.com/design/7wMwtHSiNjouhypR669J8P?node-id=7-1468)

链接的 Figma 画板为 1.1.0 归档；1.3.0 以本目录 SVG 和原生实现为准。应用源文件为 `native/JuicerLogo.swift` 和 `windows/JuicerLogo.cs`。

## 提案归档 / Proposal archive

[随机放电 02](proposals/core-discharge-v2/README.md) 是 1.3.0 的已采纳设计依据，保留动图、十种动态总览和视频。[内核放电 01](proposals/core-discharge-v1/README.md) 为早期归档。提案标签保留历史身份；产品实现以本目录和原生代码为准。

[Proposal 02](proposals/core-discharge-v2/README.md) is the accepted design reference for production 1.3.0. Earlier proposal assets retain their historical labels.
