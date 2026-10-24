import AppKit
import SwiftUI

private let missionGreen = Color(nsColor: NSColor(name:nil) { appearance in appearance.bestMatch(from:[.darkAqua,.aqua]) == .darkAqua ? NSColor(red:0.48,green:0.73,blue:0.57,alpha:1) : NSColor(red:0.26,green:0.48,blue:0.36,alpha:1) })
private let missionInk = Color(nsColor: NSColor(name:nil) { appearance in appearance.bestMatch(from:[.darkAqua,.aqua]) == .darkAqua ? NSColor(red:0.04,green:0.09,blue:0.07,alpha:1) : NSColor(red:0.08,green:0.16,blue:0.13,alpha:1) })
private let missionCanvas = Color(nsColor: .windowBackgroundColor)

struct MissionWindow: View {
    @ObservedObject var model: MissionModel
    var showSettings: () -> Void
    @State private var section = "tasks"
    @State private var search = ""
    @State private var category = "all"
    @State private var filter = "all"
    @State private var selected: String?

    var chats: [MissionChat] {
        (model.snapshot?.tasks ?? []).filter { chat in
            (category == "all" || (chat.category ?? "codex") == category) &&
            (search.isEmpty || chat.name.localizedCaseInsensitiveContains(search) || chat.id.localizedCaseInsensitiveContains(search)) &&
            (filter == "all" || filter == "waiting" && (chat.waiting || chat.plan?.scheduled == true) || filter == "scheduled" && chat.plan?.scheduled == true || filter == "attention" && chat.attention)
        }
    }
    var body: some View {
        HSplitView {
            sidebar.frame(minWidth: 230, idealWidth: 248, maxWidth: 290)
            VStack(spacing: 0) {
                toolbar
                Divider()
                if !model.connected || model.snapshot?.healthy == false {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "exclamationmark.triangle")
                        VStack(alignment: .leading, spacing: 4) {
                            Text(!model.connected ? L("正在连接本机后台") : L("检查状态待恢复")).fontWeight(.semibold)
                            Text(model.connectionError.isEmpty ? L("正在核对账号、额度和聊天状态；取得可靠状态后才能自动续接。") : model.connectionError)
                        }
                        Spacer()
                        Button(L("重新检查")) { Task { await model.refreshControl() } }
                    }.font(.callout).padding(14).background(Color.orange.opacity(0.1))
                }
                if !model.notice.isEmpty {
                    HStack {
                        Image(systemName: "info.circle")
                        Text(L(model.notice)).textSelection(.enabled)
                        Spacer()
                        Button { model.notice = "" } label: { Image(systemName: "xmark") }.buttonStyle(.plain).help(L("关闭提示"))
                    }.font(.callout).padding(12).background(missionGreen.opacity(0.12))
                }
                if section == "tasks" { taskPage }
                else if section == "events" { eventsPage }
                else { rulesPage }
            }.frame(minWidth: 860, maxWidth: .infinity, maxHeight: .infinity).background(missionCanvas)
        }
        .tint(missionGreen)
        .preferredColorScheme(model.colorScheme)
        .sheet(isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } })) {
            if let chat = model.snapshot?.tasks.first(where: { $0.key == selected }) {
                detail(chat)
            } else { VStack { Text(L("该聊天当前未在目录内")); Button(L("关闭")) { selected = nil } }.padding(32) }
        }
    }
    var sidebar: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(spacing: 12) {
                Image(systemName: "checkmark.shield").font(.system(size: 28)).padding(10).background(.white.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 4) {
                    Text(L("任务管家")).font(.title2.bold())
                    Text("MISSION / LOCAL").font(.system(size: 10, weight: .semibold, design: .monospaced)).tracking(2).foregroundStyle(.white.opacity(0.5))
                }
            }.padding(.bottom, 16)
            Text(L("工作空间")).font(.caption).foregroundStyle(.white.opacity(0.5))
            VStack(spacing: 6) {
                nav(L("任务控制"), icon: "square.grid.2x2", key: "tasks")
                nav(L("操作记录"), icon: "clock.arrow.circlepath", key: "events")
                nav(L("运行规则"), icon: "slider.horizontal.3", key: "rules")
            }
            Divider().overlay(.white.opacity(0.15))
            usage
            Spacer(minLength: 10)
            account
            Divider().overlay(.white.opacity(0.15))
            Button(action: showSettings) { Label(L("设置与系统权限"), systemImage: "gearshape").frame(maxWidth: .infinity, alignment: .leading) }
                .buttonStyle(.plain).padding(.vertical, 4)
            Label(L("关闭窗口后继续工作"), systemImage: "circle.fill").font(.caption2).foregroundStyle(.white.opacity(0.5))
        }.padding(22).foregroundStyle(.white.opacity(0.88)).frame(maxHeight: .infinity).background(missionInk)
    }
    func nav(_ title: String, icon: String, key: String) -> some View {
        Button { section = key } label: {
            HStack { Label(title, systemImage: icon); Spacer(); if key == "tasks" { Text("\(model.snapshot?.tasks.count ?? 0)").font(.caption).monospacedDigit() } }
                .padding(12).background(section == key ? Color.white.opacity(0.12) : .clear).clipShape(RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.plain)
    }
    var usage: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text(L("当前额度")).font(.subheadline.bold()); Spacer(); Text(model.snapshot?.usage?.account?.subscription ?? L("待识别")).font(.caption.bold()).padding(.horizontal, 8).padding(.vertical, 4).background(.white.opacity(0.12)).clipShape(Capsule()) }
            quota(L("五小时额度"), value: model.snapshot?.usage?.windows.five_hour)
            quota(L("周额度"), value: model.snapshot?.usage?.windows.weekly)
            Text(usageStale ? L("额度待同步 · 上次记录") : L("服务实际限额 · 本机时区"))
                .font(.caption2).foregroundStyle(usageStale ? Color.orange : .white.opacity(0.5))
        }
    }
    var usageStale: Bool {
        guard model.connected, let usage = model.snapshot?.usage, let observed = usage.observed_at else { return true }
        return usage.stale != false || Date().timeIntervalSince1970 - observed > 90
    }
    func quota(_ title: String, value: MissionQuota?) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack { Text(title); Spacer(); Text(value?.validRemaining.map { String(format: "%.1f%%", $0) } ?? L("未提供")).monospacedDigit() }.font(.caption)
            ProgressView(value: value?.validRemaining ?? 0, total: 100)
                .tint((value?.validRemaining ?? 100) <= 10 ? .orange : Color(red: 0.51, green: 0.75, blue: 0.61))
                .accessibilityLabel(title).accessibilityValue(value?.validRemaining.map { L("剩余 %@%", String(describing: $0)) } ?? L("未提供"))
            Text(value?.reset == nil ? L("刷新时间未提供") : L("下次刷新 ") + missionTime(value?.reset))
                .font(.caption2).foregroundStyle(.white.opacity(0.58)).fixedSize(horizontal: false, vertical: true)
        }
    }
    var account: some View {
        let account = model.snapshot?.usage?.account
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(.white.opacity(0.12))
                    Text(account?.initials ?? "?").font(.headline)
                    if let text = account?.avatar_url, let url = URL(string: text), url.scheme == "https" {
                        AsyncImage(url: url) { image in image.resizable().scaledToFill() } placeholder: { Color.clear }
                    }
                }.frame(width: 38, height: 38).clipShape(Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(account?.displayName ?? L("未识别账号")).font(.subheadline.bold()).lineLimit(1)
                    Text(account?.email ?? L("登录信息未提供")).font(.caption2).foregroundStyle(.white.opacity(0.5)).lineLimit(1)
                }
            }
            Text(L("账号 ID")).font(.caption2).foregroundStyle(.white.opacity(0.5))
            HStack(alignment: .top) {
                Text(account?.id ?? L("接口暂未提供")).font(.system(size: 10, design: .monospaced)).textSelection(.enabled).lineLimit(3)
                Spacer(minLength: 0)
                if let id = account?.id { Button { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(id, forType: .string) } label: { Image(systemName: "doc.on.doc") }.buttonStyle(.plain).help(L("复制账号 ID")) }
            }
        }
    }
    var toolbar: some View {
        HStack {
            Text(L("本机工作空间")).foregroundStyle(.secondary)
            Text("/").foregroundStyle(.tertiary)
            Text(section == "tasks" ? L("任务控制") : section == "events" ? L("操作记录") : L("运行规则")).fontWeight(.medium)
            Spacer()
            Text(L("最近同步 ") + missionTime(model.snapshot?.observed_at)).font(.caption).foregroundStyle(.secondary)
            Button { Task { await model.refreshControl() } } label: { Image(systemName: "arrow.clockwise") }.help(L("刷新状态"))
        }.padding(.horizontal, 26).padding(.vertical, 16)
    }
    var taskPage: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(L("任务控制")).font(.system(size: 28, weight: .bold))
                    Text(L("根据可用额度管理任务暂停、恢复和预约执行。")).foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 8) {
                    Text(model.snapshot?.control_enabled == true && model.connected ? L("自动控制已启用") : L("自动控制未生效")).font(.caption).foregroundStyle(.secondary)
                    Button(model.snapshot?.running == false ? L("启动后台服务") : model.paused ? L("启用自动控制") : L("暂停自动控制")) { model.toggleAutomatic() }.disabled(!model.connected || model.busy)
                }
            }
            HStack(spacing: 0) {
                statistic(L("聊天目录"), count: model.snapshot?.tasks.count ?? 0)
                statistic(L("正在执行"), count: model.snapshot?.tasks.filter { $0.active }.count ?? 0)
                statistic(L("等待恢复 / 预约"), count: model.snapshot?.tasks.filter { $0.waiting || $0.plan?.scheduled == true }.count ?? 0)
                statistic(L("需要留意"), count: model.snapshot?.tasks.filter { $0.attention }.count ?? 0)
            }.padding(.vertical, 14).background(Color(nsColor: .controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 10))
            HStack {
                Picker(L("来源"), selection: $category) { Text(L("全部")).tag("all"); Text("Codex").tag("codex"); Text("ChatGPT").tag("chatgpt") }.pickerStyle(.segmented).frame(width: 240)
                Picker(L("筛选"), selection: $filter) { Text(L("全部状态")).tag("all"); Text(L("等待恢复")).tag("waiting"); Text(L("已预约")).tag("scheduled"); Text(L("需留意")).tag("attention") }.frame(width: 190)
                Spacer()
                TextField(L("搜索聊天名称或 ID"), text: $search).textFieldStyle(.roundedBorder).frame(maxWidth: 240)
            }
            HStack { Text(L("聊天 / 当前执行阶段")).frame(maxWidth: .infinity, alignment: .leading); Text(L("当前状态 / 自动控制")).frame(width: 138, alignment: .leading); Text(L("额度恢复后执行 · 一次性")).frame(width: 310, alignment: .leading) }
                .font(.caption).foregroundStyle(.secondary).padding(.horizontal, 16)
            ScrollView {
                LazyVStack(spacing: 12) {
                    if chats.isEmpty { ContentUnavailableView(model.snapshot == nil ? L("正在读取聊天目录") : L("没有匹配的聊天"), systemImage: "bubble.left.and.bubble.right", description: Text(L("Codex 目录随后台更新；ChatGPT 仅显示已知目录。"))) }
                    ForEach(chats, id: \.key) { chat in MissionChatRow(model: model, chat: chat, showDetail: { selected = chat.key }) }
                }.padding(.trailing, 4)
            }
            HStack {
                Text(L("显示 %@ / %@ 个聊天 · 每 5 秒同步", String(describing: chats.count), String(describing: model.snapshot?.tasks.count ?? 0)))
                Spacer()
                Text(model.snapshot?.catalog?.local_error == nil ? L("ChatGPT 仅目录，不自动执行") : L("本机目录待重连，显示上次记录"))
            }.font(.caption2).foregroundStyle(.secondary)
        }.padding(26)
    }
    func statistic(_ title: String, count: Int) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(title).font(.caption).foregroundStyle(.secondary); Text("\(count)").font(.system(size: 26, weight: .semibold)).monospacedDigit() }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
    }
    var eventsPage: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(L("操作记录")).font(.largeTitle.bold())
            Text(L("查看最近 200 条任务控制与指令发送记录。")).foregroundStyle(.secondary)
            List(model.snapshot?.events ?? []) { event in
                HStack(alignment: .top, spacing: 18) {
                    Image(systemName: "clock").foregroundStyle(missionGreen)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(L(event.label)).fontWeight(.semibold)
                        Text(event.name ?? L("全局控制"))
                        if let reason = event.detail?.reason { Text(L(reason)).font(.callout).foregroundStyle(.secondary).textSelection(.enabled) }
                    }
                    Spacer()
                    Text(missionTime(event.created)).font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }.padding(.vertical, 10)
            }.listStyle(.inset)
            if model.snapshot?.events.isEmpty != false { Text(L("暂无控制操作记录")).foregroundStyle(.secondary) }
        }.padding(26)
    }
    var rulesPage: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text(L("运行规则")).font(.largeTitle.bold())
                rule(L("自动暂停与续接"), L("五小时剩余 ≤%@% 时暂停允许接管的执行中聊天。真实恢复窗口且余量 ≥%@% 后，连续复核至少 %@ 秒，再核对周额度、账号、原聊天与使用许可。", String(describing: Int(model.snapshot?.policy.pause ?? 10)), String(describing: Int(model.snapshot?.policy.resume ?? 20)), String(describing: Int(model.snapshot?.policy.confirm_seconds ?? 5))))
                rule(L("下个窗口执行一次"), L("预约开关独立于单聊自动控制。可以安排空闲聊天；真实恢复后只发送一次。保存指令不会立刻发送。关闭全局自动控制会阻止预约发送。"))
                rule(L("立刻执行"), L("发送当前指令框内容，不等待刷新。发送后等待真实回执，不把提交成功当作已执行。执行中、等待审批、额度或账号异常时，后台会拒绝发送。结果不明确时不会自动重复发送。"))
                rule(L("手动操作优先"), L("人工新指令、审批与 Goal 约束优先。聊天完成后等待下一条指令，不会无限续做。ChatGPT 普通聊天仅显示目录。"))
                rule(L("后台运行"), L("关闭主窗口后继续运行。退出应用停止管家和自身电源保护，不中断原客户端正在执行的聊天。锁屏、熄屏与合盖是不同的运行条件。"))
                Button(L("后台运行与系统权限…"), action: showSettings)
            }.padding(30).frame(maxWidth: 850, alignment: .leading)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    func rule(_ title: String, _ text: String) -> some View {
        GroupBox { VStack(alignment: .leading, spacing: 10) { Text(title).font(.headline); Text(text).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }.padding(12).frame(maxWidth: .infinity, alignment: .leading) }
    }
    func detail(_ chat: MissionChat) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Text(chat.name).font(.title2.bold()); Spacer(); Button(L("完成")) { selected = nil }.keyboardShortcut(.defaultAction) }
            Text(L(chat.status)).font(.headline)
            Text(chat.execution_stage?.text ?? L("暂未读取到公开执行进展")).textSelection(.enabled)
            Divider()
            Text(L("来源：%@", String(describing: L(chat.source_label ?? "Codex"))))
            Text(L("上次暂停：%@", String(describing: missionTime(chat.paused_at))))
            Text(L("上次续做：%@", String(describing: missionTime(chat.resumed_at))))
            Text(L("聊天 ID：%@", String(describing: chat.id))).font(.system(.body, design: .monospaced)).textSelection(.enabled)
            if let reason = chat.reason ?? chat.connection_error ?? chat.capability_note { Text(L(reason)).foregroundStyle(.secondary).textSelection(.enabled) }
            if let r = chat.immediate {
                Divider(); Text(L("立刻执行：%@", String(describing: r.label))); Text(L("发送标识：%@", String(describing: r.id))).textSelection(.enabled)
                if let turn = r.turn_id { Text(L("确认回合：%@", String(describing: turn))).textSelection(.enabled) }
                if let message = r.message { Text(L(message)).textSelection(.enabled) }
            }
        }.padding(28).frame(width: 620)
    }
}

struct MissionChatRow: View {
    @ObservedObject var model: MissionModel
    let chat: MissionChat
    var showDetail: () -> Void
    var locked: Bool { model.busy || !model.connected }
    var prompt: Binding<String> { Binding(get: { model.drafts[chat.key]?.text ?? chat.plan?.prompt ?? L("继续任务") }, set: { model.editPrompt(chat, text: $0) }) }
    var statusColor: Color { !model.connected ? .secondary : chat.attention ? .orange : chat.active ? missionGreen : chat.waiting ? .orange : .secondary }
    var body: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: chat.category == "chatgpt" ? "bubble.left.and.bubble.right" : "terminal").foregroundStyle(missionGreen).padding(.top, 2)
                    VStack(alignment: .leading, spacing: 5) {
                        Button(action: showDetail) { Text(chat.name).font(.headline).multilineTextAlignment(.leading) }.buttonStyle(.plain)
                        Text("\(L(chat.source_label ?? "Codex")) / \(String(chat.id.prefix(8)))").font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary)
                    }
                }
                VStack(alignment: .leading, spacing: 7) {
                    Text(L("当前执行阶段")).font(.caption.bold()).foregroundStyle(missionGreen)
                    if let stamp = chat.execution_stage?.updated_at { Text(missionTime(stamp)).font(.caption2).foregroundStyle(.secondary) }
                    Text(chat.execution_stage?.text ?? (chat.controllable ? L("暂未读取到执行进展") : L("当前仅显示目录，执行阶段暂不可读")))
                        .font(.callout).foregroundStyle(.secondary).lineLimit(5).textSelection(.enabled)
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading).background(missionGreen.opacity(0.05)).clipShape(RoundedRectangle(cornerRadius: 8))
            }.frame(maxWidth: .infinity, alignment: .leading)
            VStack(alignment: .leading, spacing: 20) {
                Label(model.connected ? chat.status : L("状态待同步"), systemImage: "circle.fill").font(.caption.bold()).foregroundStyle(statusColor).padding(8).background(statusColor.opacity(0.09)).clipShape(RoundedRectangle(cornerRadius: 7))
                VStack(alignment: .leading, spacing: 7) {
                    Text(L("自动控制")).font(.caption).foregroundStyle(.secondary)
                    Toggle(isOn: Binding(get: { chat.automatic }, set: { model.setAutomatic(chat, enabled: $0) })) {
                        Text(!chat.controllable ? L("不可用") : chat.auto_connection == "waiting_global" ? L("等待启用") : chat.auto_connection == "failed" ? L("未连接") : chat.auto_pending == true ? L("连接中") : chat.automatic ? L("已开启") : L("已关闭")).font(.caption)
                    }.toggleStyle(.switch).controlSize(.small).disabled(locked || !chat.controllable)
                        .help(L(chat.capability_note ?? L("按额度暂停并自动续接；关闭不停止当前聊天")))
                    if chat.auto_connection == "waiting_global" { Text(L("等待启用全局自动控制")).font(.caption2).foregroundStyle(.secondary) }
                    if chat.auto_connection == "failed" {
                        Button(L("重试连接")) { model.setAutomatic(chat,enabled:true) }.disabled(locked)
                        if let reason=chat.auto_error { Text(L(reason)).font(.caption2).foregroundStyle(.orange).lineLimit(3) }
                    }
                }
            }.frame(width: 138, alignment: .leading)
            VStack(alignment: .leading, spacing: 10) {
                if !chat.controllable {
                    Label(L("仅显示目录"), systemImage: "eye").font(.callout).foregroundStyle(.secondary)
                    Text(L(chat.capability_note ?? L("此聊天没有后台自动执行通道"))).font(.caption).foregroundStyle(.secondary)
                } else {
                    Toggle(isOn: Binding(get: { chat.plan?.scheduled == true }, set: { model.savePlan(chat, enabled: $0) })) { Text(L(chat.plan?.label ?? L("未预约"))).font(.caption) }
                        .toggleStyle(.switch).controlSize(.small).disabled(locked || chat.plan?.state == "sending")
                        .help(L("额度恢复后执行一次；独立于自动控制开关"))
                    TextEditor(text: prompt).font(.body).scrollContentBackground(.hidden).padding(6).frame(height: 78)
                        .background(Color(nsColor: .textBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 6))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.2)))
                        .disabled(locked || chat.plan?.state == "sending").accessibilityLabel(L("%@：执行指令", String(describing: chat.name)))
                    HStack {
                        Button(chat.plan?.scheduled == true ? L("保存指令") : L("保存并预约")) { model.savePlan(chat, enabled: true) }.disabled(locked || chat.plan?.state == "sending")
                        Button(L("立刻执行")) { model.executeNow(chat) }.buttonStyle(.borderedProminent).disabled(locked || !chat.canExecute)
                    }
                    if let receipt = chat.immediate {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(L(receipt.label)).font(.caption.bold()).foregroundStyle(receipt.state == "sent" ? missionGreen : .secondary)
                            if let message = receipt.message { Text(L(message)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                            Text(L("发送标识 %@", String(describing: String(receipt.id.prefix(8))))).font(.caption2).foregroundStyle(.secondary)
                        }.accessibilityElement(children: .combine)
                    }
                    if let reason = chat.plan?.reason { Text(L(reason)).font(.caption).foregroundStyle(.orange) }
                    if chat.plan?.state == "needs_review" { Button(L("取消此预约")) { model.savePlan(chat, enabled: false) }.disabled(locked) }
                }
            }.frame(width: 310, alignment: .leading)
        }.padding(16).background(Color(nsColor: .controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

// Offline rendering path: never starts a host, polls quota or sends a message.
// Uses the same NSHostingController and views as the main application.
enum MissionPreview {
    static func render(fixture: String, output: String) throws {
        NativeLocalization.testLanguage = CommandLine.arguments.contains("--english") ? "en" : "zh"
        defer { NativeLocalization.testLanguage = nil }
        let state = try JSONDecoder().decode(MissionSnapshot.self, from: Data(contentsOf: URL(fileURLWithPath: fixture)))
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        let args=CommandLine.arguments
        let dark=args.contains("--dark")
        app.appearance=NSAppearance(named:dark ? .darkAqua : .aqua)
        let model = MissionModel()
        model.snapshot=state; model.connected=true; model.paused=state.control_paused
        model.language=args.contains("--english") ? "en" : "zh"
        model.theme=dark ? "dark" : "light"
        let controller:NSViewController
        if args.contains("--settings") { controller=NSHostingController(rootView:MissionSettings(model:model)) }
        else if args.contains("--menu-panel") { controller=NSHostingController(rootView:MissionMenuPanel(model:model,openWindow:{},openSettings:{},quit:{})) }
        else { controller=NSHostingController(rootView:MissionWindow(model:model,showSettings:{})) }
        let window=NSWindow(contentViewController:controller)
        window.appearance=app.appearance
        window.setContentSize(args.contains("--menu-panel") ? NSSize(width:400,height:570) : args.contains("--settings") ? NSSize(width:800,height:1100) : NSSize(width:1380,height:900))
        let view=controller.view
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.7))
        view.layoutSubtreeIfNeeded()
        guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else {
            throw NSError(domain: "NativePreview", code: 1, userInfo: [NSLocalizedDescriptionKey: L("无法创建原生视图位图")])
        }
        view.effectiveAppearance.performAsCurrentDrawingAppearance {
            view.cacheDisplay(in: view.bounds, to: bitmap)
        }
        guard let data = bitmap.representation(using: .png, properties: [:]) else {
            throw NSError(domain: "NativePreview", code: 2)
        }
        try data.write(to: URL(fileURLWithPath: output))
        func classes(_ view: NSView) -> [String] { [String(describing: type(of: view))] + view.subviews.flatMap { classes($0) } }
        let hierarchy = classes(view)
        precondition(!hierarchy.contains { $0.contains("WKWeb") || $0.contains("WebView") })
        let report: [String: Any] = ["nativeHosting": true, "webViewCount": 0, "fixtureChats": state.tasks.count, "renderedViews": hierarchy.count, "messagesSent": 0, "hostStarted": model.host != nil]
        print(String(data: try JSONSerialization.data(withJSONObject: report, options: .sortedKeys), encoding: .utf8)!)
        window.close()
    }
}
