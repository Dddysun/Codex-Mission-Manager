import Foundation

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
struct MissionRuntime: Decodable { var type: String?; var activeFlags: [String]? }
struct MissionStage: Decodable { var text: String?; var phase: String?; var updated_at: Double? }
struct MissionPlan: Decodable {
    var state: String; var prompt: String?; var revision: Int; var reason: String?
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
struct MissionEvent: Decodable, Identifiable {
    var id: Int; var created: Double; var state: String; var name: String?
    var detail: MissionEventDetail?
    var label: String {
        if let allowed = detail?.automatic_control_allowed { return allowed ? L("允许自动控制") : L("保持任务") }
        return ["watching":L("纳入监测"), "pause_intent":L("开始暂停"), "paused":L("已确认暂停"), "resume_intent":L("提交续做"), "running":L("已续做"), "needs_review":L("需要核对"), "disabled":L("已撤销控制"), "held":L("保持任务"), "supervisor_paused":L("暂停自动控制"), "supervisor_enabled":L("启用自动控制"), "plan_armed":L("预约下一窗口执行"), "plan_sending":L("提交预约指令"), "plan_sent":L("预约指令已发送"), "plan_cancelled":L("取消预约"), "plan_needs_review":L("预约需要确认"), "immediate_pending":L("提交立刻执行"), "immediate_sent":L("立刻执行已确认发送"), "immediate_failed":L("立刻执行未发送"), "immediate_unknown":L("立刻执行结果待核对")][state] ?? state
    }
}
struct MissionEventDetail: Decodable {
    var reason: String?; var source: String?; var automatic_control_allowed: Bool?
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
