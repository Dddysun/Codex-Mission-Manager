import { Callout, CollapsibleSection, Divider, Grid, H1, H2, H3, Link, Pill, Row, Stack, Stat, Table, Text, useCanvasState, useHostTheme } from "cursor/canvas";

const source = "https://github.com/Dddysun/Codex-Mission-Manager/blob/7e5b0b11a763b83b52e84a745cf5f14dffc66645/";
const reportUrl = "https://github.com/Dddysun/Codex-Mission-Manager/blob/codex/runtime-cache-and-architecture-review/docs/reviews/2026-10-29-architecture.md";

type Finding = { id: string; priority: string; state: string; title: string; impact: string; action: string; proof: string; file: string };
const findings: Finding[] = [
  { id:"F01", priority:"P1", state:"已修复", title:"运行时缓存破坏应用资源封存", impact:"首次安装通过校验，冷导入后可能新增 .pyc，导致 Mac 签名完整性失败。", action:"两平台启动器和子进程显式使用 -B；对可写副本做冷导入并复核文件和签名。", proof:"可写副本及真实隔离子进程通过；新增缓存反例能够触发校验失败。", file:"scripts/verify_dmg.py" },
  { id:"F02", priority:"P1", state:"已修复", title:"写入等待未计入完整通信超时", impact:"对端停止接收时，采集循环可能卡在请求写入阶段。", action:"限制完整请求、独立广播写入和连接关闭的等待；保留结果不确定时不重发。", proof:"阻塞模拟：旧实现等到外部看门狗；修复后两个写入等待约 31–32 毫秒退出，配置为 30 毫秒。", file:"backend/tests/test_transport_deadlines.py" },
  { id:"F03", priority:"P2", state:"改进", title:"采集、控制、保存集中在同一循环", impact:"一个慢聊天会延迟后面的状态和操作，目录与控制还会重复读取。", action:"分离额度采样、只读采集和动作执行；每个聊天保持单一控制队列和最终复核。", proof:"代码结构确认；优化验收需注入慢聊天并检查额度采集和撤销许可。", file:"backend/guardian.py" },
  { id:"F04", priority:"P2", state:"改进", title:"大会话完整快照仍有瞬时开销", impact:"128 MiB 有界上限解决已知故障；完整帧接收、解析和指纹仍会占用资源。", action:"评估摘要或增量读取，减少重复解析，测量完整周期、接收大小及内存峰值。", proof:"接收后会提取较小的规范化状态，不能误称持续保存 32 份完整大会话。", file:"backend/desktop.py" },
  { id:"F05", priority:"P2", state:"改进", title:"界面协议与存储模型边界不够明确", impact:"字段变化和旧后台兼容可能在两平台表现不同。", action:"增加版本化状态／命令契约和共同样例；明确存储接口，减少重复规则和字符串字典。", proof:"Mac 结构体、Windows 字典和后台规则当前各自维护；最终发送仍由后台复核。", file:"backend/ui.py" },
  { id:"F06", priority:"P2", state:"改进", title:"Windows 主文件职责集中", impact:"约 2,449 行文件同时处理窗口、网络、进程、托盘、偏好和自检，变更容易牵动多处。", action:"先分离后台客户端、进程宿主、生命周期和页面状态；沿用现有原生界面与行为测试。", proof:"文件规模是维护指标，不单凭行数判定代码错误。", file:"windows/MissionManager.cs" },
  { id:"F07", priority:"P2", state:"改进", title:"历史查询和数据库演进缺少长期边界", impact:"每次状态读取扫描旧请求；记录增长后刷新成本增加，未来升级验证也更难。", action:"建立可索引查询、数据库版本和迁移回退测试；归档时保留幂等标识，由用户决定保留政策。", proof:"小数据量时不等于已经发生性能故障；需用大量模拟记录量化。", file:"backend/immediate.py" },
  { id:"F08", priority:"P2", state:"改进", title:"Mac 外部依赖隔离可以更清晰", impact:"桌面版本不支持会阻止整个适配器启动；CLI 还可能优先来自 PATH。", action:"区分额度读取与桌面控制能力，并核验实际 CLI 来源。", proof:"Windows 已有先启动额度通道、再尝试控制的实现，可复用其思路。", file:"backend/desktop.py" },
  { id:"F09", priority:"P2", state:"改进", title:"缺少合并前自动验证关卡", impact:"现有工作流面向 main 或手动发行；普通分支修复缺少自动的合并前两平台检查。", action:"增加无发布权限的 PR 验证，再将通过的检查设为合并条件。", proof:"发行及图库工作流的触发配置已核对；现有来源、哈希和原生检查应保留。", file:".github/workflows/release.yml" },
  { id:"F10", priority:"P2", state:"产品规则", title:"明确新聊天的默认接管方式", impact:"全局开启后，新发现且未明确撤销许可的已加载聊天可以被自动管理。", action:"决定只管理逐项选中的聊天，或明确提供默认接管新聊天的规则。", proof:"当前行为由默认配置和自动发现分支确认；本轮不擅自改变已存在的许可。", file:"backend/config.example.json" },
  { id:"F11", priority:"P2", state:"启用前置", title:"合盖辅助服务命令仍需超时", impact:"未来正式签名版本若 pmset 卡住，共用队列的恢复看门狗也可能被拖住。", action:"开放前补齐完整命令期限、恢复回执和隔离故障测试。", proof:"当前预览拒绝启用管理员服务；本轮没有修改真实电源设置。", file:"native/PowerHelper.swift" },
  { id:"F12", priority:"P3", state:"改进", title:"品牌测试环境与持续验证需固定", impact:"SVG、Swift、WPF 分别绘制，浏览器测试环境依赖调用方配置。", action:"固定开发测试依赖，将品牌回归纳入验证，集中几何及配色常量。", proof:"本轮浏览器动画、暂停、减少动态效果、深浅主题和静态导出检查通过。", file:"design/brand/test.cjs" },
  { id:"F13", priority:"P3", state:"改进", title:"补充不含聊天内容的诊断指标", impact:"连接异常时，难以区分额度读取、慢会话和数据库等待。", action:"记录阶段与完整周期耗时、大小及重连计数；提供脱敏诊断，避免保存协议正文。", proof:"现有报告已有阶段、错误类型和时间，可在此基础上扩展。", file:"backend/guardian.py" },
];

const validation = [
  ["Mac 后台", "323 项执行，3 项平台跳过", "失败 0／错误 0", "隔离夹具"],
  ["宿主与资源校验器", "31 项", "全部通过", "隔离夹具"],
  ["Mac 最终 DMG", "挂载、自检、可写副本", "冷导入后文件与签名保持完整", "候选包，未安装"],
  ["Mac 原生", "状态契约、IME、草稿、生命周期", "通过", "无生产后台"],
  ["Windows 抽查", "129 项执行，1 项平台跳过", "失败 0／错误 0", "真实设备隔离目录；非完整套件"],
  ["Windows 通信超时", "另 5 项", "全部通过", "阻塞模拟"],
  ["Windows 原生", "构建、编辑器、生命周期、深浅预览", "通过", "未创建真实系统托盘"],
  ["Windows 真实只读连接", "额度、握手、状态、自身连接重连", "通过", "无消息发送、无任务中断"],
  ["品牌组件", "动画、暂停、主题、减少动态效果等", "通过", "离线浏览器"],
];

const pending = [
  ["真实低额度 → 恢复 → 续接", "等待自然事件，或使用用户专门指定的可打断聊天"],
  ["官方提前恢复事件", "尚未观察到；来源归因仍是采样推断"],
  ["Windows 安装升级与真实托盘", "隔离构建和只读连接通过；安装与交互仍需单独验收"],
  ["Mac 菜单栏真实深浅背景", "主窗口及品牌组件已验；系统菜单栏最终观感未验"],
  ["合盖、手动睡眠、锁屏发送", "当前预览辅助服务限制继续适用；未修改真实电源设置"],
];

export default function TokenMaxArchitectureReview() {
  const theme = useHostTheme();
  const [tab, setTab] = useCanvasState("TokenMax-review-tab", "overview");
  const [filter, setFilter] = useCanvasState("TokenMax-review-filter", "all");
  const visible = findings.filter(f => filter === "all" || (filter === "fixed" ? f.state === "已修复" : f.state !== "已修复"));
  return <Stack gap={20} style={{padding:24,color:theme.text.primary,maxWidth:1120,margin:"0 auto"}}>
    <Stack gap={8}>
      <H1>TokenMax 代码架构审查</H1>
      <Text tone="secondary">2026-10-29 · Asia/Dubai · 基线 0.4.1 preview.11 · 修复候选 0.4.2</Text>
      <Text>保留共享后台与双原生界面，优先完善可靠性、采集隔离和维护边界。</Text>
    </Stack>
    <Row gap={24} wrap>
      <Stat value="2" label="已修复的具体缺陷" />
      <Stat value="11" label="后续架构与维护改进" />
      <Stat value="5" label="仍需现场或自然事件验收" />
    </Row>
    <Row gap={8} wrap>
      {[['overview','结论与改进顺序'],['findings','全部发现'],['validation','验收与边界']].map(([key,title]) =>
        <span key={key}><Pill active={tab===key} onClick={()=>setTab(key)}>{title}</Pill></span>)}
    </Row>
    <Divider />
    {tab === "overview" && <Stack gap={20}>
      <Callout title="本轮交付" tone="info">已修复运行时缓存破坏资源封存，以及通信写入无完整超时。两平台候选构建和隔离验证通过；源码修复、候选包与实际安装升级分别验收。</Callout>
      <H2>现有架构</H2>
      <Row gap={12} wrap style={{padding:16,background:theme.fill.tertiary}}>
        <Text>SwiftUI／WPF 窗口</Text><Text tone="tertiary">→</Text><Text>本机 JSON 服务</Text><Text tone="tertiary">→</Text><Text>共享 Python 调度</Text><Text tone="tertiary">↔</Text><Text>SQLite 记录</Text>
      </Row>
      <Grid columns={2} gap={20}>
        <Stack gap={8}><H3>额度读取</H3><Text>Codex app-server 提供额度采样，缺失数据保持未知。</Text></Stack>
        <Stack gap={8}><H3>聊天控制</H3><Text>版本适配的内部 IPC，执行前复核用户许可和聊天状态。</Text></Stack>
      </Grid>
      <H2>建议的改进顺序</H2>
      <Table framed={false} headers={["阶段","行动","完成标准"]} rows={[
        ["先交付","审查两项修复，安排候选版升级","资源不变、超时有界、模糊发送不重试"],
        ["合并前","PR 自动验证与统一接口样例","两平台共同检查，验证任务不能发布"],
        ["性能","分离采集与控制，减少全量重复读取","慢聊天不拖住额度采样；按完整周期测量"],
        ["维护","拆分原生端职责与外部依赖","保留草稿、IME、生命周期和原生窗口"],
        ["产品决定","新聊天接管规则与辅助服务开放条件","许可语义明确；高权限功能开放前完成恢复测试"],
      ]} />
      <H2>应保留的可靠性设计</H2>
      <Text>持久化动作意图与唯一标识、发送结果不确定时停止重试、手动保持和审批保护、账号隔离、应用自有进程回收、运行环境哈希及模拟数据预览。</Text>
    </Stack>}
    {tab === "findings" && <Stack gap={16}>
      <Row gap={8} wrap>
        {[['all','全部 13 项'],['fixed','已修复 2 项'],['next','后续 11 项']].map(([key,title]) =>
          <span key={key}><Pill active={filter===key} onClick={()=>setFilter(key)}>{title}</Pill></span>)}
      </Row>
      <Text tone="secondary">P1 为本轮已修复的可靠性缺陷；P2 为应安排的结构与边界改进；P3 为维护增强。产品规则和启用前置条件单独标注。</Text>
      {visible.map(f=><div key={f.id}><CollapsibleSection title={`${f.id} ${f.title}`} defaultOpen={f.state==='已修复'} trailing={<Text size="small">{f.priority} · {f.state}</Text>}>
        <Stack gap={10} style={{padding:"8px 0 16px"}}>
          <Text><strong>影响：</strong>{f.impact}</Text>
          <Text><strong>处理：</strong>{f.action}</Text>
          <Text tone="secondary"><strong>证据与边界：</strong>{f.proof}</Text>
          <Link href={source+f.file}>{f.file}</Link>
        </Stack>
      </CollapsibleSection></div>)}
    </Stack>}
    {tab === "validation" && <Stack gap={20}>
      <H2>完成的验证</H2>
      <Table framed={false} headers={["范围","执行内容","结果","环境与限制"]} rows={validation} />
      <H2>保留的实际验收</H2>
      <Table framed={false} headers={["项目","边界"]} rows={pending} />
      <Text tone="secondary">测试数量不代表覆盖率。离线原生截图、浏览器动画和真实设备隔离检查，都不等同于已安装应用的托盘交互或真实额度控制验收。</Text>
    </Stack>}
    <Divider />
    <Row gap={16} wrap><Link href={reportUrl}>完整审查、代码位置和模拟预览</Link><Text size="small" tone="secondary">公开报告不包含真实账号、聊天正文、运行数据库或设备连接资料。</Text></Row>
  </Stack>;
}
