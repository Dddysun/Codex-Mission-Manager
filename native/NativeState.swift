import Foundation

// Repeated Quit requests must share one cleanup and one AppKit reply. Closing a
// window is deliberately not a transition in this application lifecycle.
struct MissionTerminationState {
    enum Phase { case running, waiting, ready }
    private(set) var phase: Phase = .running
    mutating func request() -> Bool {
        guard phase == .running else { return false }
        phase = .waiting
        return true
    }
    mutating func complete() -> Bool {
        guard phase == .waiting else { return false }
        phase = .ready
        return true
    }
}

struct MissionStopReceipt {
    var hostExited: Bool
    var terminateRequested: Bool
    var forceKillRequested: Bool
    var deadlineReached: Bool
}

// Public, allowlisted backend snapshot. Optional fields remain unknown rather than
// being interpreted as unlimited quota or permission to execute.
struct MissionSnapshot: Decodable {
    var observed_at: Double?
    var running: Bool
    var healthy: Bool
    var stale: Bool
    var control_paused: Bool
    var control_enabled: Bool
    var control_revision: Int
    var tasks: [MissionChat]
    var events: [MissionEvent]
    var usage: MissionUsage?
    var catalog: MissionCatalog?
    var policy: MissionPolicy
    var compatibility: MissionCompatibility?
    var bulk_pause: MissionBulkPause?
    var poll_seconds: Double
    var ui_poll_seconds: Double?
    var rules: MissionRules?
    var codexTasks: [MissionChat] { tasks.filter { $0.isCodex } }
}
struct MissionCatalog: Decodable {
    var observed_at: Double?
    var cloud_observed_at: Double?
    var local_error: String?
}
struct MissionPolicy: Decodable { var pause: Double; var resume: Double; var confirm_seconds: Double }
struct MissionUsage: Decodable {
    var account: MissionAccount?
    var windows: MissionWindows
    var observed_at: Double?
    var stale: Bool?
    var quota_windows: [MissionQuotaWindow]?
    var quota_state: String?
    var service_allowed: Bool?
    var blocked: Bool?
    var scheduling_available: Bool?
    var scheduling_window: MissionQuotaWindow?
    var limit_name: String?
    var reset_credits: MissionResetCredits?
    var visibleWindows: [MissionQuotaWindow] {
        if let quota_windows { return quota_windows }
        // A V0.2 snapshot has only the two legacy display slots.
        var result: [MissionQuotaWindow] = []
        if let value=windows.five_hour { result.append(MissionQuotaWindow(id:"duration:300",kind:"five_hour",minutes:300,remaining:value.remaining,reset:value.reset)) }
        if let value=windows.weekly { result.append(MissionQuotaWindow(id:"duration:10080",kind:"weekly",minutes:10080,remaining:value.remaining,reset:value.reset)) }
        return result
    }
    var canSchedule: Bool { scheduling_available ?? !visibleWindows.isEmpty }
    func permitsImmediate(minimum: Double) -> Bool {
        // V0.2 snapshots do not advertise the new permission state. Keep their
        // existing button behavior; the backend always rechecks before sending.
        guard blocked != true, service_allowed != false else { return false }
        guard let quota_state else { return true }
        guard service_allowed == true, minimum.isFinite else { return false }
        if quota_state == "service_only" { return true }
        guard quota_state == "metered", !visibleWindows.isEmpty else { return false }
        return visibleWindows.allSatisfy { window in
            guard let remaining=window.value.validRemaining else { return false }
            return window.minutes == 10080 ? remaining > 0 : remaining >= minimum
        }
    }
    var schedulingUnavailableNote: String {
        if quota_state == "service_only", service_allowed == true, blocked != true {
            return L("当前账号未提供可预约的额度刷新窗口，请使用立刻执行。")
        }
        if let availabilityNote { return availabilityNote }
        return L("当前账号未提供可预约的额度刷新窗口。")
    }
    var scheduleWindow: MissionQuotaWindow? {
        guard canSchedule else { return nil }
        if let scheduling_window { return scheduling_window }
        func priority(_ window: MissionQuotaWindow) -> Int { window.minutes == 300 ? 0 : window.minutes == 10080 ? 2 : 1 }
        return visibleWindows.sorted {
            if priority($0) != priority($1) { return priority($0) < priority($1) }
            if $0.minutes != $1.minutes { return $0.minutes < $1.minutes }
            return $0.id < $1.id
        }.first
    }
    var availabilityNote: String? {
        if blocked == true { return L("服务暂不允许使用，等待重新核验") }
        if quota_state == "service_only", service_allowed == true { return L("服务已允许使用，未提供固定额度窗口") }
        if quota_state == "unknown" || visibleWindows.isEmpty { return L("额度信息不完整，自动发送暂不可用") }
        if service_allowed == false { return L("服务使用许可待确认，自动发送暂不可用") }
        return nil
    }
    var missingWindowNote: String? {
        guard !visibleWindows.isEmpty else { return nil }
        let hasFive=visibleWindows.contains { $0.kind == "five_hour" }
        let hasWeek=visibleWindows.contains { $0.kind == "weekly" }
        if !hasFive && !hasWeek { return L("仅显示服务返回的额度窗口") }
        if !hasFive { return L("未提供五小时窗口") }
        if !hasWeek { return L("未提供周额度窗口") }
        return nil
    }
}
struct MissionAccount: Decodable {
    var id: String?; var name: String?; var email: String?; var type: String?
    var plan_type: String?; var avatar_url: String?
    var displayName: String { name ?? email?.components(separatedBy: "@").first ?? L("未识别账号") }
    var initials: String { String(displayName.split(separator: " ").prefix(2).compactMap { $0.first }).uppercased() }
    var subscription: String {
        guard let plan_type, !plan_type.isEmpty else { return L("待识别") }
        let known = ["free":"Free", "plus":"Plus", "pro":"Pro", "go":"Go", "team":"Team", "business":"Business", "enterprise":"Enterprise", "edu":"Edu"]
        return known[plan_type.lowercased()] ?? plan_type
    }
}
struct MissionWindows: Decodable { var five_hour: MissionQuota?; var weekly: MissionQuota? }
struct MissionQuota: Decodable {
    var remaining: Double?; var reset: Double?
    var validRemaining: Double? {
        guard let remaining, remaining.isFinite, (0...100).contains(remaining) else { return nil }
        return remaining
    }
}
struct MissionQuotaWindow: Decodable, Identifiable {
    var id: String
    var kind: String
    var minutes: Double
    var remaining: Double?
    var reset: Double?
    var value: MissionQuota { MissionQuota(remaining:remaining,reset:reset) }
    var title: String {
        if minutes == 300 { return L("五小时额度") }
        if minutes == 10080 { return L("周额度") }
        if minutes > 0 && minutes.truncatingRemainder(dividingBy:1440) == 0 { return L("%@天额度",String(format:"%.0f",minutes/1440)) }
        if minutes > 0 && minutes.truncatingRemainder(dividingBy:60) == 0 { return L("%@小时额度",String(format:"%.0f",minutes/60)) }
        return L("%@分钟额度",String(format:"%.0f",minutes))
    }
}
struct MissionRuntime: Decodable { var type: String?; var activeFlags: [String]? }
struct MissionStage: Decodable { var text: String?; var phase: String?; var updated_at: Double? }
struct MissionPlan: Decodable {
    var state: String; var prompt: String?; var revision: Int; var reason: String?
    var armed_window_minutes: Double?; var armed_window_reset: Double?
    var scheduled: Bool { ["armed", "sending"].contains(state) }
    var label: String {
        ["off":L("未预约"), "armed":L("等待下一窗口恢复"), "sending":L("正在确认发送"), "sent":L("已发送一次，预约已关闭"), "cancelled":L("已取消预约"), "needs_review":L("需要重新确认预约")][state] ?? state
    }
}
struct MissionReceipt: Decodable {
    var id: String; var state: String; var message: String?; var turn_id: String?
    var pending: Bool { ["pending", "checking", "sending"].contains(state) }
    var label: String {
        ["pending":L("待发送"), "checking":L("正在检查"), "sending":L("正在确认发送"), "sent":L("已确认发送"), "failed":L("未发送"), "unknown":L("发送结果待核对")][state] ?? state
    }
}
struct MissionChat: Decodable, Identifiable {
    var id: String; var key: String; var name: String; var state: String
    var auto_resume: Bool; var manual_hold: Bool; var revision: Int
    var auto_connection: String?; var auto_error: String?
    var auto_pending: Bool?; var can_control: Bool?; var capability_note: String?
    var runtime: MissionRuntime?; var category: String?; var source_label: String?
    var execution_stage: MissionStage?; var plan: MissionPlan?; var immediate: MissionReceipt?
    var reason: String?; var connection_error: String?; var recovery_first_seen: Double?
    var paused_at: Double?; var resumed_at: Double?; var goal: Bool?
    var host_id: String?
    var isLocal: Bool {
        if let host_id, host_id != "local" { return false }
        // Older snapshots omit host_id. Their namespaced key still identifies
        // the host; a bare legacy key with a Codex category keeps its fallback.
        if key.hasPrefix("codex:") { return key.hasPrefix("codex:local:") }
        return host_id == "local" || (host_id == nil && category == "codex")
    }
    var isCodex: Bool { isLocal && (category == "codex" || (category == nil && key.hasPrefix("codex:"))) }
    var sourceTitle: String { isLocal ? L("Codex · 本机") : L("Codex · 远程") }
    var controllable: Bool { can_control == true }
    var automatic: Bool { auto_resume && !manual_hold && state != "disabled" }
    var waiting: Bool { ["paused", "pause_intent", "resume_intent"].contains(state) }
    var attention: Bool {
        auto_connection == "failed" || connection_error != nil || state == "needs_review" || plan?.state == "needs_review" || !(runtime?.activeFlags ?? []).isEmpty || runtime?.type == "systemError"
    }
    var active: Bool { !attention && !waiting && runtime?.type == "active" }
    var canExecute: Bool {
        controllable && immediate?.pending != true && plan?.state != "sending" && runtime?.type != "active" && (runtime?.activeFlags ?? []).isEmpty
    }
    var status: String {
        if auto_connection == "waiting_global" { return L("等待全局启用") }
        if auto_connection == "queued" { return L("等待连接") }
        if auto_connection == "failed" { return L("连接失败，可重试") }
        if state == "paused" && manual_hold { return L("手动暂停") }
        if connection_error != nil { return L("连接待恢复") }
        if state == "needs_review" || plan?.state == "needs_review" { return L("需要检查") }
        if state == "pause_intent" { return L("确认暂停中") }
        if state == "resume_intent" { return L("确认续做中") }
        if state == "paused" { return recovery_first_seen == nil ? L("等待恢复") : L("复核恢复条件") }
        if !(runtime?.activeFlags ?? []).isEmpty { return L("等待你处理") }
        if runtime?.type == "active" { return L("执行中") }
        if auto_pending == true { return L("正在连接") }
        return ["idle":L("等待指令"), "notLoaded":L("未打开"), "systemError":L("回合出错")][runtime?.type ?? ""] ?? (controllable ? L("状态待核对") : L("状态待同步"))
    }
}
enum MissionEventOrigin: String { case user, automatic }

// Filtering is local to the latest 200 cached records. It never changes the
// snapshot or derives origin from event type, task state or reset evidence.
enum MissionActivityFilter: String, CaseIterable, Identifiable {
    case all, user, automatic
    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: return L("全部记录")
        case .user: return L("用户操作")
        case .automatic: return L("自动进程")
        }
    }
    func apply(to events: [MissionEvent]) -> [MissionEvent] {
        Array(events.prefix(200)).filter { self == .all || $0.origin.rawValue == rawValue }
    }
}

struct MissionEvent: Decodable, Identifiable {
    var id: Int; var created: Double; var state: String; var name: String?
    var detail: MissionEventDetail?
    var thread_id: String?
    var origin: MissionEventOrigin
    private var hasThreadMetadata: Bool
    private enum CodingKeys: String, CodingKey { case id, created, state, name, detail, thread_id, origin }
    init(from decoder: Decoder) throws {
        let values=try decoder.container(keyedBy:CodingKeys.self)
        id=try values.decode(Int.self,forKey:.id);created=try values.decode(Double.self,forKey:.created)
        state=try values.decode(String.self,forKey:.state);name=try values.decodeIfPresent(String.self,forKey:.name)
        detail=try values.decodeIfPresent(MissionEventDetail.self,forKey:.detail)
        thread_id=try values.decodeIfPresent(String.self,forKey:.thread_id)
        origin=MissionEventOrigin(rawValue:(try? values.decode(String.self,forKey:.origin)) ?? "") ?? .automatic
        hasThreadMetadata=values.contains(.thread_id)
    }
    var isQuotaRestored: Bool { state == "quota_restored" }
    var isGlobal: Bool { isQuotaRestored || (hasThreadMetadata && (thread_id?.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty != false)) }
    var scopeTitle: String {
        if isQuotaRestored { return L("全局额度事件") }
        if isGlobal { return L("全局控制") }
        return name ?? L("全局控制")
    }
    var label: String {
        if isQuotaRestored { return MissionQuotaRestorationText.category(detail?.category) }
        if let allowed = detail?.automatic_control_allowed { return allowed ? L("允许自动控制") : L("保持任务") }
        return ["rules_updated":L("运行规则已更新"),"watching":L("纳入监测"), "pause_intent":L("开始暂停"), "paused":L("已确认暂停"), "resume_intent":L("提交续做"), "running":L("已续做"), "needs_review":L("需要核对"), "disabled":L("已撤销控制"), "held":L("保持任务"), "supervisor_paused":L("暂停自动控制"), "supervisor_enabled":L("启用自动控制"), "plan_armed":L("预约下一窗口执行"), "plan_sending":L("提交预约指令"), "plan_sent":L("预约指令已发送"), "plan_cancelled":L("取消预约"), "plan_needs_review":L("预约需要确认"), "immediate_pending":L("提交立刻执行"), "immediate_sent":L("立刻执行已确认发送"), "immediate_failed":L("立刻执行未发送"), "immediate_unknown":L("立刻执行结果待核对")][state] ?? state
    }
    var restorationLines: [String] {
        guard isQuotaRestored else { return [] }
        var lines=[L("根据余额、刷新时间和重置权益变化判定"),L("此分类为证据推断，并非官方直接原因说明。")]
        if detail?.category == "user_reset" { lines.append(L("依据权益变化判定")) }
        lines.append(L("观测时间：%@ → %@",MissionQuotaRestorationText.time(detail?.previous_observed_at),MissionQuotaRestorationText.time(detail?.observed_at)))
        let windows=detail?.windows ?? []
        if windows.isEmpty { lines.append(L("未提供可核实的额度窗口变化。")) }
        for window in windows {
            lines.append(L("%@ · 余额 %@ → %@",window.title,MissionQuotaRestorationText.percent(window.previous_remaining),MissionQuotaRestorationText.percent(window.remaining)))
            lines.append(L("刷新时间：%@ → %@",MissionQuotaRestorationText.time(window.previous_reset),MissionQuotaRestorationText.time(window.reset)))
            if let classification=window.classification { lines.append(L("窗口判定：%@",MissionQuotaRestorationText.category(classification))) }
        }
        if let credits=detail?.reset_credits, credits.hasKnownCount {
            lines.append(L("重置权益次数：%@ → %@",MissionQuotaRestorationText.count(credits.previous_available_count),MissionQuotaRestorationText.count(credits.available_count)))
        } else { lines.append(L("重置权益次数未提供。")) }
        return lines
    }
}
struct MissionEventDetail: Decodable {
    var reason: String?; var source: String?; var automatic_control_allowed: Bool?
    var recovery_reason: String?
    var category: String? = nil
    var classification_basis: String? = nil
    var previous_observed_at: Double? = nil
    var observed_at: Double? = nil
    var windows: [MissionQuotaRestorationWindow]? = nil
    var reset_credits: MissionQuotaRestorationCredits? = nil
    var recoveryNote: String? {
        guard let recovery_reason else {return nil}
        switch recovery_reason {
        case "window_advanced":return L("观察到新额度窗口")
        case "balance_restored":return L("可用余额恢复；重置原因未知")
        case "quota_available":return L("额度已重新核验可用")
        case "service_permission_restored":return L("服务许可已恢复")
        default:return L("恢复原因待核实")
        }
    }
}
struct MissionQuotaRestorationWindow: Decodable {
    var minutes: Double?
    var previous_remaining: Double?
    var remaining: Double?
    var previous_reset: Double?
    var reset: Double?
    var classification: String?
    var title: String {
        guard let minutes, minutes.isFinite, minutes>0 else {return L("额度窗口未提供")}
        return MissionQuotaWindow(id:"event-window",kind:"",minutes:minutes,remaining:nil,reset:nil).title
    }
}
struct MissionQuotaRestorationCredits: Decodable {
    var previous_available_count: Double?
    var available_count: Double?
    var delta: Double?
    var hasKnownCount: Bool { MissionQuotaRestorationText.validCount(previous_available_count) != nil || MissionQuotaRestorationText.validCount(available_count) != nil }
}
enum MissionQuotaRestorationText {
    static func category(_ value: String?) -> String {
        switch value {
        case "user_reset":return L("用户主动恢复")
        case "official_scheduled_reset":return L("官方正常周期重置")
        case "official_independent_reset":return L("官方独立重置")
        default:return L("额度恢复·原因待确认")
        }
    }
    static func percent(_ value: Double?) -> String {
        guard let value, value.isFinite, (0...100).contains(value) else {return L("未提供")}
        return String(format:"%.1f%%",value)
    }
    static func validCount(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value>=0, value.rounded()==value else {return nil}
        return value
    }
    static func count(_ value: Double?) -> String {
        guard let value=validCount(value) else {return L("未提供")}
        return String(format:"%g",value)
    }
    static func time(_ value: Double?) -> String {
        guard let value, value.isFinite, value>0 else {return L("未提供")}
        return missionTime(value)
    }
}
struct MissionDraft { var text: String; var revision: Int }

func missionTime(_ stamp: Double?) -> String {
    guard let stamp, stamp.isFinite, stamp > 0 else { return L("尚未提供") }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "zh_CN")
    formatter.timeZone = .current
    formatter.dateFormat = "MM/dd HH:mm:ss"
    return formatter.string(from: Date(timeIntervalSince1970: stamp))
}

// One source of truth for native control requests; the backend still rechecks
// account, quota, current turn and durable idempotency before dispatching.
enum MissionCommands {
    static func rules(_ values: [String:Int], revision: Int) -> [String:Any] {
        ["action":"set_rules", "rules_revision":revision, "rules":values]
    }
    static func automatic(_ chat: MissionChat, enabled: Bool) -> [String: Any] {
        ["action":"set_auto", "key":chat.key, "enabled":enabled, "revision":chat.revision]
    }
    static func plan(_ chat: MissionChat, draft: MissionDraft?, enabled: Bool) -> [String: Any] {
        let prompt = enabled ? draft?.text ?? chat.plan?.prompt ?? L("继续任务") : chat.plan?.prompt ?? L("继续任务")
        let revision = enabled ? draft?.revision ?? chat.plan?.revision ?? 0 : chat.plan?.revision ?? 0
        return ["action":"set_plan", "key":chat.key, "enabled":enabled, "prompt":prompt, "revision":revision]
    }
    static func immediate(_ chat: MissionChat, draft: MissionDraft?, requestID: String = UUID().uuidString.lowercased()) -> [String: Any] {
        ["action":"execute_now", "key":chat.key, "prompt":draft?.text ?? chat.plan?.prompt ?? L("继续任务"), "revision":chat.revision, "request_id":requestID]
    }
}

enum MissionAccent: String, CaseIterable {
    case green, blue, purple, yellow
    var title: String {
        switch self { case .green:return L("绿色");case .blue:return L("蓝色");case .purple:return L("紫色");case .yellow:return L("鹅蛋黄") }
    }
    var lightHex: String {
        switch self {case .green:return "3F765F";case .blue:return "326CB5";case .purple:return "7856B1";case .yellow:return "D9B95F"}
    }
    var darkHex: String {
        switch self {case .green:return "7FB795";case .blue:return "85B4F0";case .purple:return "B39ADE";case .yellow:return "E5CA80"}
    }
    var lightTextHex: String { self == .yellow ? "302717" : "FFFFFF" }
    var darkTextHex: String {
        switch self {case .green:return "102117";case .blue:return "10223B";case .purple:return "21182F";case .yellow:return "2D2411"}
    }
    var lightSelectedHex: String {
        switch self {case .green:return "35423D";case .blue:return "2D435F";case .purple:return "423553";case .yellow:return "514832"}
    }
    var darkSelectedHex: String {
        switch self {case .green:return "2A332F";case .blue:return "223149";case .purple:return "30243F";case .yellow:return "3C331E"}
    }
    var lightInkHex: String {
        switch self {case .green:return "192822";case .blue:return "162638";case .purple:return "241E34";case .yellow:return "302A1B"}
    }
    var darkInkHex: String {
        switch self {case .green:return "0D1712";case .blue:return "0E1724";case .purple:return "171222";case .yellow:return "1E1A11"}
    }
}

struct MissionRuleBound: Decodable { var min: Int; var max: Int }
struct MissionRules: Decodable {
    var revision: Int
    var values: [String:Int]
    var bounds: [String:MissionRuleBound]?
    func confirms(_ submitted:[String:Int], after revision:Int) -> Bool {
        self.revision > revision && values == submitted
    }
}
enum MissionRuleFields {
    static let keys = ["pause_remaining","resume_remaining","poll_seconds","near_limit_poll_seconds","recovery_confirm_seconds","ui_poll_seconds"]
    static let defaults = ["pause_remaining":10,"resume_remaining":20,"poll_seconds":30,"near_limit_poll_seconds":10,"recovery_confirm_seconds":5,"ui_poll_seconds":5]
    static let bounds = ["pause_remaining":1...50,"resume_remaining":5...95,"poll_seconds":10...300,"near_limit_poll_seconds":5...60,"recovery_confirm_seconds":3...60,"ui_poll_seconds":2...30]
    static func title(_ key:String) -> String {
        L(["pause_remaining":"暂停阈值（剩余 %）","resume_remaining":"恢复阈值（剩余 %）","poll_seconds":"正常采集间隔（秒）","near_limit_poll_seconds":"临近阈值采集间隔（秒）","recovery_confirm_seconds":"恢复复核时间（秒）","ui_poll_seconds":"界面刷新间隔（秒）"][key] ?? key)
    }
    static func validation(_ text:[String:String], remoteBounds:[String:MissionRuleBound]? = nil) -> (values:[String:Int]?,error:String?) {
        var values=[String:Int]()
        for key in keys {
            guard let raw=text[key], let value=Int(raw.trimmingCharacters(in:.whitespacesAndNewlines)) else { return (nil,L("请为每项规则输入整数。")) }
            let local=bounds[key]!
            let minimum=max(local.lowerBound,remoteBounds?[key]?.min ?? local.lowerBound)
            let maximum=min(local.upperBound,remoteBounds?[key]?.max ?? local.upperBound)
            guard value>=minimum && value<=maximum else { return (nil,L("%@的范围为 %@–%@。",title(key),String(minimum),String(maximum))) }
            values[key]=value
        }
        guard values["resume_remaining"]! >= values["pause_remaining"]!+5 else { return (nil,L("恢复阈值必须至少比暂停阈值高 5%。")) }
        guard values["near_limit_poll_seconds"]! <= values["poll_seconds"]! else { return (nil,L("临近阈值采集间隔不能大于正常采集间隔。")) }
        return (values,nil)
    }
}

// Polling must never replace an active IME composition, caret or local draft.
// This policy is shared by the real NSTextView adapter and contract tests.
enum MissionPromptSynchronization {
    static func shouldApply(current:String,incoming:String,editing:Bool,marked:Bool,hasDraft:Bool) -> Bool {
        current != incoming && !editing && !marked && !hasDraft
    }
    static func selection(_ selected:NSRange, utf16Length:Int) -> NSRange {
        let start=min(max(0,selected.location),utf16Length)
        return NSRange(location:start,length:min(max(0,selected.length),utf16Length-start))
    }
}

struct MissionResetCredit: Decodable {
    var id: String?
    var resetType: String?
    var status: String?
    var grantedAt: Double?
    var expiresAt: Double?
    var title: String?
    var description: String?
    var displayTitle: String { title ?? L("额度重置权益") }
}

struct MissionResetCredits: Decodable {
    var available_count: Double?
    var credits: [MissionResetCredit]?
    var supported: Bool?
    var displayCount: String {
        guard supported == true, let count=available_count, count.isFinite, count>=0 else {return L("未提供")}
        return String(format:"%g",count)
    }
}

struct MissionCompatibility: Decodable {
    var build: String?; var version: String?; var supported: Bool; var status: String
    var live_control_tested: Bool?
}
struct MissionBulkPause: Decodable {
    var state: String; var total: Int; var paused: Int; var skipped: Int; var failed: Int
    var items: [MissionBulkItem]?
}
struct MissionBulkItem: Decodable, Identifiable {
    var thread_id: String; var state: String; var reason: String?
    var id:String { thread_id }
}
