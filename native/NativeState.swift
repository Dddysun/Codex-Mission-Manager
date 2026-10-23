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
    var displayName: String { name ?? email?.components(separatedBy: "@").first ?? "未识别账号" }
    var initials: String { String(displayName.split(separator: " ").prefix(2).compactMap { $0.first }).uppercased() }
    var subscription: String {
        guard let plan_type, !plan_type.isEmpty else { return "待识别" }
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
        ["off":"未预约", "armed":"等待下一窗口恢复", "sending":"正在确认发送", "sent":"已发送一次，预约已关闭", "cancelled":"已取消预约", "needs_review":"需要重新确认预约"][state] ?? state
    }
}
struct MissionReceipt: Decodable {
    var id: String; var state: String; var message: String?; var turn_id: String?
    var pending: Bool { ["pending", "checking", "sending"].contains(state) }
    var label: String {
        ["pending":"待发送", "checking":"正在检查", "sending":"正在确认发送", "sent":"已确认发送", "failed":"未发送", "unknown":"发送结果待核对"][state] ?? state
    }
}
struct MissionChat: Decodable, Identifiable {
    var id: String; var key: String; var name: String; var state: String
    var auto_resume: Bool; var manual_hold: Bool; var revision: Int
    var auto_pending: Bool?; var can_control: Bool?; var capability_note: String?
    var runtime: MissionRuntime?; var category: String?; var source_label: String?
    var execution_stage: MissionStage?; var plan: MissionPlan?; var immediate: MissionReceipt?
    var reason: String?; var connection_error: String?; var recovery_first_seen: Double?
    var paused_at: Double?; var resumed_at: Double?; var goal: Bool?
    var controllable: Bool { can_control == true }
    var automatic: Bool { auto_resume && !manual_hold && state != "disabled" }
    var waiting: Bool { ["paused", "pause_intent", "resume_intent"].contains(state) }
    var attention: Bool {
        connection_error != nil || state == "needs_review" || plan?.state == "needs_review" || !(runtime?.activeFlags ?? []).isEmpty || runtime?.type == "systemError"
    }
    var active: Bool { !attention && !waiting && runtime?.type == "active" }
    var canExecute: Bool {
        controllable && immediate?.pending != true && plan?.state != "sending" && runtime?.type != "active" && (runtime?.activeFlags ?? []).isEmpty
    }
    var status: String {
        if connection_error != nil { return "连接待恢复" }
        if state == "needs_review" || plan?.state == "needs_review" { return "需要检查" }
        if state == "pause_intent" { return "确认暂停中" }
        if state == "resume_intent" { return "确认续做中" }
        if state == "paused" { return recovery_first_seen == nil ? "等待恢复" : "复核恢复条件" }
        if !(runtime?.activeFlags ?? []).isEmpty { return "等待你处理" }
        if runtime?.type == "active" { return "执行中" }
        if auto_pending == true { return "正在连接" }
        return ["idle":"等待指令", "notLoaded":"未打开", "systemError":"回合出错"][runtime?.type ?? ""] ?? (controllable ? "状态待核对" : "状态待同步")
    }
}
struct MissionEvent: Decodable, Identifiable {
    var id: Int; var created: Double; var state: String; var name: String?
    var detail: MissionEventDetail?
    var label: String {
        if let allowed = detail?.automatic_control_allowed { return allowed ? "允许自动控制" : "保持任务" }
        return ["watching":"纳入监测", "pause_intent":"开始暂停", "paused":"已确认暂停", "resume_intent":"提交续做", "running":"已续做", "needs_review":"需要核对", "disabled":"已撤销控制", "held":"保持任务", "supervisor_paused":"暂停自动控制", "supervisor_enabled":"启用自动控制", "plan_armed":"预约下一窗口执行", "plan_sending":"提交预约指令", "plan_sent":"预约指令已发送", "plan_cancelled":"取消预约", "plan_needs_review":"预约需要确认", "immediate_pending":"提交立刻执行", "immediate_sent":"立刻执行已确认发送", "immediate_failed":"立刻执行未发送", "immediate_unknown":"立刻执行结果待核对"][state] ?? state
    }
}
struct MissionEventDetail: Decodable {
    var reason: String?; var source: String?; var automatic_control_allowed: Bool?
}
struct MissionDraft { var text: String; var revision: Int }

func missionTime(_ stamp: Double?) -> String {
    guard let stamp, stamp.isFinite, stamp > 0 else { return "尚未提供" }
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
        let prompt = enabled ? draft?.text ?? chat.plan?.prompt ?? "继续任务" : chat.plan?.prompt ?? "继续任务"
        let revision = enabled ? draft?.revision ?? chat.plan?.revision ?? 0 : chat.plan?.revision ?? 0
        return ["action":"set_plan", "key":chat.key, "enabled":enabled, "prompt":prompt, "revision":revision]
    }
    static func immediate(_ chat: MissionChat, draft: MissionDraft?, requestID: String = UUID().uuidString.lowercased()) -> [String: Any] {
        ["action":"execute_now", "key":chat.key, "prompt":draft?.text ?? chat.plan?.prompt ?? "继续任务", "revision":chat.revision, "request_id":requestID]
    }
}
