import Foundation

@main enum NativeContractTests {
    static func main() throws {
        NativeLocalization.testLanguage = "zh"
        let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let state = try JSONDecoder().decode(MissionSnapshot.self, from: data)
        if CommandLine.arguments.contains("--decode-only") { print("Native decoder accepted live snapshot: \(state.tasks.count) chats, \(state.events.count) events"); return }
        let taskObject = ((try JSONSerialization.jsonObject(with:data) as! [String:Any])["tasks"] as! [[String:Any]])[1]
        func decodedConnectionTask(_ value: Any?, revision: Any? = nil) throws -> MissionChat {
            var object=taskObject
            object.removeValue(forKey:"connection_error")
            if let value { object["connection_error"]=value }
            if let revision { object["revision"]=revision }
            return try JSONDecoder().decode(MissionChat.self,from:JSONSerialization.data(withJSONObject:object))
        }
        for value: Any? in [nil,NSNull()] {
            let task=try decodedConnectionTask(value)
            precondition(task.connection_error == nil && !task.attention && task.status == "等待指令")
        }
        let stringError=try decodedConnectionTask("Connection temporarily unavailable")
        precondition(stringError.connection_error == "Connection temporarily unavailable" && stringError.attention && stringError.status == "连接待恢复")
        let objectError=try decodedConnectionTask(["type":"ConnectionError","detail":"Connection temporarily unavailable"])
        precondition(objectError.connection_error == stringError.connection_error && objectError.attention && objectError.status == "连接待恢复")
        let typeOnlyError=try decodedConnectionTask(["type":"ConnectionError"])
        precondition(typeOnlyError.connection_error == "ConnectionError" && typeOnlyError.attention)
        let emptyError=try decodedConnectionTask([String:String]())
        precondition(emptyError.connection_error == "连接待恢复" && emptyError.attention,"An empty legacy failure object must not clear its error state")
        for invalid: Any in [42,["detail":42],["type":true]] {
            do { _=try decodedConnectionTask(invalid);preconditionFailure("Invalid connection-error types must still fail decoding") }
            catch is DecodingError {} // Only the known string/object compatibility is allowed.
        }
        do { _=try decodedConnectionTask(["type":"ConnectionError","detail":"offline"],revision:"invalid");preconditionFailure("Other fields must remain strict") }
        catch is DecodingError {}
        var termination = MissionTerminationState()
        precondition(termination.phase == .running && !termination.complete())
        precondition(termination.request() && termination.phase == .waiting)
        precondition(!termination.request() && termination.phase == .waiting,"Repeated Quit must wait for the original cleanup")
        precondition(termination.complete() && termination.phase == .ready)
        precondition(!termination.complete() && !termination.request(),"Cleanup and termination reply must each occur once")
        var idle = state.tasks[1]
        precondition(idle.canExecute && !state.tasks[0].canExecute && !state.tasks[2].canExecute)
        precondition(idle.status == "等待指令")
        var unopened = idle
        unopened.runtime?.type = "notLoaded"
        precondition(unopened.status == "未打开" && !unopened.attention)
        unopened.connection_error = "read failed"
        precondition(unopened.status == "连接待恢复" && unopened.attention,
                     "A real error must not be hidden by unloaded metadata")
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
        precondition(service.usage?.availabilityNote == "服务可用，未提供固定窗口。")
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
        precondition(unknown.usage?.availabilityNote == "额度待核验，暂不发送。")
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
        precondition(service.usage?.availabilityNote == "Service available; no fixed quota window.")
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
        let quotaEvents=try fixture("native-quota-restored.json")
        let globalEvents=quotaEvents.events.filter(\.isQuotaRestored)
        precondition(globalEvents.count == 4 && globalEvents.allSatisfy { $0.isGlobal && $0.thread_id == nil && $0.scopeTitle == "Global quota event" })
        precondition(globalEvents.map(\.label) == ["User reset (inferred)","Scheduled reset (inferred)","Extra reset (inferred)","Quota restored"])
        precondition(globalEvents[0].restorationSummary == ["5-hour quota 2.0% → 100.0%"])
        precondition(globalEvents[0].restorationLines.contains("Reset credits: 2 → 1"))
        precondition(globalEvents[0].restorationLines.contains("Inferred from credit changes"))
        precondition(globalEvents[0].restorationLines.contains { $0.contains("2.0% → 100.0%") })
        precondition(globalEvents[0].restorationLines.contains { $0.hasPrefix("Reset time: ") && !$0.contains("Unavailable") })
        precondition(globalEvents[3].restorationLines.contains("Reset-credit counts unavailable."))
        precondition(globalEvents.allSatisfy { $0.restorationLines.contains("Cause inferred from quota changes; not confirmed by the service.") })
        precondition(quotaEvents.events.last?.scopeTitle == "整理示例发布清单" && quotaEvents.events.last?.isGlobal == false && quotaEvents.events.last?.restorationLines.isEmpty == true)
        precondition(MissionQuotaRestorationText.percent(nil) == "Unavailable" && MissionQuotaRestorationText.percent(0) == "0.0%")
        precondition(MissionQuotaRestorationText.count(nil) == "Unavailable" && MissionQuotaRestorationText.count(0) == "0")
        precondition(MissionQuotaRestorationText.count(-1) == "Unavailable" && MissionQuotaRestorationText.count(0.5) == "Unavailable")
        precondition(MissionQuotaRestorationText.category("future_category") == "Quota restored")
        func decodeEvent(_ object:[String:Any]) throws -> MissionEvent {
            try JSONDecoder().decode(MissionEvent.self,from:JSONSerialization.data(withJSONObject:object))
        }
        let ghost=try decodeEvent(["id":900,"created":1793156400,"state":"quota_restored","thread_id":NSNull(),"name":"ghost task must stay hidden","detail":["category":"future_category","windows":[["minutes":300,"previous_reset":NSNull(),"reset":NSNull()]],"reset_credits":["previous_available_count":NSNull(),"available_count":0]]])
        precondition(ghost.isGlobal && ghost.scopeTitle == "Global quota event" && ghost.label == "Quota restored")
        precondition(ghost.restorationLines.contains("Reset credits: Unavailable → 0") && !ghost.restorationLines.contains { $0.contains("ghost task") })
        precondition(ghost.restorationLines.contains("Reset time: Unavailable → Unavailable"))
        let globalRules=try decodeEvent(["id":901,"created":1793156400,"state":"rules_updated","thread_id":NSNull(),"name":"ghost task must stay hidden"])
        precondition(globalRules.scopeTitle == "Global control")
        precondition(state.events.first?.scopeTitle == state.events.first?.name,"Older snapshots without thread metadata retain task titles")
        precondition(MissionActivityFilter.all.title == "All records" && MissionActivityFilter.user.title == "User actions" && MissionActivityFilter.automatic.title == "Automated processes")
        let cachedIDs=quotaEvents.events.map(\.id)
        precondition(MissionActivityFilter.all.apply(to:quotaEvents.events).map(\.id) == cachedIDs)
        precondition(MissionActivityFilter.user.apply(to:quotaEvents.events).map(\.id) == [104])
        precondition(MissionActivityFilter.automatic.apply(to:quotaEvents.events).map(\.id) == [103,102,101,100])
        let futureOrigin=try decodeEvent(["id":902,"created":1793156400,"state":"quota_restored","origin":"future_origin","detail":["category":"user_reset","origin":"user"]])
        let nullOrigin=try decodeEvent(["id":903,"created":1793156400,"state":"running","origin":NSNull()])
        let invalidOrigin=try decodeEvent(["id":904,"created":1793156400,"state":"running","origin":true])
        let legacyEvents=[globalRules,futureOrigin,nullOrigin,invalidOrigin]
        precondition(legacyEvents.allSatisfy { $0.origin == .automatic },"Only API event.origin determines the filter bucket; legacy or unknown values are automatic")
        precondition(MissionActivityFilter.user.apply(to:legacyEvents).isEmpty && MissionActivityFilter.automatic.apply(to:legacyEvents).count == 4)
        let extendedHistory=Array(repeating:globalRules,count:200)+[quotaEvents.events[0]]
        precondition(MissionActivityFilter.all.apply(to:extendedHistory).count == 200 && MissionActivityFilter.user.apply(to:extendedHistory).isEmpty,"Filter after selecting the latest 200 cached records")
        precondition(quotaEvents.events.map(\.id) == cachedIDs && extendedHistory.count == 201,"Filtering retains the complete immutable cache")
        precondition(MissionActivityFilter.all.apply(to:[]).isEmpty && MissionActivityFilter.user.apply(to:[]).isEmpty && MissionActivityFilter.automatic.apply(to:[]).isEmpty)
        NativeLocalization.testLanguage="zh"
        precondition(MissionActivityFilter.all.title == "全部记录" && MissionActivityFilter.user.title == "用户操作" && MissionActivityFilter.automatic.title == "自动进程")
        precondition(globalEvents.map(\.label) == ["用户恢复（推断）","周期重置（推断）","额外重置（推断）","额度恢复"])
        precondition(globalEvents[0].scopeTitle == "全局额度事件" && globalEvents[0].restorationLines.contains("依据权益变化判定"))
        precondition(L("任务管家") == "TOKEN榨汁机" && L("任务控制") == "来一杯")
        precondition(L("启用自动控制") == "开始榨汁" && L("恢复自动控制") == "开始榨汁")
        precondition(L("暂停自动控制") == "暂停榨汁" && L("自动控制") == "榨汁状态")
        precondition(L(L("关闭窗口后，任务管家继续在菜单栏运行。")) == "关闭窗口后仍在后台运行。")
        precondition(NativeLocalization.notificationTitle("额度管家：额度已恢复") == "额度已恢复")
        NativeLocalization.testLanguage="en"
        precondition(L("任务管家") == "TokenMax" && L("来一杯") == "Juice Bar")
        precondition(L("开始榨汁") == "Start Juicing" && L("暂停榨汁") == "Pause Juicing")
        precondition(L("%@：榨汁状态","Test task") == "Test task: juicing")
        precondition(NativeLocalization.notificationTitle("TOKEN榨汁机：已暂停任务") == "Tasks paused")
        precondition(NativeLocalization.notificationTitle("额度管家：额度已恢复") == "Quota restored")
        precondition(!NativeLocalization.english.values.contains { $0.contains("Mission Manager") })
        var logo=state
        logo.control_paused=false;logo.running=true;logo.healthy=true;logo.control_enabled=true;logo.stale=false
        logo.control_available=true;logo.usage?.stale=false;logo.usage?.quota_state="metered"
        logo.quota_phase="healthy";logo.service_error=nil;logo.desktop_connection_error=nil
        logo.compatibility=nil;logo.usage?.blocked=false
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .working)
        logo.tasks[0].runtime?.type="systemError"
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .working,"Individual task errors must not alter global branding")
        precondition(MissionLogoControl.state(connected:true,paused:true,snapshot:logo) == .idle)
        precondition(MissionLogoControl.state(connected:false,paused:false,snapshot:logo) == .disconnected)
        logo.quota_phase="low";logo.healthy=false;logo.control_enabled=false
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .waiting,"Confirmed low quota is a waiting state, even when controls cannot execute")
        logo.stale=true
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .disconnected,"Stale low readings must not imply a confirmed quota wait")
        logo.stale=false;logo.service_error="quota_read_failed"
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .error)
        precondition(MissionLogoControl.state(connected:true,paused:true,snapshot:logo) == .idle,"Stopped control always shows a static idle logo")
        logo.service_error=nil;logo.quota_phase=nil;logo.healthy=true;logo.control_enabled=true
        logo.usage?.windows.five_hour?.remaining=logo.policy.pause
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .waiting,"Older snapshots derive the waiting visual from known quota")
        logo.running=false
        precondition(MissionLogoControl.state(connected:true,paused:false,snapshot:logo) == .idle)
        print("Native connection-error missing / null / string / legacy-object compatibility checks passed")
        print("Native TokenMax copy / recovery summary / five-state logo checks passed")
        print("Native activity origin / three filters / immutable latest-200 cache checks passed")
        print("Native V0.3.0 rules / Codex filtering / theme / IME synchronization checks passed")
        print("Native snapshot / status / control contract checks passed")
    }
}
