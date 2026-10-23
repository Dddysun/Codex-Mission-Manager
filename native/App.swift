import AppKit
import Carbon
import SwiftUI
import ServiceManagement
import UserNotifications
import IOKit.pwr_mgt

final class MissionModel: ObservableObject {
    @Published var backend = "正在启动本机服务"
    @Published var client = "尚未检查"
    @Published var power = "尚未检查"
    @Published var awake = false
    @Published var login = "尚未检查"
    @Published var notifications = "尚未检查"
    @Published var helper = "尚未检查"
    @Published var closedLid = "未启用"
    @Published var checked = "尚未检查"
    @Published var error = ""
    @Published var paused = true
    @Published var allowBattery = false
    @Published var waitingForLock = false
    var lockDeadline = Date.distantPast
    var baseURL: URL?
    var stateDirectory: URL?
    @Published var snapshot: MissionSnapshot?
    @Published var connected = false
    @Published var busy = false
    @Published var notice = ""
    @Published var drafts: [String: MissionDraft] = [:]
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

    var signed: Bool { MissionIdentity.releaseSigned }
    var service: SMAppService { SMAppService.daemon(plistName: MissionIdentity.helperPlist) }
    var support: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/CodexMissionManager") }

    func start() {
        setAwake(UserDefaults.standard.object(forKey: "keepAwake") as? Bool ?? true)
        let center = DistributedNotificationCenter.default()
        observerTokens.append(center.addObserver(forName: .init("com.apple.screenIsLocked"), object: nil, queue: .main) { [weak self] _ in
            guard let self, self.waitingForLock, Date() < self.lockDeadline else { return }
            self.waitingForLock = false
            self.withHelper { peer in peer.enableClosedLid(onBattery: self.allowBattery) { value in
                DispatchQueue.main.async { self.closedLid = value["reason"] as? String ?? "未确认" }
            } }
        })
        observerTokens.append(center.addObserver(forName: .init("com.apple.screenIsUnlocked"), object: nil, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.waitingForLock = false
            if self.powerConnection != nil { self.disableClosedLid() }
        })
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            self?.refresh()
            self?.heartbeat()
            self?.deliverNotices()
            Task { await self?.refreshControl() }
        }
        startHost()
    }

    func startHost() {
        guard host == nil, let resources = Bundle.main.resourceURL else { return }
        let task = Process(), output = Pipe(), input = Pipe()
        task.executableURL = resources.appendingPathComponent("python/bin/python3")
        task.arguments = ["-I", resources.appendingPathComponent("backend/app_host.py").path]
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
            task.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
                self?.backend = "后台已退出；已有记录保留"
                self?.host = nil
                self?.connected = false
            } }
            try task.run()
            host = task
            hostInput = input
        } catch { self.error = error.localizedDescription; backend = "启动失败" }
    }

    func receiveHost(_ data: Data) {
        hostOutput.append(data)
        while let newline = hostOutput.firstIndex(of: 10) {
            let line = Data(hostOutput[..<newline])
            hostOutput.removeSubrange(...newline)
            guard let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                  let text = value["url"] as? String, let url = URL(string: text),
                  url.scheme == "http", url.host == "127.0.0.1", url.port != nil else { continue }
            baseURL = url
            stateDirectory = (value["state_dir"] as? String).map { URL(fileURLWithPath: $0) }
            backend = value["external"] as? Bool == true ? "已连接原有任务管家，未启动重复执行器" : "应用自带后台已启动"
            Task { await refreshControl() }
        }
    }

    // A private ephemeral cookie session authenticates the local JSON API.
    // No HTML is rendered and no WebKit runtime is used by the application.
    @MainActor func refreshControl() async {
        guard let url = baseURL, !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            _ = try await session.data(from: url) // Compatibility session handshake with existing backends.
            let (data, response) = try await session.data(from: url.appendingPathComponent("api/state"))
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                throw NSError(domain: "Guardian", code: 1, userInfo: [NSLocalizedDescriptionKey: "无法读取本机后台状态"])
            }
            let value = try JSONDecoder().decode(MissionSnapshot.self, from: data)
            await MainActor.run {
                self.snapshot = value; self.paused = value.control_paused; self.connected = true; self.error = ""
            }
        } catch { await MainActor.run { self.connected = false; self.error = "后台连接待恢复：" + error.localizedDescription } }
    }

    func perform(_ payload: [String: Any]) {
        guard !busy, connected, let url = baseURL else { return }
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
                    throw NSError(domain: "Guardian", code: 1, userInfo: [NSLocalizedDescriptionKey: body?["error"] as? String ?? "操作结果待核对，请刷新后检查记录"])
                }
                await MainActor.run {
                    self.notice = body?["message"] as? String ?? "操作已提交"
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
        drafts[chat.key] = MissionDraft(text: String(text.prefix(8000)), revision: revision)
    }
    func savePlan(_ chat: MissionChat, enabled: Bool) {
        guard chat.controllable else { return }
        perform(MissionCommands.plan(chat, draft: drafts[chat.key], enabled: enabled))
    }
    func executeNow(_ chat: MissionChat) {
        guard chat.canExecute else { return }
        perform(MissionCommands.immediate(chat, draft: drafts[chat.key]))
    }

    func setAwake(_ value: Bool) {
        if value && assertion == 0 {
            let result = IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep as CFString,
                IOPMAssertionLevel(kIOPMAssertionLevelOn), "任务管家：保持后台工作，允许屏幕熄灭" as CFString, &assertion)
            awake = result == kIOReturnSuccess
        } else if !value && assertion != 0 { IOPMAssertionRelease(assertion); assertion = 0; awake = false }
        UserDefaults.standard.set(awake, forKey: "keepAwake")
    }

    func registration(_ value: SMAppService.Status) -> String {
        switch value {
        case .enabled: return "系统已允许"
        case .requiresApproval: return "等待系统批准／已被停用"
        case .notRegistered: return "尚未登记"
        case .notFound: return "服务文件不可用"
        @unknown default: return "未知，待确认"
        }
    }

    func refresh() {
        login = registration(SMAppService.mainApp.status)
        helper = signed ? registration(service.status) : "本机预览包未配置 Developer ID，管理员服务不可启用"
        let p = HardwareState.power()
        power = "\(p.ac ? "外接电源" : "电池／电源待确认") · 电量 \(p.battery.map { "\($0)%" } ?? "未知") · \(HardwareState.lidClosed.map { $0 ? "已合盖" : "开盖" } ?? "机盖状态待确认")"
        let app = URL(fileURLWithPath: "/Applications/ChatGPT.app/Contents/Info.plist")
        if let data = try? Data(contentsOf: app), let info = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] {
            let build = info["CFBundleVersion"] as? String ?? "未知"
            client = build == "20770" ? "检测到兼容客户端 build 20770；实际登录与连接见任务页" : "客户端 build \(build) 尚未适配，控制会被阻止"
        } else { client = "未找到 ChatGPT 桌面客户端；应用内置 Python，但不分发原客户端" }
        checked = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        if waitingForLock && Date() >= lockDeadline { waitingForLock = false; closedLid = "锁屏等待已超时，未启用合盖保持" }
        UNUserNotificationCenter.current().getNotificationSettings { value in DispatchQueue.main.async {
            switch value.authorizationStatus {
            case .authorized, .provisional: self.notifications = "已允许"
            case .denied: self.notifications = "已拒绝；任务仍可执行"
            case .notDetermined: self.notifications = "尚未申请"
            default: self.notifications = "状态待确认"
            }
        } }
    }

    func requestNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, error in
            DispatchQueue.main.async { self.error = error?.localizedDescription ?? ""; self.refresh() }
        }
    }
    func registerLogin() {
        do { try SMAppService.mainApp.register(); refresh() }
        catch { self.error = error.localizedDescription }
    }
    func unregisterLogin() {
        do { try SMAppService.mainApp.unregister(); refresh() }
        catch { self.error = error.localizedDescription }
    }
    func registerPower() {
        guard signed else { error = "需要发行签名和系统管理员批准；此预览包不会安装 root 服务"; return }
        do { try service.register(); refresh(); SMAppService.openSystemSettingsLoginItems() }
        catch { self.error = error.localizedDescription }
    }
    func removePower() {
        guard signed else { return }
        withHelper { peer in peer.disable { _ in DispatchQueue.main.async {
            do { try self.service.unregister(); self.powerConnection?.invalidate(); self.powerConnection = nil; self.refresh() }
            catch { self.error = error.localizedDescription }
        } } }
    }
    func withHelper(_ body: @escaping (PowerHelperProtocol) -> Void) {
        guard signed, service.status == .enabled else { error = "管理员辅助服务未获准运行"; return }
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
            DispatchQueue.main.async { self?.closedLid = "服务连接失败：" + error.localizedDescription }
        } as? PowerHelperProtocol
        if let proxy { body(proxy) }
    }
    func prepareClosedLid() {
        guard signed, service.status == .enabled else { error = "需先完成发行签名与管理员辅助服务授权"; return }
        waitingForLock = true
        lockDeadline = Date().addingTimeInterval(60)
        closedLid = "等待锁屏：请按 Control–Command–Q；确认锁屏事件后才启用"
        // No simulated keyboard input, Accessibility access or private locking API.
    }
    func disableClosedLid() {
        waitingForLock = false
        withHelper { peer in peer.disable { value in DispatchQueue.main.async {
            self.closedLid = value["reason"] as? String ?? "待确认"
        } } }
    }
    func heartbeat() {
        guard powerConnection != nil else { return }
        withHelper { peer in peer.heartbeat { value in DispatchQueue.main.async {
            self.closedLid = value["reason"] as? String ?? "待确认"
        } } }
    }
    func deliverNotices() {
        guard let stateDirectory,
              let data = try? Data(contentsOf: stateDirectory.appendingPathComponent("native-notices.json")),
              let records = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return }
        for record in records {
            guard let key = record["key"] as? String else { continue }
            if !notificationKeys.contains(key), !firstNoticeRead {
                let content = UNMutableNotificationContent()
                content.title = record["title"] as? String ?? "任务管家"
                content.body = record["body"] as? String ?? ""
                UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: key, content: content, trigger: nil))
            }
            notificationKeys.insert(key)
        }
        firstNoticeRead = false
    }
    func stop() {
        timer?.invalidate()
        if powerConnection != nil { withHelper { $0.disable { _ in } } }
        if assertion != 0 { IOPMAssertionRelease(assertion); assertion = 0 }
        try? hostInput?.fileHandleForWriting.write(contentsOf: Data("stop\n".utf8))
        try? hostInput?.fileHandleForWriting.close()
    }
    func openSettings(_ destination: String) {
        if destination == "login" { SMAppService.openSystemSettingsLoginItems(); return }
        let known = ["battery": "x-apple.systempreferences:com.apple.preference.battery", "notifications": "x-apple.systempreferences:com.apple.preference.notifications", "privacy": "x-apple.systempreferences:com.apple.preference.security"]
        if let text = known[destination], let url = URL(string: text) { NSWorkspace.shared.open(url) }
    }
}

struct MissionSettings: View {
    @ObservedObject var model: MissionModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("后台运行与系统权限").font(.title2.bold())
                Text("V0.1 · 授权状态、运行条件与实机验证分别展示").foregroundStyle(.secondary)
                GroupBox("正常开盖后台") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.backend); Text(model.client).foregroundStyle(.secondary)
                        Button("重新连接后台") { model.startHost() }.disabled(model.host != nil)
                        Text("无需辅助功能、录屏或完全磁盘访问权限。关闭窗口后仍运行；退出应用才停止管家。")
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                GroupBox("锁屏与熄屏") {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle("保持系统清醒，允许屏幕熄灭", isOn: Binding(get: { model.awake }, set: { model.setAwake($0) }))
                        Text(model.awake ? "本应用防空闲睡眠断言已启用" : "本应用未持有防睡眠断言")
                        Text(model.power).foregroundStyle(.secondary)
                        Text("当前配置会让管家后端持有自己的防睡眠保护；连接旧服务时，旧服务也可能持有保护。锁屏、熄屏发送及打开未加载聊天：实机验收未完成。")
                        Button("打开电池设置") { model.openSettings("battery") }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                GroupBox("无外屏合盖运行 · 增强模式") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.helper)
                        Text(model.closedLid).foregroundStyle(.secondary)
                        Text("管理员服务仅处理固定睡眠开关。默认需接电；电池余量≤20%、严重热压力或客户端失联45秒时恢复。启用前需手动锁屏；解锁会撤销合盖保持。机盖事件和锁屏事件均需本机实测。")
                        Toggle("允许电池运行（保留20%截止保护）", isOn: $model.allowBattery)
                        HStack {
                            Button("申请管理员服务授权") { model.registerPower() }.disabled(!model.signed)
                            Button("打开系统设置") { model.openSettings("login") }
                        }
                        HStack {
                            Button("准备启用，等待锁屏") { model.prepareClosedLid() }.disabled(!model.signed)
                            Button("取消／停用") { model.disableClosedLid() }.disabled(!model.signed)
                            Button("移除辅助服务") { model.removePower() }.disabled(!model.signed)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                GroupBox("登录启动") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.login)
                        HStack { Button("登记登录启动") { model.registerLogin() }; Button("取消登录启动") { model.unregisterLogin() }; Button("打开系统设置") { model.openSettings("login") } }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                GroupBox("通知") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.notifications)
                        Text("仅通知暂停、续接、发送失败和需处理异常。拒绝通知不影响执行。")
                        HStack { Button("申请通知权限") { model.requestNotifications() }; Button("打开通知设置") { model.openSettings("notifications") } }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                if !model.error.isEmpty { Text(model.error).foregroundStyle(.orange).textSelection(.enabled) }
                HStack { Button("重新检查") { model.refresh() }; Text("最近检查：\(model.checked)").foregroundStyle(.secondary) }
                Text("本机预览包采用临时签名，未公证。管理员合盖服务未启用、未实机验证；不应将本包标记为合盖能力验收通过。")
                    .font(.footnote).foregroundStyle(.secondary)
            }.padding(24)
        }.frame(minWidth: 670, minHeight: 600)
    }
}

final class MissionApp: NSObject, NSApplicationDelegate {
    let model = MissionModel()
    var window: NSWindow!
    var settingsWindow: NSWindow?
    var statusItem: NSStatusItem!
    var pauseMenu: NSMenuItem!
    var isQuitting = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "设置…", action: #selector(showSettings), keyEquivalent: ",").target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出任务管家", action: #selector(quit), keyEquivalent: "q").target = self
        appItem.submenu = appMenu
        let editItem = NSMenuItem(); menu.addItem(editItem)
        let edit = NSMenu(title: "编辑"); editItem.submenu = edit
        for (title, selector, key) in [("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] { edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key) }
        NSApp.mainMenu = menu
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.image = NSImage(systemSymbolName: "shield", accessibilityDescription: "任务管家")
        statusItem.button?.toolTip = "任务管家"
        let tray = NSMenu()
        tray.addItem(withTitle: "打开任务管家", action: #selector(showWindow), keyEquivalent: "").target = self
        pauseMenu = tray.addItem(withTitle: "暂停／恢复自动控制", action: #selector(toggleControl), keyEquivalent: ""); pauseMenu.target = self
        tray.addItem(.separator())
        tray.addItem(withTitle: "退出任务管家", action: #selector(quit), keyEquivalent: "").target = self
        statusItem.menu = tray
        let content = MissionWindow(model: model, showSettings: { [weak self] in self?.showSettings() })
        window = NSWindow(contentViewController: NSHostingController(rootView: content))
        window.title = "任务管家 · V0.1 原生预览"
        window.setContentSize(NSSize(width: 1380, height: 900))
        window.minSize = NSSize(width: 1120, height: 680)
        window.isReleasedWhenClosed = false
        window.titlebarAppearsTransparent = true
        window.center()
        model.start()
        let loginLaunch = NSAppleEventManager.shared().currentAppleEvent?.paramDescriptor(forKeyword: AEKeyword(keyAELaunchedAsLogInItem)) != nil
        if !loginLaunch && !CommandLine.arguments.contains("--background") { showWindow() }
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.pauseMenu.title = self.model.paused ? "恢复自动控制" : "暂停自动控制"
        }
    }
    @objc func showWindow() { NSApp.setActivationPolicy(.regular); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func showSettings() {
        if settingsWindow == nil {
            let host = NSHostingController(rootView: MissionSettings(model: model))
            let value = NSWindow(contentViewController: host)
            value.title = "设置 · 后台运行与系统权限"
            value.setContentSize(NSSize(width: 740, height: 760)); value.isReleasedWhenClosed = false; value.center()
            settingsWindow = value
        }
        model.refresh(); settingsWindow?.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc func toggleControl() { model.toggleAutomatic() }
    @objc func quit() { NSApp.terminate(nil) }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !isQuitting else { return .terminateNow }
        isQuitting = true
        model.stop()
        let end = Date().addingTimeInterval(40)
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { timer in
            if self.model.host?.isRunning != true || Date() > end { timer.invalidate(); NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}

@main enum MissionMain {
    static func main() {
        if let index = CommandLine.arguments.firstIndex(of: "--ui-self-test"), CommandLine.arguments.count > index + 2 {
            do {
                try MissionPreview.render(fixture: CommandLine.arguments[index + 1], output: CommandLine.arguments[index + 2])
            } catch { fputs("Native UI self-test failed: \(error)\n", stderr); exit(1) }
            return
        }
        if CommandLine.arguments.contains("--self-test") {
            let report: [String: Any] = ["version": MissionIdentity.version, "architecture": "arm64", "native": true, "ui": "SwiftUI-AppKit", "webView": false,
                "releaseSigned": MissionIdentity.releaseSigned, "helperPreviewFailsClosed": !MissionIdentity.releaseSigned,
                "hardwareReadOnly": true, "privateDataLoaded": false]
            let data = try! JSONSerialization.data(withJSONObject: report, options: .sortedKeys)
            print(String(data: data, encoding: .utf8)!)
            return
        }
        let app = NSApplication.shared
        let delegate = MissionApp()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
