import Foundation

@main enum NativeContractTests {
    static func main() throws {
        NativeLocalization.testLanguage = "zh"
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
        idle.auto_connection = "waiting_global"
        precondition(idle.status == "等待全局启用")
        idle.auto_connection = "queued"
        precondition(idle.status == "等待连接")
        idle.auto_connection = "failed"
        idle.runtime?.type = "active"
        precondition(idle.attention && !idle.active && idle.status == "连接失败，可重试")
        idle.auto_connection = nil
        idle.connection_error = nil
        idle.state = "paused"
        idle.manual_hold = true
        precondition(idle.waiting && !idle.automatic && idle.status == "手动暂停")
        idle.auto_connection = "waiting_global"
        NativeLocalization.testLanguage = "en"
        precondition(idle.status == "Waiting for automation")
        precondition(L("暂停所有任务") == "Pause all tasks")
        precondition(L("客户端 %@ · 兼容配置已匹配", "21828") == "Client 21828 · Compatibility profile matched")
        precondition(!NativeLocalization.english.values.contains { $0.contains("本机预览") })
        let fixtureDirectory = URL(fileURLWithPath: CommandLine.arguments[1]).deletingLastPathComponent()
        func fixture(_ name: String) throws -> MissionSnapshot {
            try JSONDecoder().decode(MissionSnapshot.self, from: Data(contentsOf: fixtureDirectory.appendingPathComponent(name)))
        }
        NativeLocalization.testLanguage = "zh"
        precondition(state.usage?.visibleWindows.count == 2 && state.usage?.canSchedule == true,
                     "V0.2 snapshots must continue decoding without new quota metadata")
        precondition(state.usage?.permitsImmediate(minimum:20) == true)
        let weekly = try fixture("native-pro-weekly.json")
        precondition(weekly.usage?.account?.subscription == "Pro")
        precondition(weekly.usage?.visibleWindows.count == 1 && weekly.usage?.visibleWindows.first?.minutes == 10080)
        precondition(weekly.usage?.visibleWindows.first?.title == "周额度" && weekly.usage?.canSchedule == true)
        precondition(weekly.usage?.missingWindowNote == "未提供五小时窗口")
        precondition(weekly.usage?.scheduleWindow?.minutes == 10080)
        var weeklyUsage = weekly.usage!
        precondition(weeklyUsage.permitsImmediate(minimum:20))
        weeklyUsage.quota_windows?[0].remaining = 1
        precondition(weeklyUsage.permitsImmediate(minimum:20), "Weekly windows remain usable above zero")
        weeklyUsage.quota_windows?[0].remaining = 0
        precondition(!weeklyUsage.permitsImmediate(minimum:20))
        let custom = try fixture("native-custom-windows.json")
        precondition(custom.usage?.visibleWindows.map { $0.title } == ["15分钟额度", "1天额度"])
        precondition(custom.usage?.scheduleWindow?.minutes == 15)
        var customUsage = custom.usage!
        precondition(customUsage.permitsImmediate(minimum:20))
        customUsage.quota_windows?[0].remaining = 19
        precondition(!customUsage.permitsImmediate(minimum:20))
        precondition(customUsage.permitsImmediate(minimum:15), "Use the configured recovery threshold")
        let service = try fixture("native-service-only.json")
        precondition(service.usage?.visibleWindows.isEmpty == true && service.usage?.canSchedule == false)
        precondition(service.usage?.scheduleWindow == nil)
        precondition(service.usage?.availabilityNote == "服务已允许使用，未提供固定额度窗口")
        var serviceUsage = service.usage!
        precondition(serviceUsage.permitsImmediate(minimum:20))
        serviceUsage.service_allowed = false
        precondition(!serviceUsage.permitsImmediate(minimum:20))
        serviceUsage.service_allowed = true
        serviceUsage.blocked = true
        precondition(!serviceUsage.permitsImmediate(minimum:20))
        let unknown = try fixture("native-quota-unknown.json")
        precondition(unknown.usage?.account?.subscription == "future-plan")
        precondition(unknown.usage?.visibleWindows.isEmpty == true && unknown.usage?.canSchedule == false)
        precondition(unknown.usage?.scheduleWindow == nil)
        precondition(unknown.usage?.availabilityNote == "额度信息不完整，自动发送暂不可用")
        precondition(!unknown.healthy && !unknown.control_enabled)
        precondition(unknown.usage?.permitsImmediate(minimum:20) == false)
        var object = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        var usage = object["usage"] as! [String: Any]
        usage["quota_windows"] = []
        object["usage"] = usage
        let explicitlyEmpty = try JSONDecoder().decode(MissionSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
        precondition(explicitlyEmpty.usage?.visibleWindows.isEmpty == true && explicitlyEmpty.usage?.canSchedule == false,
                     "Explicit new empty windows must not resurrect cached V0.2 meters")
        NativeLocalization.testLanguage = "en"
        precondition(custom.usage?.visibleWindows.map { $0.title } == ["15-minute quota", "1-day quota"])
        precondition(weekly.usage?.visibleWindows.first?.title == "Weekly quota")
        precondition(service.usage?.availabilityNote == "The service allows usage; no fixed quota window was provided.")
        precondition(state.codexTasks.allSatisfy { $0.isCodex }, "Only Codex tasks belong in the task UI")
        var directoryOnly=state.tasks[2];directoryOnly.category="chatgpt";directoryOnly.key="chatgpt:cloud:fixture-hidden"
        var mixed=state;mixed.tasks.append(directoryOnly)
        precondition(mixed.codexTasks.count == state.codexTasks.count,"An unsupported product directory item must stay hidden")
        var localWithoutHost=state.tasks[1];localWithoutHost.host_id=nil
        precondition(localWithoutHost.isCodex,"A legacy local key must not require a new host field")
        localWithoutHost.category=nil
        precondition(localWithoutHost.isCodex,"A local Codex key identifies older snapshots without category")
        var remote=localWithoutHost;remote.category="codex";remote.host_id="remote-host"
        precondition(!remote.isCodex,"An explicit remote host cannot be displayed as local")
        remote.host_id=nil;remote.key="codex:remote-host:fixture-hidden"
        precondition(!remote.isCodex,"A missing host field cannot hide the remote host in a namespaced key")
        remote.host_id="local"
        precondition(!remote.isCodex,"Conflicting local metadata must not override a remote key")
        var legacyBare=state.tasks[1];legacyBare.host_id=nil;legacyBare.key="legacy-local-id";legacyBare.category="codex"
        precondition(legacyBare.isCodex && legacyBare.sourceTitle == L("Codex · 本机"))
        precondition(MissionAccent.allCases.map { $0.rawValue } == ["green","blue","purple","yellow"])
        precondition(MissionAccent.yellow.lightTextHex != "FFFFFF", "Egg-yellow controls need dark foreground text")
        var ruleText=MissionRuleFields.defaults.mapValues(String.init)
        precondition(MissionRuleFields.validation(ruleText).values == MissionRuleFields.defaults)
        ruleText["pause_remaining"]="20";ruleText["resume_remaining"]="24"
        precondition(MissionRuleFields.validation(ruleText).values == nil,"Recovery needs hysteresis of at least five points")
        ruleText["resume_remaining"]="25";ruleText["near_limit_poll_seconds"]="31"
        precondition(MissionRuleFields.validation(ruleText).values == nil,"Near-limit checks cannot be slower than normal checks")
        ruleText["near_limit_poll_seconds"]="10";ruleText["poll_seconds"]="1.5"
        precondition(MissionRuleFields.validation(ruleText).values == nil,"Rules accept integers, not silently rounded decimals")
        ruleText=MissionRuleFields.defaults.mapValues(String.init);ruleText["ui_poll_seconds"]="31"
        precondition(MissionRuleFields.validation(ruleText).values == nil)
        let rulesRequest=MissionCommands.rules(MissionRuleFields.defaults,revision:7)
        precondition(rulesRequest["rules_revision"] as? Int == 7 && rulesRequest["action"] as? String == "set_rules")
        precondition(rulesRequest["revision"] == nil,"Rules revision is independent of task/global control revision")
        let confirmedRules=MissionRules(revision:8,values:MissionRuleFields.defaults,bounds:nil)
        precondition(confirmedRules.confirms(MissionRuleFields.defaults,after:7))
        precondition(!confirmedRules.confirms(MissionRuleFields.defaults,after:8),"A 200 response with the old revision cannot clear a draft")
        precondition(!confirmedRules.confirms(MissionRuleFields.defaults,after:9),"An older receipt cannot clear a draft")
        var changedRuleValues=MissionRuleFields.defaults;changedRuleValues["ui_poll_seconds"]=9
        precondition(!confirmedRules.confirms(changedRuleValues,after:7),"A receipt for different values must retain the submitted draft")
        var extraRuleValues=MissionRuleFields.defaults;extraRuleValues["unsupported"]=1
        precondition(!confirmedRules.confirms(extraRuleValues,after:7),"Only an exact rules receipt confirms the request")
        for event in ["poll","sort","theme","locale"] {
            precondition(!MissionPromptSynchronization.shouldApply(current:"正在输入中文",incoming:"旧指令",editing:false,marked:true,hasDraft:false),"\(event) must preserve marked text")
            precondition(!MissionPromptSynchronization.shouldApply(current:"正在输入中文",incoming:"旧指令",editing:true,marked:false,hasDraft:false),"\(event) must preserve an active caret")
            precondition(!MissionPromptSynchronization.shouldApply(current:"本地草稿",incoming:"旧指令",editing:false,marked:false,hasDraft:true),"\(event) must preserve an unsaved draft")
        }
        precondition(MissionPromptSynchronization.shouldApply(current:"旧指令",incoming:"已确认的服务端指令",editing:false,marked:false,hasDraft:false))
        precondition(MissionPromptSynchronization.selection(NSRange(location:99,length:4),utf16Length:2) == NSRange(location:2,length:0))
        precondition(MissionResetCredits(available_count:nil,credits:nil,supported:false).displayCount == L("未提供"))
        precondition(MissionResetCredits(available_count:0,credits:[],supported:true).displayCount == "0")
        object["rules"]=["revision":4,"values":MissionRuleFields.defaults,"bounds":["ui_poll_seconds":["min":2,"max":30]],"constraints":["early_balance_restoration_min_drop_percent":20]] as [String:Any]
        usage["reset_credits"]=["supported":true,"available_count":2,"credits":[["id":"fixture-credit","title":"Fixture reset credit","status":"available","expiresAt":1793000000,"description":"Read-only service metadata"]]] as [String:Any]
        object["usage"]=usage
        let modern=try JSONDecoder().decode(MissionSnapshot.self,from:JSONSerialization.data(withJSONObject:object))
        precondition(modern.rules?.revision == 4 && modern.rules?.values["ui_poll_seconds"] == 5)
        precondition(modern.usage?.reset_credits?.available_count == 2 && modern.usage?.reset_credits?.credits?.first?.expiresAt == 1793000000)
        let restored=MissionEventDetail(reason:nil,source:nil,automatic_control_allowed:nil,recovery_reason:"balance_restored")
        precondition(restored.recoveryNote?.contains("unknown") == true && restored.recoveryNote?.contains("official") == false,"A balance increase is not proof of an official campaign reset")
        print("Native V0.3.0 rules / Codex filtering / theme / IME synchronization checks passed")
        print("Native snapshot / status / control contract checks passed")
    }
}
