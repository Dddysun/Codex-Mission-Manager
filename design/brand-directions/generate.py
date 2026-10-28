"""Static brand direction studies. No application integration or animation."""
from pathlib import Path
import json

ROOT = Path(__file__).parent

def svg(style, theme='light', state='idle'):
    blue = '#2168D5' if theme == 'light' else '#6CA9FF'
    pale = '#EAF3FF' if theme == 'light' else '#162E50'
    bolt = ('#F4B321' if theme == 'light' else '#FFD166') if state == 'working' else ('#8795A8' if theme == 'light' else '#A0AEC1')
    if style == 'app':
        blue, pale = '#FFFFFF', '#367BDD'
        bolt = '#FFD166' if state == 'working' else '#CED8E6'
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-label="额度榨汁机 · {style} · {state}">', '<title>额度榨汁机</title>']
    if style == 'app':
        s += ['<g id="app-tile"><rect x="8" y="8" width="240" height="240" rx="56" fill="#175CC9"/><path d="M64 20H192" stroke="#6BA9FF" stroke-width="3" stroke-linecap="round" opacity=".4"/></g>', '<g id="mark" transform="translate(26 24) scale(.80)">']
    if style == 'outline':
        s += [f'<g id="handle"><path d="M184 79H198C220 79 228 94 224 113L221 129C218 146 202 154 176 151" fill="none" stroke="{blue}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></g>',
        f'<g id="cup"><path d="M65 64H189L176 160Q175 173 160 173H94Q79 173 78 160Z" fill="none" stroke="{blue}" stroke-width="9" stroke-linejoin="round"/></g>',
        f'<g id="lid"><path d="M61 62H192" stroke="{blue}" stroke-width="10" stroke-linecap="round"/></g>',
        f'<g id="top-knob"><path d="M110 47Q110 35 127 35Q144 35 144 47" fill="none" stroke="{blue}" stroke-width="8" stroke-linecap="round"/></g>',
        f'<g id="vortex"><path d="M95 151Q119 164 153 151" fill="none" stroke="{blue}" stroke-width="5" stroke-linecap="round" opacity=".48"/></g>',
        f'<g id="base"><path d="M87 183H167Q176 183 180 194L185 214H69L74 194Q78 183 87 183Z" fill="none" stroke="{blue}" stroke-width="9" stroke-linejoin="round"/></g>',
        f'<g id="control"><path d="M123 199H132" stroke="{blue}" stroke-width="6" stroke-linecap="round"/></g>']
    else:
        s += [f'<g id="handle"><path d="M180 78H199Q229 78 226 110L223 128Q220 156 176 153" fill="none" stroke="{blue}" stroke-width="15" stroke-linejoin="round"/></g>',
        f'<g id="cup"><path d="M62 63H193L181 158Q179 177 160 177H94Q75 177 73 158Z" fill="{blue}"/><path d="M78 76H177L166 155Q165 163 155 163H99Q89 163 88 155Z" fill="{pale}"/></g>',
        f'<g id="lid"><rect x="57" y="48" width="142" height="22" rx="11" fill="{blue}"/></g>',
        f'<g id="top-knob"><path d="M110 43V35Q110 29 117 29H138Q145 29 145 35V43Z" fill="{blue}"/><path d="M122 35H132" stroke="{pale}" stroke-width="3" stroke-linecap="round"/></g>',
        f'<g id="vortex"><path d="M99 147Q125 158 153 145" fill="none" stroke="{blue}" stroke-width="4" stroke-linecap="round" opacity=".3"/></g>',
        f'<g id="base"><path d="M88 182H166Q183 182 187 199L190 212Q192 222 180 222H74Q62 222 64 212L67 199Q71 182 88 182Z" fill="{blue}"/></g>',
        f'<g id="control"><circle cx="127" cy="202" r="10" fill="{pale}"/><path d="M127 196V201" stroke="{blue}" stroke-width="3" stroke-linecap="round"/></g>']
    s += [f'<g id="lightning"><path d="M129 83H151L133 108H153L113 145L124 118H104Z" fill="{bolt}"/></g>']
    if state == 'working':
        s += [f'<g id="arcs" fill="none" stroke="{bolt}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"><path d="M40 92L29 106H40L30 120"/><path d="M205 44L214 35"/><path d="M208 177L221 183"/></g>']
    else:
        s += ['<g id="arcs"/>']
    if style == 'app': s += ['</g>']
    return ''.join(s) + '</svg>\n'

assets=[]
for style in ('outline','geometric','app'):
    for theme in ('light','dark'):
        for state in ('idle','working'):
            name=f'{style}-{theme}-{state}.svg'
            data=svg(style,theme,state)
            (ROOT/name).write_text(data)
            assets.append(dict(style=style,theme=theme,state=state,name=name,svg=data))
(ROOT/'assets.json').write_text(json.dumps(assets,ensure_ascii=False,indent=2))
names={'outline':('A','线性轮廓','轻巧、克制，适合菜单栏与工具界面。'), 'geometric':('B','实心几何','轮廓鲜明，适合长期品牌与多尺寸传播。'), 'app':('C','圆角 App 图标','完整蓝色底座，适合桌面与应用商店。')}
cards=[]
for st,(letter,title,desc) in names.items():
    cards.append(f'''<article><div class="eyebrow">DIRECTION {letter}</div><h2>{title}</h2><p>{desc}</p><div class="hero">{svg(st)}</div><div class="pair"><div>{svg(st,'light','idle')}<span>静态 · 灰色闪电</span></div><div>{svg(st,'light','working')}<span>工作态配色 · 静态示意</span></div></div><div class="dark"><span>深色背景 / 64 · 32 · 24</span><div class="sizes">{''.join(f'<img width="{z}" height="{z}" src="{st}-dark-idle.svg" alt="{title} {z}像素"/>' for z in (64,32,24))}</div></div></article>''')
(ROOT/'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>额度榨汁机 · 品牌方向</title><style>*{box-sizing:border-box}body{margin:0;background:#f3f5f9;color:#14233a;font-family:system-ui,-apple-system,sans-serif}main{max-width:1440px;margin:auto;padding:56px 40px}header{margin-bottom:32px}.eyebrow{font-size:12px;letter-spacing:2px;color:#687a93}h1{font-size:40px;margin:12px 0}h2{font-size:23px;margin:10px 0}p{color:#627189;line-height:1.7}section{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}article{background:white;border:1px solid #e1e6ee;border-radius:24px;padding:28px;overflow:hidden}.hero{display:flex;justify-content:center;padding:18px 0}.hero svg{width:240px;height:240px}.pair{display:flex;justify-content:space-between;border-top:1px solid #e8edf4;padding:20px 0}.pair>div{text-align:center;flex:1}.pair svg{width:86px;height:86px;display:block;margin:0 auto 10px}.pair span{font-size:11px;color:#64748b}.dark{background:#101c30;border-radius:14px;color:#98acc8;padding:16px;font-size:11px}.sizes{display:flex;align-items:center;justify-content:space-around;height:86px}footer{font-size:13px;color:#61728b;padding:28px 0;line-height:1.9}@media(max-width:960px){section{grid-template-columns:1fr}main{padding:30px 20px}}</style><main><header><div class="eyebrow">品牌探索 / 01</div><h1>额度榨汁机</h1><p>让每一份额度，都继续创造价值。三种静态方向，先确认造型，再制作动态组件。</p></header><section>'''+''.join(cards)+'''</section><footer>本轮为品牌方向提案，尚未选定最终 Logo。工作态展示仅用于比较配色，不包含动画。<br>下一阶段：idle / working / waiting / disconnected / error；透明背景、深浅主题、动画启停与 prefers-reduced-motion。</footer></main></html>''')
print(f'Created {len(assets)} static SVG studies and comparison page')
