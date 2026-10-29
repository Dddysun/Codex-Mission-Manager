import AppKit
import Carbon
import SwiftUI
import ServiceManagement
import UserNotifications
import IOKit.pwr_mgt
import Darwin

// AppKit may enter a menu-tracking or modal run loop while a quit request is
// pending. Completion must not depend on a default-mode Timer firing.
func missionOnMainCommonModes(_ body: @escaping () -> Void) {
    CFRunLoopPerformBlock(CFRunLoopGetMain(), RunLoop.Mode.common.rawValue as CFString, body)
    CFRunLoopWakeUp(CFRunLoopGetMain())
}

final class MissionModel: ObservableObject {
    @Published var language = NativeLocalization.testLanguage ?? UserDefaults.standard.string(forKey: "language") ?? (Locale.preferredLanguages.first?.hasPrefix("zh") == true ? "zh" : "en") {
        didSet { if NativeLocalization.testLanguage == nil { UserDefaults.standard.set(language, forKey: "language"); refresh() }; onPresentationChanged?() }
    }
    @Published var theme = NativeLocalization.testLanguage == nil ? (UserDefaults.standard.string(forKey: "theme") ?? "system") : "system" {
        didSet { if NativeLocalization.testLanguage == nil { UserDefaults.standard.set(theme, forKey: "theme") }; onPresentationChanged?() }
    }
    @Published var accent = NativeLocalization.testLanguage == nil ? (UserDefaults.standard.string(forKey:"accent") ?? "green") : "green" {
        didSet { if NativeLocalization.testLanguage == nil { UserDefaults.standard.set(accent,forKey:"accent") }; onPresentationChanged?() }
    }
    var accentChoice: MissionAccent { MissionAccent(rawValue:accent) ?? .green }
    var tint: Color { MissionPalette.accent(accentChoice) }
    var sidebarInk: Color { MissionPalette.ink(accentChoice) }
    var selectedNavigation: Color { MissionPalette.selected(accentChoice) }
    var accentForeground: Color { MissionPalette.foreground(accentChoice) }
    @Published var loginEnabled = false
    @Published var notificationsEnabled = false
    @Published var notificationDelivery = NativeLocalization.testLanguage == nil ? (UserDefaults.standard.object(forKey:"notificationDelivery") as? Bool ?? false) : false
    @Published var notificationsDenied = false
    @Published var helperEnabled = false
    @Published var closedLidEnabled = false
    var onPresentationChanged: (() -> Void)?
    var colorScheme: ColorScheme? { theme == "dark" ? .dark : theme == "light" ? .light : nil }
    @Published var backend = L("正在启动本机服务")
    @Published var client = L("尚未检查")
    @Published var power = L("尚未检查")
    @Published var awake = false
    @Published var login = L("尚未检查")
    @Published var notifications = L("尚未检查")
    @Published var helper = L("尚未检查")
    @Published var closedLid = L("未启用")
    @Published var checked = L("尚未检查")
    @Published var error = ""
    @Published var paused = true
    @Published var allowBattery = false
    @Published var waitingForLock = false
    var lockDeadline = Date.distantPast
    var baseURL: URL?
    var stateDirectory: URL?
    @Published var snapshot: MissionSnapshot?
    @Published var connectionError = ""
    @Published var connected = false
    @Published var busy = false
    @Published var notice = ""
    @Published var drafts: [String: MissionDraft] = [:]
    @Published var rulesDraft: [String:String] = [:]
    @Published var rulesDraftRevision: Int?
    @Published var rulesStatus = ""
    @Published var rulesSaving = false
    var refreshing = false
    var host: Process?
    var hostInput: Pipe?
    var hostOutput = Data()
    var observerTokens: [NSObjectProtocol] = []
    var timer: Timer?
    var assertion: IOPMAssertionID = 0
    var powerConnection: NSXPCConnection?
    let session = URLSession(configuration: .ephemeral)
    var notificationKeys = Set<String>()
    var firstNoticeRead = true
    private(set) var stopping = false
    private var stoppingHost: Process?
    private var stopReceipt: MissionStopReceipt?
    private var stopCallbacks: [(MissionStopReceipt) -> Void] = []

    var logoState: MissionLogoState {
        MissionLogoControl.state(connected:connected,paused:paused,snapshot:snapshot)
    }
    var signed: Bool { MissionIdentity.releaseSigned }
    var service: SMAppService { SMAppService.daemon(plistName: MissionIdentity.helperPlist) }
    var support: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/CodexMissionManager") }

    func start() {
        setAwake(UserDefaults.standard.object(forKey: "keepAwake") as? Bool ?? false)
        let center = DistributedNotificationCenter.default()
        observerTokens.append(center.addObserver(forName: .init("com.apple.screenIsLocked"), object: nil, queue: .main) { [weak self] _ in
            guard let self, self.waitingForLock, Date() < self.lockDeadline else { return }
            self.waitingForLock = false
            self.withHelper { peer in peer.enableClosedLid(onBattery: self.allowBattery) { value in
                DispatchQueue.main.async { self.closedLidEnabled = value["active"] as? Bool ?? false; self.closedLid = value["reason"] as? String ?? L("未确认") }
            } }
        })
        observerTokens.append(center.addObserver(forName: .init("com.apple.screenIsUnlocked"), object: nil, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.waitingForLock = false
            if self.powerConnection != nil { self.disableClosedLid() }
        })
        refresh()
        configureRefreshTimer(5)
        startHost()
    }

    func configureRefreshTimer(_ seconds: Double) {
        guard !stopping else { return }
        let interval=min(30,max(2,seconds.isFinite ? seconds : 5))
        if let timer, abs(timer.timeInterval-interval)<0.001 { return }
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.refresh()
            self?.heartbeat()
            self?.deliverNotices()
            Task { await self?.refreshControl() }
        }
    }

    func startHost() {
        guard !stopping, host == nil, let resources = Bundle.main.resourceURL else { return }
        let task = Process(), output = Pipe(), input = Pipe()
        task.executableURL = resources.appendingPathComponent("python/bin/python3")
        task.arguments = ["-B", "-I", resources.appendingPathComponent("backend/app_host.py").path]
        task.standardInput = input
        task.standardOutput = output
        do {
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            let log = support.appendingPathComponent("launcher.log")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
            let handle = try FileHandle(forWritingTo: log)
            try handle.seekToEnd()
            task.standardError = handle
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty { handle.readabilityHandler = nil; return }
                DispatchQueue.main.async { self?.receiveHost(data) }
            }
            task.terminationHandler = { [weak self] stopped in DispatchQueue.main.async {
                guard let self, self.host === stopped else { return }
                self.backend = L("后台已退出；已有记录保留")
                self.host = nil
                self.connected = false
            } }
            try task.run()
            host = task
            hostInput = input
        } catch { self.error = error.localizedDescription; backend = L("启动失败") }
    }

    func receiveHost(_ data: Data) {
        guard !stopping else { return }
        hostOutput.append(data)
        while let newline = hostOutput.firstIndex(of: 10) {
            let line = Data(hostOutput[..<newline])
            hostOutput.removeSubrange(...newline)
            guard let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                  let text = value["url"] as? String, let url = URL(string: text),
                  url.scheme == "http", url.host == "127.0.0.1", url.port != nil else { continue }
            baseURL = url
            stateDirectory = (value["state_dir"] as? String).map { URL(fileURLWithPath: $0) }
            backend = value["external"] as? Bool == true ? L("已连接原有任务管家，未启动重复执行器") : L("应用自带后台已启动")
            Task { await refreshControl() }
        }
    }

    // A private ephemeral cookie session authenticates the local JSON API.
    // No HTML is rendered and no WebKit runtime is used by the application.
    @MainActor func refreshControl() async {
        guard !stopping, let url = baseURL, !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            _ = try await session.data(from: url) // Compatibility session handshake with existing backends.
            let (data, response) = try await session.data(from: url.appendingPathComponent("api/state"))
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                throw NSError(domain: "Guardian", code: 1, userInfo: [NSLocalizedDescriptionKey: L("无法读取本机后台状态")])
            }
            let value = try JSONDecoder().decode(MissionSnapshot.self, from: data)
            await MainActor.run {
                guard !self.stopping else { return }
                self.snapshot = value; self.paused = value.control_paused; self.connected = true; self.connectionError = ""
                self.configureRefreshTimer(value.rules?.values["ui_poll_seconds"].map(Double.init) ?? value.ui_poll_seconds ?? 5)
            }
        } catch { await MainActor.run { self.connected = false; self.connectionError = L("后台连接待恢复：") + error.localizedDescription } }
    }

    func perform(_ payload: [String: Any]) {
        guard !stopping, !busy, connected, let url = baseURL else { return }
        busy = true
        notice = ""
        Task {
            do {
                var request = URLRequest(url: url.appendingPathComponent("api/action"))
                request.httpMethod = "POST"
                request.timeoutInterval = 20
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("1", forHTTPHeaderField: "X-Guardian-UI")
                request.setValue(url.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")), forHTTPHeaderField: "Origin")
                request.httpBody = try JSONSerialization.data(withJSONObject: payload)
                let (reply, response) = try await session.data(for: request)
                let body = (try? JSONSerialization.jsonObject(with: reply)) as? [String: Any]
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw NSError(domain: "Guardian", code: 1, userInfo: [NSLocalizedDescriptionKey: body?["error"] as? String ?? L("操作结果待核对，请刷新后检查记录")])
                }
                await MainActor.run {
                    self.notice = (self.language == "en" ? body?["message_en"] as? String : nil) ?? body?["message"] as? String ?? L("操作已提交")
                    // Clear only a draft confirmed saved by this exact request.
                    if payload["action"] as? String == "set_plan", payload["enabled"] as? Bool == true,
                       let key = payload["key"] as? String, let prompt = payload["prompt"] as? String,
                       self.drafts[key]?.text == prompt { self.drafts.removeValue(forKey: key) }
                }
            } catch { await MainActor.run { self.notice = error.localizedDescription } }
            await self.refreshControl()
            await MainActor.run { self.busy = false }
        }
    }

    func setGlobalAutomatic(_ enabled: Bool) {
        guard let state = snapshot else { return }
        perform(["action":enabled ? "enable" : "pause", "revision":state.control_revision])
    }
    func pauseAllTasks() {
        guard let state = snapshot else { return }
        perform(["action":"pause_all", "revision":state.control_revision])
    }
    func toggleAutomatic() {
        guard let state = snapshot else { return }
        perform(["action": !state.running ? "start" : state.control_paused ? "enable" : "pause", "revision": state.control_revision])
    }
    func setAutomatic(_ chat: MissionChat, enabled: Bool) {
        guard chat.controllable else { return }
        perform(MissionCommands.automatic(chat, enabled: enabled))
    }
    func editPrompt(_ chat: MissionChat, text: String) {
        let revision = drafts[chat.key]?.revision ?? chat.plan?.revision ?? 0
        // Never truncate provisional IME text. Length is checked on submission.
        drafts[chat.key] = MissionDraft(text: text, revision: revision)
    }
    func savePlan(_ chat: MissionChat, enabled: Bool) {
        guard chat.controllable else { return }
        guard !enabled || (drafts[chat.key]?.text ?? chat.plan?.prompt ?? "").count<=8000 else { notice=L("指令最多允许 8000 个字符；草稿已保留。");return }
        perform(MissionCommands.plan(chat, draft: drafts[chat.key], enabled: enabled))
    }
    func executeNow(_ chat: MissionChat) {
        guard chat.canExecute else { return }
        guard (drafts[chat.key]?.text ?? chat.plan?.prompt ?? "").count<=8000 else { notice=L("指令最多允许 8000 个字符；草稿已保留。");return }
        perform(MissionCommands.immediate(chat, draft: drafts[chat.key]))
    }

    func editRule(_ key:String,text:String) {
        guard let current=snapshot?.rules else { return }
        if rulesDraftRevision == nil {
            rulesDraftRevision=current.revision
            rulesDraft=current.values.mapValues(String.init)
        }
        rulesDraft[key]=text;rulesStatus=""
    }
    func discardRulesDraft() { rulesDraft=[:];rulesDraftRevision=nil;rulesStatus="" }
    @MainActor func saveRules() async {
        guard !stopping, !rulesSaving, !busy, connected, let state=snapshot?.rules, let url=baseURL else { return }
        let text=rulesDraftRevision == nil ? state.values.mapValues(String.init) : rulesDraft
        let validated=MissionRuleFields.validation(text,remoteBounds:state.bounds)
        guard let values=validated.values else {rulesStatus=validated.error ?? L("规则未通过校验。");return}
        let revision=rulesDraftRevision ?? state.revision
        rulesSaving=true;rulesStatus=L("正在保存规则…")
        defer { rulesSaving=false }
        do {
            var request=URLRequest(url:url.appendingPathComponent("api/action"))
            request.httpMethod="POST";request.timeoutInterval=20
            request.setValue("application/json",forHTTPHeaderField:"Content-Type")
            request.setValue("1",forHTTPHeaderField:"X-Guardian-UI")
            request.setValue(url.absoluteString.trimmingCharacters(in:CharacterSet(charactersIn:"/")),forHTTPHeaderField:"Origin")
            request.httpBody=try JSONSerialization.data(withJSONObject:MissionCommands.rules(values,revision:revision))
            let (data,response)=try await session.data(for:request)
            let body=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                throw NSError(domain:"Rules",code:1,userInfo:[NSLocalizedDescriptionKey:body?["error"] as? String ?? L("规则保存失败；草稿已保留。")])
            }
            guard let metadata=body?["rules"], JSONSerialization.isValidJSONObject(metadata),
               let encoded=try? JSONSerialization.data(withJSONObject:metadata),
               let confirmed=try? JSONDecoder().decode(MissionRules.self,from:encoded),
               confirmed.confirms(values,after:revision) else {
                throw NSError(domain:"Rules",code:2,userInfo:[NSLocalizedDescriptionKey:L("操作结果待核对，请刷新后检查记录")])
            }
            if confirmed.revision >= (snapshot?.rules?.revision ?? 0) {
                snapshot?.rules=confirmed
                configureRefreshTimer(Double(confirmed.values["ui_poll_seconds"] ?? 5))
            }
            // Preserve any edits made while the request was in flight.
            if rulesDraftRevision == revision && rulesDraft == text { rulesDraft=[:];rulesDraftRevision=nil }
            rulesStatus=L("规则已保存。")
            await refreshControl()
        } catch { rulesStatus=error.localizedDescription+" · "+L("草稿已保留，请核对后重试。") }
    }

    func setAwake(_ value: Bool) {
        if value && assertion == 0 {
            let result = IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep as CFString,
                IOPMAssertionLevel(kIOPMAssertionLevelOn), L("任务管家：保持后台工作，允许屏幕熄灭") as CFString, &assertion)
            awake = result == kIOReturnSuccess
        } else if !value && assertion != 0 { IOPMAssertionRelease(assertion); assertion = 0; awake = false }
        UserDefaults.standard.set(awake, forKey: "keepAwake")
    }

    func registration(_ value: SMAppService.Status) -> String {
        switch value {
        case .enabled: return L("系统已允许")
        case .requiresApproval: return L("等待系统批准／已被停用")
        case .notRegistered: return L("尚未登记")
        case .notFound: return L("尚未注册或服务暂不可用")
        @unknown default: return L("未知，待确认")
        }
    }

    func refresh() {
        guard !stopping else { return }
        loginEnabled = SMAppService.mainApp.status == .enabled
        helperEnabled = signed && service.status == .enabled
        login = registration(SMAppService.mainApp.status)
        helper = signed ? registration(service.status) : L("本机预览包未配置 Developer ID，管理员服务不可启用")
        let p = HardwareState.power()
        power = L("%@ · 电量 %@ · %@", String(describing: p.ac ? "外接电源" : "电池／电源待确认"), String(describing: p.battery.map { "\($0)%" } ?? "未知"), String(describing: HardwareState.lidClosed.map { $0 ? "已合盖" : "开盖" } ?? "机盖状态待确认"))
        if let compatibility = snapshot?.compatibility {
            if compatibility.status == "client_missing" { client = L("未检测到 Codex 客户端，请安装并登录。") }
            else if compatibility.supported {
                client = L("客户端 %@ · 兼容配置已匹配", compatibility.build ?? "—") + (connected ? " · " + L("已连接") : " · " + L("连接待恢复"))
            } else { client = L("客户端 %@ 尚未支持，请检查任务管家更新。", compatibility.build ?? "—") }
        } else { client = L("正在检查客户端兼容性") }
        checked = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        if waitingForLock && Date() >= lockDeadline { waitingForLock = false; closedLid = L("锁屏等待已超时，未启用合盖保持") }
        UNUserNotificationCenter.current().getNotificationSettings { value in DispatchQueue.main.async {
            self.notificationsDenied = value.authorizationStatus == .denied
            self.notificationsEnabled = [.authorized, .provisional].contains(value.authorizationStatus) && self.notificationDelivery
            switch value.authorizationStatus {
            case .authorized, .provisional: self.notifications = L("已允许")
            case .denied: self.notifications = L("已拒绝；任务仍可执行")
            case .notDetermined: self.notifications = L("尚未申请")
            default: self.notifications = L("状态待确认")
            }
        } }
    }

    func setNotifications(_ enabled: Bool) {
        notificationDelivery = enabled
        UserDefaults.standard.set(enabled, forKey: "notificationDelivery")
        if enabled && notificationsDenied { openSettings("notifications") }
        else if enabled { requestNotifications() }
        refresh()
    }
    func requestNotifications() {
        error = ""
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, error in
            DispatchQueue.main.async { self.error = error?.localizedDescription ?? ""; self.refresh() }
        }
    }
    func registerLogin() {
        error = ""
        do { try SMAppService.mainApp.register(); refresh() }
        catch { self.error = error.localizedDescription }
    }
    func unregisterLogin() {
        error = ""
        do { try SMAppService.mainApp.unregister(); refresh() }
        catch { self.error = error.localizedDescription }
    }
    func registerPower() {
        error = ""
        guard signed else { error = L("需要发行签名和系统管理员批准；此预览包不会安装 root 服务"); return }
        do { try service.register(); refresh(); SMAppService.openSystemSettingsLoginItems() }
        catch { self.error = error.localizedDescription }
    }
    func removePower() {
        guard signed else { return }
        withHelper { peer in peer.disable { value in DispatchQueue.main.async {
            guard value["active"] as? Bool != true else { self.error = L("电源设置尚未恢复，请稍后重试。"); return }
            do { try self.service.unregister(); self.powerConnection?.invalidate(); self.powerConnection = nil; self.refresh() }
            catch { self.error = error.localizedDescription }
        } } }
    }
    func withHelper(_ body: @escaping (PowerHelperProtocol) -> Void) {
        guard signed, service.status == .enabled else { error = L("管理员辅助服务未获准运行"); return }
        if powerConnection == nil {
            let connection = NSXPCConnection(machServiceName: MissionIdentity.helper, options: .privileged)
            connection.remoteObjectInterface = NSXPCInterface(with: PowerHelperProtocol.self)
            let requirement = "anchor apple generic and identifier \"\(MissionIdentity.helper)\" and certificate leaf[subject.OU] = \"\(MissionIdentity.team)\""
            connection.setCodeSigningRequirement(requirement)
            connection.invalidationHandler = { [weak self] in DispatchQueue.main.async { self?.powerConnection = nil } }
            connection.resume()
            powerConnection = connection
        }
        let proxy = powerConnection?.remoteObjectProxyWithErrorHandler { [weak self] error in
            DispatchQueue.main.async { self?.closedLid = L("服务连接失败：") + error.localizedDescription }
        } as? PowerHelperProtocol
        if let proxy { body(proxy) }
    }
    func prepareClosedLid() {
        guard signed, service.status == .enabled else { error = L("需先完成发行签名与管理员辅助服务授权"); return }
        waitingForLock = true
        lockDeadline = Date().addingTimeInterval(60)
        closedLid = L("等待锁屏：请按 Control–Command–Q；确认锁屏事件后才启用")
        // No simulated keyboard input, Accessibility access or private locking API.
    }
    func disableClosedLid() {
        waitingForLock = false
        withHelper { peer in peer.disable { value in DispatchQueue.main.async {
            self.closedLidEnabled = value["active"] as? Bool ?? false
            self.closedLid = value["reason"] as? String ?? L("待确认")
        } } }
    }
    func heartbeat() {
        guard powerConnection != nil else { return }
        withHelper { peer in peer.heartbeat { value in DispatchQueue.main.async {
            self.closedLidEnabled = value["active"] as? Bool ?? false
            self.closedLid = value["reason"] as? String ?? L("待确认")
        } } }
    }
    func deliverNotices() {
        guard let stateDirectory,
              let data = try? Data(contentsOf: stateDirectory.appendingPathComponent("native-notices.json")),
              let records = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return }
        for record in records {
            guard let key = record["key"] as? String else { continue }
            if notificationDelivery, notificationsEnabled, !notificationKeys.contains(key), !firstNoticeRead {
                let content = UNMutableNotificationContent()
                content.title = NativeLocalization.notificationTitle(record["title"] as? String ?? "TOKEN榨汁机")
                content.body = NativeLocalization.language == "en" ? ((record["body_en"] as? String) ?? L("打开TOKEN榨汁机查看详情。")) : L(record["body"] as? String ?? "")
                UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: key, content: content, trigger: nil))
            }
            notificationKeys.insert(key)
        }
        firstNoticeRead = false
    }
    func stop(grace: TimeInterval = 6, finalWait: TimeInterval = 2, completion: @escaping (MissionStopReceipt) -> Void) {
        if let stopReceipt { completion(stopReceipt); return }
        stopCallbacks.append(completion)
        guard !stopping else { return }
        stopping = true
        timer?.invalidate(); timer = nil
        waitingForLock = false
        for token in observerTokens { DistributedNotificationCenter.default().removeObserver(token) }
        observerTokens.removeAll()
        session.invalidateAndCancel()
        // Only use an existing helper connection. Quitting must never register a
        // service, request authorization, or wait indefinitely for an XPC reply.
        if let connection = powerConnection {
            powerConnection = nil
            let proxy = connection.remoteObjectProxyWithErrorHandler { _ in connection.invalidate() } as? PowerHelperProtocol
            proxy?.disable { _ in connection.invalidate() }
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2) { connection.invalidate() }
        }
        if assertion != 0 { IOPMAssertionRelease(assertion); assertion = 0 }
        let ownedHost = host
        stoppingHost = ownedHost
        let input = hostInput
        hostInput = nil
        // Even a five-byte write can block if an unhealthy child stops reading.
        // Keep it separate from both AppKit and the independent shutdown clock.
        if let input {
            DispatchQueue.global(qos: .utility).async {
                try? input.fileHandleForWriting.write(contentsOf: Data("stop\n".utf8))
                try? input.fileHandleForWriting.close()
            }
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var terminated = false, killed = false
            let end = ProcessInfo.processInfo.systemUptime + max(0, grace)
            while ownedHost?.isRunning == true && ProcessInfo.processInfo.systemUptime < end { Thread.sleep(forTimeInterval: 0.025) }
            if let ownedHost, ownedHost.isRunning {
                terminated = true
                ownedHost.terminate()
                let finalEnd = ProcessInfo.processInfo.systemUptime + max(0, finalWait)
                while ownedHost.isRunning && ProcessInfo.processInfo.systemUptime < finalEnd { Thread.sleep(forTimeInterval: 0.025) }
                if ownedHost.isRunning {
                    // This is the Process launched by this app, never a client
                    // process selected by name, catalog id, or a saved PID.
                    killed = Darwin.kill(ownedHost.processIdentifier, SIGKILL) == 0
                }
            }
            let receipt = MissionStopReceipt(hostExited: ownedHost?.isRunning != true,
                terminateRequested: terminated, forceKillRequested: killed, deadlineReached: terminated)
            missionOnMainCommonModes {
                guard let self, self.stopReceipt == nil else { return }
                self.stopReceipt = receipt
                let callbacks = self.stopCallbacks
                self.stopCallbacks.removeAll()
                callbacks.forEach { $0(receipt) }
            }
        }
    }
    func finalizeOwnedHostStop() {
        // The final AppKit deadline may win a scheduling race with the worker.
        // Reclaim only the same captured child before replying, without waiting.
        guard stopping, let stoppingHost, stoppingHost.isRunning else { return }
        _ = Darwin.kill(stoppingHost.processIdentifier, SIGKILL)
    }
    func openSettings(_ destination: String) {
        if destination == "login" { SMAppService.openSystemSettingsLoginItems(); return }
        let known = ["general": "x-apple.systempreferences:com.apple.preference.general", "battery": "x-apple.systempreferences:com.apple.preference.battery", "notifications": "x-apple.systempreferences:com.apple.preference.notifications", "privacy": "x-apple.systempreferences:com.apple.preference.security"]
        if let text = known[destination], let url = URL(string: text) { NSWorkspace.shared.open(url) }
    }
}

final class MissionApp: NSObject, NSApplicationDelegate {
    let model = MissionModel()
    var window: NSWindow!
    var settingsWindow: NSWindow?
    var statusItem: NSStatusItem!
    let popover = NSPopover()
    var termination = MissionTerminationState()
    var terminationReply: (Bool) -> Void = { NSApp.reply(toApplicationShouldTerminate: $0) }
    var shutdownGraceSeconds: TimeInterval = 6
    var shutdownFinalWaitSeconds: TimeInterval = 2
    var shutdownReplyDeadlineSeconds: TimeInterval = 8

    func applicationDidFinishLaunching(_ notification: Notification) {
        rebuildMainMenu()
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button=statusItem.button {
            let artwork=JuicerStatusHostingView(rootView:JuicerStatusIcon(model:model))
            artwork.frame=button.bounds
            artwork.autoresizingMask=[.width,.height]
            button.addSubview(artwork)
            button.setAccessibilityLabel(L("TOKEN榨汁机"))
        }
        statusItem.button?.toolTip = L("任务管家")
        statusItem.button?.target = self
        statusItem.button?.action = #selector(togglePanel)
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: MissionMenuPanel(model: model, openWindow: { [weak self] in self?.popover.performClose(nil); self?.showWindow() }, openSettings: { [weak self] in self?.popover.performClose(nil); self?.showSettings() }, quit: { [weak self] in self?.quit() }))
        popover.contentSize = NSSize(width: 400, height: 570)
        model.onPresentationChanged = { [weak self] in self?.applyPresentation() }
        applyPresentation()
        let content = MissionWindow(model: model, showSettings: { [weak self] in self?.showSettings() })
        window = NSWindow(contentViewController: NSHostingController(rootView: content))
        window.title = L("任务管家")
        window.setContentSize(NSSize(width: 1380, height: 900))
        window.minSize = NSSize(width: 1120, height: 680)
        window.isReleasedWhenClosed = false
        window.titlebarAppearsTransparent = true
        window.center()
        model.start()
        let loginLaunch = NSAppleEventManager.shared().currentAppleEvent?.paramDescriptor(forKeyword: AEKeyword(keyAELaunchedAsLogInItem)) != nil
        if !loginLaunch && !CommandLine.arguments.contains("--background") { showWindow() }
    }
    func rebuildMainMenu() {
        let menu = NSMenu(), appItem = NSMenuItem(title:L("任务管家"),action:nil,keyEquivalent:""), appMenu = NSMenu(title:L("任务管家"))
        menu.addItem(appItem); appItem.submenu = appMenu
        appMenu.addItem(withTitle:L("打开任务管家"),action:#selector(showWindow),keyEquivalent:"").target = self
        appMenu.addItem(withTitle:L("设置…"), action:#selector(showSettings), keyEquivalent:",").target = self
        appMenu.addItem(.separator())
        let quitItem = appMenu.addItem(withTitle:L("退出任务管家"), action:#selector(quit), keyEquivalent:"q")
        quitItem.target = self; quitItem.keyEquivalentModifierMask = [.command]
        let editItem = NSMenuItem(); menu.addItem(editItem)
        let edit = NSMenu(title:L("编辑")); editItem.submenu = edit
        for (title, selector, key) in [(L("撤销"), "undo:", "z"), (L("剪切"), "cut:", "x"), (L("复制"), "copy:", "c"), (L("粘贴"), "paste:", "v"), (L("全选"), "selectAll:", "a")] { edit.addItem(withTitle:title, action:Selector(selector), keyEquivalent:key) }
        NSApp.mainMenu = menu
    }
    func applyPresentation() {
        NSApp.appearance = model.theme == "system" ? nil : NSAppearance(named:model.theme == "dark" ? .darkAqua : .aqua)
        rebuildMainMenu()
        window?.title = L("任务管家")
        settingsWindow?.title = L("设置")
        statusItem?.button?.toolTip = L("任务管家")
        statusItem?.button?.setAccessibilityLabel(L("TOKEN榨汁机"))
    }
    @objc func togglePanel() {
        guard termination.phase == .running else { return }
        guard let button = statusItem.button else { return }
        if popover.isShown { popover.performClose(nil) }
        else { popover.show(relativeTo:button.bounds, of:button, preferredEdge:.minY); Task { await model.refreshControl() } }
    }
    @objc func showWindow() { guard termination.phase == .running else { return }; NSApp.setActivationPolicy(.regular); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func showSettings() {
        guard termination.phase == .running else { return }
        if settingsWindow == nil {
            let host = NSHostingController(rootView: MissionSettings(model: model))
            let value = NSWindow(contentViewController: host)
            value.title = L("设置")
            value.setContentSize(NSSize(width: 800, height: 780)); value.isReleasedWhenClosed = false; value.center()
            settingsWindow = value
        }
        model.refresh(); settingsWindow?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc func toggleControl() { model.toggleAutomatic() }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if termination.phase == .ready { return .terminateNow }
        guard termination.request() else { return .terminateLater }
        popover.performClose(nil)
        model.stop(grace:shutdownGraceSeconds,finalWait:shutdownFinalWaitSeconds) { [weak self] _ in self?.finishTermination() }
        // Independent fallback, including a blocked stop-pipe writer. Common
        // run-loop modes also allow completion while a menu/modal loop is open.
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + shutdownReplyDeadlineSeconds) { [weak self] in
            missionOnMainCommonModes { self?.finishTermination() }
        }
        return .terminateLater
    }
    func finishTermination() {
        guard termination.complete() else { return }
        model.finalizeOwnedHostStop()
        terminationReply(true)
    }
}

enum MissionLifecycleChecks {
    static func wait(until ready: () -> Bool, timeout: TimeInterval = 3, mode: RunLoop.Mode = .default) -> Bool {
        let end = ProcessInfo.processInfo.systemUptime + timeout
        while !ready() && ProcessInfo.processInfo.systemUptime < end {
            _ = RunLoop.main.run(mode:mode,before:Date().addingTimeInterval(0.01))
            Thread.sleep(forTimeInterval:0.001)
        }
        return ready()
    }
    static func fixture(_ script: String) throws -> (Process, Pipe) {
        let process=Process(), input=Pipe(), ready=Pipe()
        process.executableURL=URL(fileURLWithPath:"/bin/sh")
        process.arguments=["-c",script]
        process.standardInput=input;process.standardOutput=ready;process.standardError=FileHandle.nullDevice
        try process.run()
        guard ready.fileHandleForReading.readData(ofLength:6) == Data("ready\n".utf8) else {
            process.terminate()
            throw NSError(domain:"MissionLifecycleFixture",code:1)
        }
        return (process,input)
    }
    static func run() throws -> [String:Any] {
        NativeLocalization.testLanguage="en"
        let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
        let trackingMode=RunLoop.Mode.eventTracking
        let delegate=MissionApp()
        var replies=0
        delegate.terminationReply={ allowed in if allowed { replies += 1 } }
        delegate.rebuildMainMenu()
        let appMenu=NSApp.mainMenu?.items.first?.submenu
        let quitItem=appMenu?.items.first { $0.action == #selector(MissionApp.quit) }
        let namedMenu=NSApp.mainMenu?.items.first?.title == L("任务管家") && appMenu?.title == L("任务管家")
        let quitMenu=quitItem?.title == L("退出任务管家") && quitItem?.keyEquivalent == "q" && quitItem?.keyEquivalentModifierMask == [.command] && quitItem?.target === delegate
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:200,height:100),styleMask:[.titled,.closable],backing:.buffered,defer:true)
        window.isReleasedWhenClosed=false;window.close()
        let closeKeepsRunning = !delegate.applicationShouldTerminateAfterLastWindowClosed(app) && delegate.termination.phase == .running && !delegate.model.stopping
        let first=delegate.applicationShouldTerminate(app), repeated=delegate.applicationShouldTerminate(app)
        let repeatedWaits=first == .terminateLater && repeated == .terminateLater
        let completedInTrackingMode=wait(until:{replies == 1},mode:trackingMode)
        delegate.finishTermination()
        let replyOnce=replies == 1 && delegate.applicationShouldTerminate(app) == .terminateNow
        let graceful=try fixture("printf 'ready\\n'; while IFS= read -r line; do if [ \"$line\" = stop ]; then exit 0; fi; done")
        defer { if graceful.0.isRunning { _=Darwin.kill(graceful.0.processIdentifier,SIGKILL) } }
        let gracefulModel=MissionModel();gracefulModel.host=graceful.0;gracefulModel.hostInput=graceful.1
        var gracefulCallbacks=0;var gracefulReceipt:MissionStopReceipt?
        gracefulModel.stop(grace:0.5,finalWait:0.1) { gracefulReceipt=$0;gracefulCallbacks += 1 }
        gracefulModel.stop(grace:0.5,finalWait:0.1) { _ in gracefulCallbacks += 1 }
        let gracefulDone=wait(until:{gracefulCallbacks == 2})
        let gracefulStopped=gracefulDone && gracefulReceipt?.hostExited == true && gracefulReceipt?.terminateRequested == false
        let stubborn=try fixture("trap '' TERM; printf 'ready\\n'; while :; do :; done")
        defer { if stubborn.0.isRunning { _=Darwin.kill(stubborn.0.processIdentifier,SIGKILL) } }
        let stubbornModel=MissionModel();stubbornModel.host=stubborn.0;stubbornModel.hostInput=stubborn.1
        var stubbornReceipt:MissionStopReceipt?
        let start=ProcessInfo.processInfo.systemUptime
        stubbornModel.stop(grace:0.1,finalWait:0.1) { stubbornReceipt=$0 }
        let stopReturnedImmediately=ProcessInfo.processInfo.systemUptime-start < 0.05
        let stubbornDone=wait(until:{stubbornReceipt != nil})
        let stubbornBounded=stubbornDone && ProcessInfo.processInfo.systemUptime-start < 1 && stubbornReceipt?.terminateRequested == true && stubbornReceipt?.forceKillRequested == true
        let stubbornReaped=wait(until:{!stubborn.0.isRunning})
        let fallbackHost=try fixture("trap '' TERM; printf 'ready\\n'; while :; do :; done")
        defer { if fallbackHost.0.isRunning { _=Darwin.kill(fallbackHost.0.processIdentifier,SIGKILL) } }
        let fallbackDelegate=MissionApp()
        fallbackDelegate.model.host=fallbackHost.0;fallbackDelegate.model.hostInput=fallbackHost.1
        fallbackDelegate.shutdownGraceSeconds=0.1;fallbackDelegate.shutdownFinalWaitSeconds=0.3
        fallbackDelegate.shutdownReplyDeadlineSeconds=0.15
        var fallbackReplies=0
        fallbackDelegate.terminationReply={ if $0 {fallbackReplies += 1} }
        _=fallbackDelegate.applicationShouldTerminate(app)
        let fallbackCompleted=wait(until:{fallbackReplies == 1},mode:trackingMode)
        let fallbackHostReaped=wait(until:{!fallbackHost.0.isRunning})
        let fallbackReclaimsHost=fallbackCompleted && fallbackHostReaped
        // Fill an artificial pipe without blocking this thread, then restore
        // blocking mode. This reproduces the old synchronous write hazard.
        let full=Pipe();let fd=full.fileHandleForWriting.fileDescriptor
        let flags=fcntl(fd,F_GETFL);_ = fcntl(fd,F_SETFL,flags|O_NONBLOCK)
        var chunk=[UInt8](repeating:65,count:4096)
        while Darwin.write(fd,&chunk,chunk.count) > 0 {}
        _ = fcntl(fd,F_SETFL,flags)
        let fullModel=MissionModel();fullModel.hostInput=full
        var fullReceipt:MissionStopReceipt?
        let fullStart=ProcessInfo.processInfo.systemUptime
        fullModel.stop(grace:0.1,finalWait:0.1) { fullReceipt=$0 }
        let pipeWriteOffMain=ProcessInfo.processInfo.systemUptime-fullStart < 0.05 && wait(until:{fullReceipt != nil},mode:trackingMode)
        // Drain enough for the background writer to finish, then close safely.
        _ = full.fileHandleForReading.availableData
        _ = full.fileHandleForReading.readDataToEndOfFile()
        try? full.fileHandleForReading.close()
        let passed=namedMenu && quitMenu && closeKeepsRunning && repeatedWaits && completedInTrackingMode && replyOnce && gracefulStopped && stopReturnedImmediately && stubbornBounded && stubbornReaped && fallbackReclaimsHost && pipeWriteOffMain
        return ["native":true,"checksPassed":passed,"namedApplicationMenu":namedMenu,"quitMenuAndCommandQ":quitMenu,
            "closeKeepsRunning":closeKeepsRunning,"repeatedQuitWaits":repeatedWaits,"terminationReplyOnce":replyOnce,
            "completionInTrackingMode":completedInTrackingMode,"gracefulOwnedHostExit":gracefulStopped,
            "stopReturnsWithoutBlocking":stopReturnedImmediately,"unresponsiveOwnedHostBounded":stubbornBounded,
            "unresponsiveFixtureReaped":stubbornReaped,"fullPipeWriteOffMain":pipeWriteOffMain,
            "fallbackReclaimsOwnedHost":fallbackReclaimsHost,
            "noProductionHost":true,"fixtureProcessesStarted":3,"messagesSent":0,"privatePreferencesLoaded":false,"systemPowerChanged":false]
    }
}

@main enum MissionMain {
    static func main() {
        if CommandLine.arguments.contains("--lifecycle-self-test") {
            do {
                let report=try MissionLifecycleChecks.run()
                print(String(data:try JSONSerialization.data(withJSONObject:report,options:.sortedKeys),encoding:.utf8)!)
                if report["checksPassed"] as? Bool != true { exit(1) }
            } catch { fputs("Native lifecycle self-test failed: \(error)\n",stderr);exit(1) }
            return
        }
        if CommandLine.arguments.contains("--editor-self-test") {
            let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
            let report=MissionPromptEditorChecks.run()
            print(String(data:try! JSONSerialization.data(withJSONObject:report,options:.sortedKeys),encoding:.utf8)!)
            return
        }
        if let index=CommandLine.arguments.firstIndex(of:"--activity-preview"), !CommandLine.arguments.contains("--ui-self-test") {
            guard CommandLine.arguments.count>index+2 else {
                fputs("Usage: --activity-preview fixture.json output.png [--dark] [--english]\n",stderr);exit(2)
            }
            do {try MissionPreview.render(fixture:CommandLine.arguments[index+1],output:CommandLine.arguments[index+2])}
            catch {fputs("Native activity preview failed: \(error)\n",stderr);exit(1)}
            return
        }
        if let index = CommandLine.arguments.firstIndex(of: "--ui-self-test"), CommandLine.arguments.count > index + 2 {
            do {
                try MissionPreview.render(fixture: CommandLine.arguments[index + 1], output: CommandLine.arguments[index + 2])
            } catch { fputs("Native UI self-test failed: \(error)\n", stderr); exit(1) }
            return
        }
        if let index=CommandLine.arguments.firstIndex(of:"--logo-self-test"),CommandLine.arguments.count>index+1 {
            do { try JuicerPreview.export(to:CommandLine.arguments[index+1]) }
            catch { fputs("Logo verification failed: \(error)\n",stderr);exit(1) }
            return
        }
        if CommandLine.arguments.contains("--self-test") {
            let report: [String: Any] = ["version": MissionIdentity.version, "architecture": "arm64", "native": true, "ui": "SwiftUI-AppKit", "webView": false,
                "releaseSigned": MissionIdentity.releaseSigned, "helperPreviewFailsClosed": !MissionIdentity.releaseSigned,
                "brandIdentityVersion":"1.3.0","brandMotionChecks":JuicerMotion.selfTest(), "hardwareReadOnly": true, "privateDataLoaded": false]
            let data = try! JSONSerialization.data(withJSONObject: report, options: .sortedKeys)
            print(String(data: data, encoding: .utf8)!)
            if !JuicerMotion.selfTest() {exit(1)}
            return
        }
        let app = NSApplication.shared
        let delegate = MissionApp()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
