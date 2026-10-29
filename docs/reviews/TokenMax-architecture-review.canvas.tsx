import { Callout, CollapsibleSection, Divider, Grid, H1, H2, H3, Link, Pill, Row, Stack, Stat, Table, Text, useCanvasState, useHostTheme } from "cursor/canvas";

const source = "https://github.com/Dddysun/Codex-Mission-Manager/blob/codex/runtime-cache-and-architecture-review/";
const reportUrl = source + "docs/reviews/2026-10-29-code-review.md";

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
  { id:"F14", priority:"P1", state:"已修复", title:"旧状态和并发偏好可覆盖用户撤销", impact:"后台读修订号后，用户可以先关闭榨汁，随后被旧状态整行写回；不同聊天的偏好也可能互相覆盖。", action:"读取前取得写锁；许可、偏好、修订号和接管请求原子提交；注册与接管再次核对撤销。", proof:"两个真实 SQLite 连接复现；旧版回归失败，修复通过；另测 24 项并发撤销、延迟接管和失败回滚。", file:"backend/tests/test_store_concurrency.py" },
  { id:"F15", priority:"P2", state:"已修复", title:"排序重复全遍历聊天目录", impact:"每个排序键都重扫目录，已有字典没有用于直接查找，查找量约 N²。", action:"按现有 key 直接查时间；保持降序及相同时间的稳定顺序。", proof:"模拟 3,000 聊天 state() 三次中位数约 115.210 → 9.507 毫秒；不代表实际界面或联网提速倍数。", file:"backend/ui.py" },
  { id:"F16", priority:"P2", state:"已修复", title:"本机 HTTP 资源和错误响应边界", impact:"空闲连接可长期占用线程；Windows 在拒绝未读正文时可能收不到错误提示。", action:"5 秒 I/O 空闲期限、16 个工作线程上限；有界丢弃拒绝正文，回收名额并处理正常断开。", proof:"真实临时套接字测试覆盖空闲、未完成正文、上限与恢复、错误输入和 32 KiB 等号。", file:"backend/tests/test_http_boundaries.py" },
  { id:"F17", priority:"P2", state:"已修复", title:"超大整数触发额度校验溢出", impact:"math.isfinite 对超大整数会抛 OverflowError，无法走预期的拒绝或忽略路径。", action:"共用安全有限数值检查；无效窗口拒绝、可选权益时间忽略、异常归因样本不替换基线。", proof:"覆盖布尔、容器、字符串、NaN、无穷和正负超大整数；指令另测空白与 8,000／8,001 码点。", file:"backend/tests/test_review_boundaries.py" },
  { id:"F18", priority:"P2", state:"安全待办", title:"敏感本地记录未做应用层加密", impact:"指令、目标、标题和账号资料可存在普通 SQLite／JSON 中，文件权限不是加密。", action:"先减少保存与明确期限，再设计密钥管理、认证加密、迁移和备份；覆盖 WAL、日志和旧副本。", proof:"纯模拟指令可在数据库字节中读到；未判断用户 FileVault／BitLocker 状态，未修改真实数据。", file:"backend/guardian.py" },
  { id:"F19", priority:"P2", state:"安全待办", title:"本机握手缺少应用或系统用户身份边界", impact:"任何能访问端口的本机程序可通过 GET / 取得 Cookie；跨站头检查不能认证本机进程。", action:"启动私有管道传递随机能力凭据；明确旧后台兼容，并验证其他 OS 用户和端口竞争。", proof:"匿名隔离客户端取得会话并提交模拟动作；未攻击真实服务或切换系统用户，不是互联网远程执行证据。", file:"backend/ui.py" },
  { id:"F20", priority:"P3", state:"改进", title:"Windows 行缓存缺少按目录淘汰", impact:"已离开目录的聊天行可保留到主题或界面重建，长期增删聊天可能积累对象。", action:"仅淘汰离开完整目录的行；保留筛选隐藏、正在编辑和有草稿的状态，并测内存曲线。", proof:"代码确认缓存插入与清空路径；尚未量化生产内存增长或确认崩溃。", file:"windows/MissionManager.cs" },
  { id:"F21", priority:"P2", state:"已修复", title:"大快照忽略配置的等待预算", impact:"Windows 完整套件中合法大帧超过固定 5 秒等待，随后管道关闭产生次级错误。", action:"采用配置的有限传输预算，保留短诊断连接的最低快照窗口；大帧夹具采用生产预算。", proof:"真实隔离大帧回归；虚拟时钟验证 6 秒到达可在 10 秒预算中返回、缺失快照仍到期清 owner。", file:"backend/tests/test_transport_deadlines.py" },
];

const validation = [
  ["Mac 后台", "349 项执行，3 项平台跳过", "失败 0／错误 0", "完整隔离套件"],
  ["宿主与资源校验器", "31 项", "全部通过", "隔离夹具"],
  ["Mac 前轮候选 DMG", "挂载、自检、可写副本", "冷导入后文件与签名保持完整", "未安装；不含本次追加源码"],
  ["Mac 原生", "状态契约、IME、草稿、生命周期", "通过", "无生产后台"],
  ["Windows 首轮完整回归", "347 项，5 项跳过", "1 项失败／4 项错误", "保留首次失败；包含同一大帧测试的清理错误"],
  ["Windows 最终完整回归", "349 项，5 项平台跳过；宿主另 31 项", "失败 0／错误 0", "真实设备隔离目录；五份改动后端摘要与本地相同"],
  ["Windows 首轮通信超时", "5 项", "全部通过", "历史阻塞模拟记录；现已包括在完整回归中"],
  ["Windows 首轮原生", "构建、编辑器、生命周期、深浅预览", "通过", "前轮候选；未创建真实系统托盘"],
  ["Windows 真实只读连接", "额度、握手、状态、自身连接重连", "通过", "无消息发送、无任务中断"],
  ["品牌组件", "动画、暂停、主题、减少动态效果等", "通过", "离线浏览器"],
];

const dimensions = [
  ["正确性", "并发撤销优先已补齐；大快照采用配置预算", "F14、F21；真实低额度链路仍待验收"],
  ["可读性", "模块命名基本清楚；原生端和后台大类职责集中", "拆分职责、类型化接口、说明安全不变量"],
  ["错误处理", "严格数值与长度边界；Windows 拒绝响应修复", "错误码、双语提示和损坏数据恢复指引仍需统一"],
  ["性能", "排序改用字典直接查询，避免重复全扫描", "全量快照、请求历史和行缓存仍需量化优化"],
  ["安全", "资源有界、参数绑定、IPC 来源与发布摘要检查", "明文敏感记录、本机身份认证是明确待办"],
];

const coverage = [
  ["额度与规则", "阈值等号、缺窗口、权限未知、非法类型、NaN／溢出", "自动化；真实服务变化持续补样例"],
  ["暂停／续接", "新输入、审批、账号变化、目标、重启和不重发", "自动化；真实低额度完整链路未验"],
  ["立刻执行", "空白、8,000／8,001、UUID、幂等、过期、二次复核", "模拟发送；未向真实聊天发消息"],
  ["预约", "窗口身份、取消、修改、提前余额恢复和只发一次", "模拟；官方提前恢复事件未观察"],
  ["并发许可", "真实 SQLite 竞争、24 个聊天撤销、回滚和延迟接管", "新回归；旧版反例失败"],
  ["HTTP", "来源检查、JSON、32 KiB、空闲、上限与恢复", "真实临时套接字；OS 用户隔离未实现"],
  ["状态与目录", "大帧、超限、断线、重连、历史路径及当前回合", "模拟与只读连接；长期压力未测"],
  ["进程与原生 UI", "自有进程清理、编辑器、草稿、窗口和主题预览", "夹具；非所有控件与输入法穷举"],
  ["安装／托盘／电源", "载荷、哈希、路径、原生生命周期和禁用辅助服务", "真实 Windows 升级、托盘与合盖未验"],
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
      <H1>TokenMax 整体代码审查</H1>
      <Text tone="secondary">2026-10-29 · Asia/Dubai · 基线 0.4.1 preview.11 · 修复候选 0.4.2</Text>
      <Text>保留共享后台与双原生界面，优先完善可靠性、采集隔离和维护边界。</Text>
    </Stack>
    <Row gap={24} wrap>
      <Stat value={String(findings.filter(f=>f.state==='已修复').length)} label="已修复的具体缺陷" />
      <Stat value={String(findings.filter(f=>f.state!=='已修复').length)} label="安全、架构与维护待办" />
      <Stat value="5" label="仍需现场或自然事件验收" />
    </Row>
    <Row gap={8} wrap>
      {[['overview','结论与改进顺序'],['dimensions','五项审查与测试范围'],['findings','全部发现'],['validation','验收与边界']].map(([key,title]) =>
        <span key={key}><Pill active={tab===key} onClick={()=>setTab(key)}>{title}</Pill></span>)}
    </Row>
    <Divider />
    {tab === "overview" && <Stack gap={20}>
      <Callout title="本轮结论" tone="info">累计七类源码修复，包含用户撤销被旧状态覆盖、通信与快照期限、输入及 HTTP 边界。敏感记录未加密、本机进程身份隔离不足仍需处理。前轮候选包不含本次追加源码，实际安装未升级。</Callout>
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
        ["源码审查","审查七类修复和新增反例","资源不变、撤销优先、有界等待、不确定发送不重试"],
        ["安全","本机能力凭据与敏感记录保护","身份边界明确；密钥、WAL、备份和迁移可验证"],
        ["合并前","PR 自动验证与统一接口样例","两平台共同检查，验证任务不能发布"],
        ["性能","分离采集与控制，减少全量重复读取","慢聊天不拖住额度采样；按完整周期测量"],
        ["维护","拆分原生端职责与外部依赖","保留草稿、IME、生命周期和原生窗口"],
        ["产品决定","新聊天接管规则与辅助服务开放条件","许可语义明确；高权限功能开放前完成恢复测试"],
      ]} />
      <H2>应保留的可靠性设计</H2>
      <Text>持久化动作意图与唯一标识、发送结果不确定时停止重试、手动保持和审批保护、账号隔离、应用自有进程回收、运行环境哈希及模拟数据预览。</Text>
    </Stack>}
    {tab === "dimensions" && <Stack gap={20}>
      <H2>五个方面的审查结论</H2>
      <Table framed={false} headers={["方面","结论","已修复及剩余范围"]} rows={dimensions} />
      <Callout title="没有宣称所有功能都测过" tone="info">测试数量不是覆盖率。本轮没有逐行或分支覆盖率统计；真实聊天保持运行，发送与中断只在模拟器中测试。</Callout>
      <H2>功能与边界对应</H2>
      <Table framed={false} headers={["功能","输入及异常边界","验证边界"]} rows={coverage} />
      <Link href={reportUrl}>查看逐功能测试文件、错误处理与完整安全分析</Link>
    </Stack>}
    {tab === "findings" && <Stack gap={16}>
      <Row gap={8} wrap>
        {[['all','全部 21 项'],['fixed','已修复 7 项'],['next','后续 14 项']].map(([key,title]) =>
          <span key={key}><Pill active={filter===key} onClick={()=>setFilter(key)}>{title}</Pill></span>)}
      </Row>
      <Text tone="secondary">P1 为优先可靠性缺陷；P2 包含已修复的边界缺陷及仍需安排的安全和结构改进；P3 为维护增强。产品规则和启用前置条件单独标注。</Text>
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
