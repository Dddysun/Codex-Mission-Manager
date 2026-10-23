import Foundation

@main enum NativeContractTests {
    static func main() throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let state = try JSONDecoder().decode(MissionSnapshot.self, from: data)
        if CommandLine.arguments.contains("--decode-only") { print("Native decoder accepted live snapshot: \(state.tasks.count) chats, \(state.events.count) events"); return }
        var idle = state.tasks[1]
        precondition(idle.canExecute && !state.tasks[0].canExecute && !state.tasks[2].canExecute)
        precondition(idle.status == "等待指令")
        idle.runtime?.activeFlags = ["waitingForApproval"]
        precondition(!idle.canExecute && idle.status == "等待你处理")
        idle.runtime?.activeFlags = []
        let draft = MissionDraft(text: "先核对进度，再整理文档", revision: 1)
        let save = MissionCommands.plan(idle, draft: draft, enabled: true)
        precondition(save["revision"] as? Int == 1, "A polling refresh must not silently rebase an edited plan")
        precondition(save["prompt"] as? String == draft.text)
        let cancel = MissionCommands.plan(idle, draft: draft, enabled: false)
        precondition(cancel["revision"] as? Int == 2 && cancel["prompt"] as? String == "继续任务")
        let immediate = MissionCommands.immediate(idle, draft: draft, requestID: "stable-request")
        precondition(immediate["action"] as? String == "execute_now" && immediate["revision"] as? Int == 3)
        precondition(immediate["request_id"] as? String == "stable-request")
        precondition(immediate["enabled"] == nil, "Immediate send must not arm or change a future plan")
        let automatic = MissionCommands.automatic(idle, enabled: false)
        precondition(automatic["action"] as? String == "set_auto" && automatic["enabled"] as? Bool == false)
        precondition(automatic["prompt"] == nil)
        precondition(MissionQuota(remaining: nil, reset: nil).validRemaining == nil)
        precondition(MissionQuota(remaining: 101, reset: nil).validRemaining == nil)
        precondition(MissionQuota(remaining: 0, reset: nil).validRemaining == 0)
        precondition(state.usage?.account?.subscription == "Plus")
        idle.connection_error = "offline"
        precondition(idle.status == "连接待恢复")
        print("Native snapshot / status / control contract checks passed")
    }
}
