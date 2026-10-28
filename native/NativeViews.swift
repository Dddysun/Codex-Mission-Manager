import AppKit
import SwiftUI

enum MissionPalette {
    static func color(_ hex:String) -> NSColor {
        let value=UInt32(hex,radix:16) ?? 0
        return NSColor(srgbRed:Double((value>>16)&255)/255,green:Double((value>>8)&255)/255,blue:Double(value&255)/255,alpha:1)
    }
    static func dynamic(_ light:String,_ dark:String) -> Color {
        Color(nsColor:NSColor(name:nil) { appearance in color(appearance.bestMatch(from:[.darkAqua,.aqua]) == .darkAqua ? dark : light) })
    }
    static func accent(_ choice:MissionAccent) -> Color {dynamic(choice.lightHex,choice.darkHex)}
    static func ink(_ choice:MissionAccent) -> Color {dynamic(choice.lightInkHex,choice.darkInkHex)}
    static func selected(_ choice:MissionAccent) -> Color {dynamic(choice.lightSelectedHex,choice.darkSelectedHex)}
    static func foreground(_ choice:MissionAccent) -> Color {dynamic(choice.lightTextHex,choice.darkTextHex)}
    static func content(_ choice:MissionAccent) -> Color {dynamic(choice == .yellow ? "8E721E" : choice.lightHex,choice.darkHex)}
}
private let missionCanvas = Color(nsColor: .windowBackgroundColor)

struct MissionPrimaryButtonStyle: ButtonStyle {
    let fill:Color
    let text:Color
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration:Configuration) -> some View {
        configuration.label.padding(.horizontal,10).padding(.vertical,4)
            .foregroundStyle(text.opacity(enabled ? 1 : 0.6))
            .background(fill.opacity(enabled ? (configuration.isPressed ? 0.82 : 1) : 0.28))
            .clipShape(RoundedRectangle(cornerRadius:6))
    }
}

struct MissionWindow: View {
    @ObservedObject var model: MissionModel
    var showSettings: () -> Void
    @State private var section: String
    @State private var search = ""
    @State private var filter = "all"
    @State private var activityFilter: MissionActivityFilter = .all
    @State private var selected: String?

    init(model: MissionModel, showSettings: @escaping () -> Void, initialSection: String = "tasks") {
        self.model=model;self.showSettings=showSettings
        _section=State(initialValue:initialSection == "events" ? "events" : "tasks")
    }

    var chats: [MissionChat] {
        (model.snapshot?.codexTasks ?? []).filter { chat in
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
                    }.font(.callout).padding(12).background(model.tint.opacity(0.12))
                }
                if section == "tasks" { taskPage }
                else if section == "events" { eventsPage }
                else { rulesPage }
            }.frame(minWidth: 860, maxWidth: .infinity, maxHeight: .infinity).background(missionCanvas)
        }
        .tint(model.tint)
        .preferredColorScheme(model.colorScheme)
        .sheet(isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } })) {
            if let chat = model.snapshot?.codexTasks.first(where: { $0.key == selected }) {
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
        }.padding(22).foregroundStyle(.white.opacity(0.88)).frame(maxHeight: .infinity).background(model.sidebarInk)
    }
    func nav(_ title: String, icon: String, key: String) -> some View {
        Button { section = key } label: {
            HStack { Label(title, systemImage: icon); Spacer(); if key == "tasks" { Text("\(model.snapshot?.codexTasks.count ?? 0)").font(.caption).monospacedDigit() } }
                .padding(12).background(section == key ? model.selectedNavigation : .clear).clipShape(RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.plain)
    }
    var usage: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text(L("当前额度")).font(.subheadline.bold()); Spacer(); Text(model.snapshot?.usage?.account?.subscription ?? L("待识别")).font(.caption.bold()).padding(.horizontal, 8).padding(.vertical, 4).background(.white.opacity(0.12)).clipShape(Capsule()) }
            ForEach(model.snapshot?.usage?.visibleWindows ?? []) { window in
                quota(window.title, value: window.value)
            }
            if let note=model.snapshot?.usage?.availabilityNote {
                Text(note).font(.caption).foregroundStyle(.white.opacity(0.75)).fixedSize(horizontal:false,vertical:true)
            } else if let note=model.snapshot?.usage?.missingWindowNote {
                Text(note).font(.caption2).foregroundStyle(.white.opacity(0.58)).fixedSize(horizontal:false,vertical:true)
            } else if model.snapshot?.usage == nil {
                Text(L("额度待同步")).font(.caption).foregroundStyle(.white.opacity(0.65))
            }
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
            if let remaining=value?.validRemaining {
                ProgressView(value: remaining, total: 100)
                    .tint(remaining <= 10 ? .orange : model.tint)
                    .accessibilityLabel(title).accessibilityValue(L("剩余 %@%", String(describing: remaining)))
            }
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
                statistic(L("聊天目录"), count: model.snapshot?.codexTasks.count ?? 0)
                statistic(L("正在执行"), count: model.snapshot?.codexTasks.filter { $0.active }.count ?? 0)
                statistic(L("等待恢复 / 预约"), count: model.snapshot?.codexTasks.filter { $0.waiting || $0.plan?.scheduled == true }.count ?? 0)
                statistic(L("需要留意"), count: model.snapshot?.codexTasks.filter { $0.attention }.count ?? 0)
            }.padding(.vertical, 14).background(Color(nsColor: .controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius: 10))
            HStack {
                Label(L("Codex 任务"),systemImage:"terminal").font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
                Picker(L("筛选"), selection: $filter) { Text(L("全部状态")).tag("all"); Text(L("等待恢复")).tag("waiting"); Text(L("已预约")).tag("scheduled"); Text(L("需留意")).tag("attention") }.frame(width: 190)
                Spacer()
                TextField(L("搜索聊天名称或 ID"), text: $search).textFieldStyle(.roundedBorder).frame(maxWidth: 240)
            }
            ScrollView {
                LazyVStack(spacing: 12) {
                    if chats.isEmpty { ContentUnavailableView(model.snapshot == nil ? L("正在读取聊天目录") : L("没有匹配的聊天"), systemImage: "terminal", description: Text(L("Codex 任务目录将在后台连接后更新。"))) }
                    ForEach(chats, id: \.key) { chat in MissionChatRow(model: model, chat: chat, showDetail: { selected = chat.key }) }
                }.padding(.trailing, 4)
            }
            HStack {
                Text(L("显示 %@ / %@ 个 Codex 任务", String(describing: chats.count), String(describing: model.snapshot?.codexTasks.count ?? 0)))
                Spacer()
                Text(model.snapshot?.catalog?.local_error == nil ? L("界面每 %@ 秒同步",String(format:"%g",model.snapshot?.rules?.values["ui_poll_seconds"].map(Double.init) ?? model.snapshot?.ui_poll_seconds ?? 5)) : L("本机目录待重连，显示上次记录"))
            }.font(.caption2).foregroundStyle(.secondary)
        }.padding(26)
    }
    func statistic(_ title: String, count: Int) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(title).font(.caption).foregroundStyle(.secondary); Text("\(count)").font(.system(size: 26, weight: .semibold)).monospacedDigit() }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
    }
    var eventsPage: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(L("操作记录")).font(.largeTitle.bold())
            HStack(spacing: 18) {
                Text(L("查看最近 200 条额度恢复、任务控制与指令发送记录。")).foregroundStyle(.secondary)
                Spacer(minLength: 12)
                Picker(L("记录来源"), selection: $activityFilter) {
                    ForEach(MissionActivityFilter.allCases) { choice in Text(choice.title).tag(choice) }
                }.pickerStyle(.menu).labelsHidden().frame(width: 200).accessibilityLabel(L("记录来源"))
            }
            List(activityEvents) { event in
                HStack(alignment: .top, spacing: 18) {
                    Image(systemName: event.isQuotaRestored ? "arrow.clockwise.circle" : "clock").foregroundStyle(model.tint)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(L(event.label)).fontWeight(.semibold)
                        Text(event.scopeTitle)
                        if event.isQuotaRestored {
                            ForEach(Array(event.restorationLines.enumerated()),id:\.offset) { _,line in
                                Text(line).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                            }
                        } else {
                            if let recovery=event.detail?.recoveryNote {Text(recovery).font(.callout).foregroundStyle(.secondary)}
                            if let reason = event.detail?.reason { Text(L(reason)).font(.callout).foregroundStyle(.secondary).textSelection(.enabled) }
                        }
                    }
                    Spacer()
                    Text(missionTime(event.created)).font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }.padding(.vertical, 10)
            }.listStyle(.inset).overlay {
                if activityEvents.isEmpty { Text(L("此筛选条件下暂无记录")).foregroundStyle(.secondary) }
            }
        }.padding(26)
    }
    var activityEvents: [MissionEvent] { activityFilter.apply(to: model.snapshot?.events ?? []) }
    var rulesPage: some View { MissionRulesEditor(model:model) }
    func rule(_ title: String, _ text: String) -> some View {
        GroupBox { VStack(alignment: .leading, spacing: 10) { Text(title).font(.headline); Text(text).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }.padding(12).frame(maxWidth: .infinity, alignment: .leading) }
    }
    func detail(_ chat: MissionChat) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack { Text(chat.name).font(.title2.bold()); Spacer(); Button(L("完成")) { selected = nil }.keyboardShortcut(.defaultAction) }
            Text(L(chat.status)).font(.headline)
            Text(chat.execution_stage?.text ?? L("暂未读取到公开执行进展")).textSelection(.enabled)
            Divider()
            Text(L("来源：%@", chat.sourceTitle))
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
    var canSchedule: Bool { model.snapshot?.usage?.canSchedule == true }
    var quotaPermitsImmediate: Bool { model.snapshot?.usage?.permitsImmediate(minimum:model.snapshot?.policy.resume ?? 20) ?? true }
    var scheduleTarget: MissionQuotaWindow? {
        if let plan=chat.plan, ["armed","sending","needs_review"].contains(plan.state), let reset=plan.armed_window_reset {
            let minutes=plan.armed_window_minutes ?? 300
            return MissionQuotaWindow(id:"plan",kind:minutes == 300 ? "five_hour" : minutes == 10080 ? "weekly" : "custom",minutes:minutes,remaining:nil,reset:reset)
        }
        return model.snapshot?.usage?.scheduleWindow
    }
    var statusColor: Color { !model.connected ? .secondary : chat.attention ? .orange : chat.active ? MissionPalette.accent(.green) : chat.waiting ? .orange : .secondary }
    var autoLabel: String {
        !chat.controllable ? L("不可用") : chat.auto_connection == "waiting_global" ? L("等待启用") : chat.auto_connection == "failed" ? L("未连接") : chat.auto_pending == true ? L("连接中") : chat.automatic ? L("已开启") : L("已关闭")
    }
    var body: some View {
        HStack(alignment:.top,spacing:24) {
            VStack(alignment:.leading,spacing:12) {
                HStack(alignment:.top,spacing:10) {
                    Image(systemName:"terminal").foregroundStyle(model.tint).padding(.top,2)
                    VStack(alignment:.leading,spacing:5) {
                        Button(action:showDetail) { Text(chat.name).font(.headline).multilineTextAlignment(.leading) }.buttonStyle(.plain)
                        Text("\(chat.sourceTitle) / \(String(chat.id.prefix(8)))").font(.system(.caption,design:.monospaced)).foregroundStyle(.secondary)
                    }.frame(maxWidth:.infinity,alignment:.leading)
                    Label(model.connected ? chat.status : L("状态待同步"),systemImage:"circle.fill")
                        .font(.caption.bold()).foregroundStyle(statusColor).padding(8).background(statusColor.opacity(0.09)).clipShape(RoundedRectangle(cornerRadius:7))
                }
                VStack(alignment:.leading,spacing:7) {
                    Text(L("当前执行阶段")).font(.caption.bold()).foregroundStyle(MissionPalette.content(model.accentChoice))
                    if let stamp=chat.execution_stage?.updated_at {Text(missionTime(stamp)).font(.caption2).foregroundStyle(.secondary)}
                    Text(chat.execution_stage?.text ?? L("暂未读取到执行进展")).font(.callout).foregroundStyle(.secondary).lineLimit(5).textSelection(.enabled)
                }.padding(12).frame(maxWidth:.infinity,alignment:.leading).background(model.tint.opacity(0.05)).clipShape(RoundedRectangle(cornerRadius:8))
            }.frame(maxWidth:.infinity,alignment:.leading)
            VStack(alignment:.leading,spacing:10) {
                HStack(alignment:.center,spacing:10) {
                    Text(L("额度恢复后执行 · 一次性")).font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength:4)
                    VStack(alignment:.trailing,spacing:4) {
                        Text(L("自动控制")).font(.caption2).foregroundStyle(.secondary)
                        Toggle(autoLabel,isOn:Binding(get:{chat.automatic},set:{model.setAutomatic(chat,enabled:$0)}))
                            .font(.caption).toggleStyle(.switch).controlSize(.small).disabled(locked || !chat.controllable)
                            .help(L("按额度暂停并自动续接；关闭不停止当前任务"))
                    }
                }
                if chat.auto_connection == "waiting_global" {Text(L("等待启用全局自动控制")).font(.caption2).foregroundStyle(.secondary)}
                if chat.auto_connection == "failed" {
                    HStack {Text(L(chat.auto_error ?? L("Codex 客户端连接尚未通过核验。"))).font(.caption).foregroundStyle(.orange);Spacer();Button(L("重试连接")){model.setAutomatic(chat,enabled:true)}}
                }
                Toggle(isOn:Binding(get:{chat.plan?.scheduled == true},set:{model.savePlan(chat,enabled:$0)})) {Text(L(chat.plan?.label ?? L("未预约"))).font(.caption)}
                    .toggleStyle(.switch).controlSize(.small).disabled(locked || !chat.controllable || chat.plan?.state == "sending" || (!canSchedule && chat.plan?.scheduled != true))
                    .help(L("额度恢复后执行一次；独立于自动控制开关"))
                if let target=scheduleTarget {
                    HStack {Text(L("预约窗口：%@",target.title));Spacer();Text(L("刷新时间 %@",missionTime(target.reset)))}.font(.caption2).foregroundStyle(.secondary)
                }
                MissionPromptEditor(model:model,chat:chat,editable:!locked && chat.controllable && chat.plan?.state != "sending")
                    .frame(height:90).background(Color(nsColor:.textBackgroundColor)).clipShape(RoundedRectangle(cornerRadius:6))
                    .overlay(RoundedRectangle(cornerRadius:6).stroke(Color.secondary.opacity(0.2)))
                    .accessibilityLabel(L("%@：执行指令",chat.name))
                HStack {
                    Button(chat.plan?.scheduled == true ? L("保存指令") : L("保存并预约")){model.savePlan(chat,enabled:true)}.disabled(locked || !chat.controllable || chat.plan?.state == "sending" || !canSchedule)
                    Button(L("立刻执行")){model.executeNow(chat)}.buttonStyle(MissionPrimaryButtonStyle(fill:model.tint,text:model.accentForeground)).disabled(locked || !chat.canExecute || !quotaPermitsImmediate)
                }
                if !chat.controllable {Text(L("Codex 客户端连接尚未通过核验，暂不能发送指令。")).font(.caption).foregroundStyle(.secondary)}
                else if !canSchedule {Text(model.snapshot?.usage?.schedulingUnavailableNote ?? L("额度信息不完整，自动发送暂不可用")).font(.caption).foregroundStyle(.secondary)}
                if let receipt=chat.immediate {
                    VStack(alignment:.leading,spacing:4) {
                        Text(L(receipt.label)).font(.caption.bold()).foregroundStyle(receipt.state == "sent" ? MissionPalette.accent(.green) : .secondary)
                        if let message=receipt.message {Text(L(message)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)}
                        Text(L("发送标识 %@",String(receipt.id.prefix(8)))).font(.caption2).foregroundStyle(.secondary)
                    }.accessibilityElement(children:.combine)
                }
                if let reason=chat.plan?.reason {Text(L(reason)).font(.caption).foregroundStyle(.orange)}
                if chat.plan?.state == "needs_review" {Button(L("取消此预约")){model.savePlan(chat,enabled:false)}.disabled(locked)}
            }.frame(maxWidth:.infinity,alignment:.leading)
        }.padding(18).background(Color(nsColor:.controlBackgroundColor)).clipShape(RoundedRectangle(cornerRadius:10))
    }
}

struct MissionRulesEditor: View {
    @ObservedObject var model: MissionModel
    var current: MissionRules? {model.snapshot?.rules}
    var text: [String:String] {model.rulesDraftRevision == nil ? (current?.values.mapValues(String.init) ?? [:]) : model.rulesDraft}
    var validation: (values:[String:Int]?,error:String?) {MissionRuleFields.validation(text,remoteBounds:current?.bounds)}
    var body: some View {
        ScrollView {
            VStack(alignment:.leading,spacing:22) {
                VStack(alignment:.leading,spacing:8) {
                    Text(L("运行规则")).font(.largeTitle.bold())
                    Text(L("调整任务管家的控制阈值与检查间隔。服务额度与刷新时间由官方返回，不能在此修改。")).foregroundStyle(.secondary)
                }
                GroupBox {
                    VStack(alignment:.leading,spacing:16) {
                        ForEach(MissionRuleFields.keys,id:\.self) { key in field(key) }
                        Divider()
                        Text(L("恢复阈值至少高于暂停阈值 5%；临近阈值采集不能慢于正常采集。")).font(.caption).foregroundStyle(.secondary)
                        if let current, let base=model.rulesDraftRevision, base != current.revision {
                            Label(L("规则已在其他界面更新。草稿保留，保存前请重新核对。"),systemImage:"exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                        }
                        if model.rulesDraftRevision != nil, let error=validation.error {Text(error).font(.callout).foregroundStyle(.orange)}
                        if !model.rulesStatus.isEmpty {Text(L(model.rulesStatus)).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)}
                        HStack {
                            Button(model.rulesSaving ? L("正在保存…") : L("保存规则")){Task {await model.saveRules()}}
                                .buttonStyle(MissionPrimaryButtonStyle(fill:model.tint,text:model.accentForeground))
                                .disabled(!model.connected || current == nil || model.rulesSaving || model.busy || model.rulesDraftRevision == nil || validation.values == nil)
                            Button(L("撤销更改")){model.discardRulesDraft()}.disabled(model.rulesDraftRevision == nil || model.rulesSaving)
                            Spacer()
                            Text(current.map {L("规则版本 %@",String($0.revision))} ?? L("正在读取规则")).font(.caption).foregroundStyle(.secondary)
                        }
                        if current == nil {Text(L("后台尚未提供可编辑规则；已停止规则提交。")).font(.caption).foregroundStyle(.secondary)}
                    }.padding(14)
                }
                GroupBox {
                    VStack(alignment:.leading,spacing:12) {
                        Label(L("官方额度与刷新"),systemImage:"clock.arrow.circlepath").font(.headline)
                        ForEach(model.snapshot?.usage?.visibleWindows ?? []) { window in
                            HStack {Text(window.title);Spacer();Text(window.remaining.map {String(format:"%.1f%%",$0)} ?? L("未提供"));Text(window.reset.map {missionTime($0)} ?? L("刷新时间未提供")).foregroundStyle(.secondary)}.font(.callout)
                        }
                        if model.snapshot?.usage?.visibleWindows.isEmpty != false {Text(L("官方额度窗口尚未提供。")).foregroundStyle(.secondary)}
                        Text(L("这些额度和时间仅供读取；修改任务管家规则不会改变官方限额。")).font(.caption).foregroundStyle(.secondary)
                        Divider()
                        MissionResetCreditDetails(credits:model.snapshot?.usage?.reset_credits)
                    }.padding(14).frame(maxWidth:.infinity,alignment:.leading)
                }
                GroupBox {
                    VStack(alignment:.leading,spacing:10) {
                        Text(L("任务控制行为")).font(.headline)
                        Text(L("暂停和续接前核对账号、原任务、当前回合及服务许可。手动输入与审批优先；状态不明确时不重复发送。"))
                        Text(L("预约在核验额度恢复后执行一次。关闭全局自动控制会停止预约发送；保存指令不会立即执行。"))
                        Text(L("采集间隔从每轮完成后计算；处理耗时另计。界面刷新只读取后台缓存。"))
                    }.foregroundStyle(.secondary).padding(14).frame(maxWidth:.infinity,alignment:.leading)
                }
            }.padding(26).frame(maxWidth:960,alignment:.leading)
        }.frame(maxWidth:.infinity,alignment:.leading).background(missionCanvas).foregroundStyle(.primary).preferredColorScheme(model.colorScheme).tint(model.tint)
    }
    func field(_ key:String) -> some View {
        let bound=MissionRuleFields.bounds[key]!
        let minimum=max(bound.lowerBound,current?.bounds?[key]?.min ?? bound.lowerBound)
        let maximum=min(bound.upperBound,current?.bounds?[key]?.max ?? bound.upperBound)
        return HStack(spacing:18) {
            VStack(alignment:.leading,spacing:5) {
                Text(MissionRuleFields.title(key)).font(.headline)
                Text(L("允许范围 %@–%@",String(minimum),String(maximum))).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            TextField("",text:Binding(get:{text[key] ?? ""},set:{model.editRule(key,text:$0)}))
                .textFieldStyle(.roundedBorder).multilineTextAlignment(.trailing).frame(width:100)
                .disabled(!model.connected || current == nil || model.rulesSaving)
                .accessibilityLabel(MissionRuleFields.title(key))
        }
    }
}

struct MissionResetCreditDetails: View {
    let credits: MissionResetCredits?
    var body: some View {
        VStack(alignment:.leading,spacing:9) {
            HStack {Text(L("额度重置权益")).font(.headline);Spacer();Text(L("可用次数：%@",credits?.displayCount ?? L("未提供"))).font(.callout)}
            if let credits, credits.supported == true {
                ForEach(Array((credits.credits ?? []).enumerated()),id:\.offset) { _,credit in
                    VStack(alignment:.leading,spacing:4) {
                        Text(credit.displayTitle).font(.callout.weight(.medium))
                        if let description=credit.description,!description.isEmpty {Text(description).font(.caption).foregroundStyle(.secondary)}
                        HStack {
                            if let status=credit.status {Text(L("状态：%@",status))}
                            if let expires=credit.expiresAt {Text(L("有效期至 %@",missionTime(expires)))}
                        }.font(.caption).foregroundStyle(.secondary)
                    }
                }
            } else {Text(L("服务未提供可核实的重置权益，不能推断为零次或无限次。")).font(.caption).foregroundStyle(.secondary)}
            Text(L("仅展示服务返回的权益，不自动兑换；权益次数不会作为额度已恢复的证明。")).font(.caption).foregroundStyle(.secondary)
        }
    }
}

// NSTextView owns composition and selection. SwiftUI polling only proposes an
// external string; it cannot rewrite an active editor or an unsaved local draft.
final class MissionPromptTextCoordinator: NSObject, NSTextViewDelegate {
    var applying=false
    var desiredEditable=true
    var onEdit: (String)->Void = {_ in}
    func update(_ view:NSTextView,incoming:String,hasDraft:Bool,editable:Bool) {
        desiredEditable=editable
        let marked=view.hasMarkedText()
        if !marked, view.isEditable != editable {view.isEditable=editable}
        let editing=view.window?.firstResponder === view
        guard MissionPromptSynchronization.shouldApply(current:view.string,incoming:incoming,editing:editing,marked:marked,hasDraft:hasDraft) else {return}
        let selected=view.selectedRange()
        applying=true
        view.string=incoming
        view.setSelectedRange(MissionPromptSynchronization.selection(selected,utf16Length:(incoming as NSString).length))
        applying=false
    }
    func textDidChange(_ notification:Notification) {
        guard !applying, let view=notification.object as? NSTextView else{return}
        onEdit(view.string)
        if !view.hasMarkedText(), view.isEditable != desiredEditable {view.isEditable=desiredEditable}
    }
}
struct MissionPromptEditor: NSViewRepresentable {
    @ObservedObject var model: MissionModel
    let chat: MissionChat
    let editable: Bool
    func makeCoordinator() -> MissionPromptTextCoordinator {MissionPromptTextCoordinator()}
    func makeNSView(context:Context) -> NSScrollView {
        let scroll=NSScrollView()
        scroll.hasVerticalScroller=true;scroll.hasHorizontalScroller=false;scroll.autohidesScrollers=true;scroll.drawsBackground=false;scroll.borderType = .noBorder
        let view=NSTextView(frame:NSRect(x:0,y:0,width:400,height:90))
        view.isRichText=false;view.importsGraphics=false;view.allowsUndo=true;view.isVerticallyResizable=true;view.isHorizontallyResizable=false
        view.minSize=NSSize(width:0,height:90);view.maxSize=NSSize(width:CGFloat.greatestFiniteMagnitude,height:CGFloat.greatestFiniteMagnitude)
        view.autoresizingMask=[.width];view.textContainer?.widthTracksTextView=true
        view.textContainer?.containerSize=NSSize(width:0,height:CGFloat.greatestFiniteMagnitude)
        view.textContainerInset=NSSize(width:6,height:6);view.font = .systemFont(ofSize:13);view.textColor = .labelColor;view.drawsBackground=false
        view.isAutomaticQuoteSubstitutionEnabled=false;view.isAutomaticDashSubstitutionEnabled=false;view.isAutomaticSpellingCorrectionEnabled=false
        view.string=model.drafts[chat.key]?.text ?? chat.plan?.prompt ?? L("继续任务")
        view.delegate=context.coordinator;scroll.documentView=view
        return scroll
    }
    func updateNSView(_ scroll:NSScrollView,context:Context) {
        guard let view=scroll.documentView as? NSTextView else{return}
        context.coordinator.onEdit={ [weak model] text in model?.editPrompt(chat,text:text) }
        context.coordinator.update(view,incoming:model.drafts[chat.key]?.text ?? chat.plan?.prompt ?? L("继续任务"),hasDraft:model.drafts[chat.key] != nil,editable:editable)
    }
}

enum MissionPromptEditorChecks {
    static func run() -> [String:Any] {
        let view=NSTextView(frame:NSRect(x:0,y:0,width:400,height:90))
        view.string="原有指令";view.setSelectedRange(NSRange(location:4,length:0))
        let coordinator=MissionPromptTextCoordinator()
        view.delegate=coordinator
        view.setMarkedText("中文输入",selectedRange:NSRange(location:2,length:0),replacementRange:NSRange(location:NSNotFound,length:0))
        let composing=view.string, selection=view.selectedRange()
        precondition(view.hasMarkedText(),"Native marked-text fixture must create a composition")
        for _ in 0..<5 {coordinator.update(view,incoming:"轮询返回的旧指令",hasDraft:false,editable:true)}
        precondition(view.hasMarkedText() && view.string == composing && view.selectedRange() == selection,"Polling must preserve native composition and caret")
        view.unmarkText()
        coordinator.update(view,incoming:"服务器旧指令",hasDraft:true,editable:true)
        precondition(view.string == composing,"A local draft must survive a refresh after composition commits")
        return ["nativeTextView":true,"markedTextPreserved":true,"selectionPreserved":true,"draftPreserved":true,"hostStarted":false,"messagesSent":0,"privatePreferencesLoaded":false]
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
        if let index=args.firstIndex(of:"--accent"), args.count>index+1, MissionAccent(rawValue:args[index+1]) != nil {model.accent=args[index+1]} else {model.accent="green"}
        model.snapshot=state; model.connected=true; model.paused=state.control_paused
        model.language=args.contains("--english") ? "en" : "zh"
        model.theme=dark ? "dark" : "light"
        let controller:NSViewController
        if args.contains("--activity") || args.contains("--activity-preview") {controller=NSHostingController(rootView:MissionWindow(model:model,showSettings:{},initialSection:"events"))}
        else if args.contains("--rules") {controller=NSHostingController(rootView:MissionRulesEditor(model:model))}
        else if args.contains("--settings") { controller=NSHostingController(rootView:MissionSettings(model:model)) }
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
        let previewView=args.contains("--activity") || args.contains("--activity-preview") ? "activity" : args.contains("--rules") ? "rules" : args.contains("--settings") ? "settings" : args.contains("--menu-panel") ? "menu" : "home"
        let report: [String: Any] = ["nativeHosting": true, "webViewCount": 0, "fixtureChats": state.codexTasks.count, "sourceChats":state.tasks.count, "accent":model.accent, "rulesEditable":state.rules != nil, "renderedViews": hierarchy.count, "messagesSent": 0, "hostStarted": model.host != nil,"privatePreferencesLoaded":false,"view":previewView,"language":model.language,"theme":model.theme]
        print(String(data: try JSONSerialization.data(withJSONObject: report, options: .sortedKeys), encoding: .utf8)!)
        window.close()
    }
}
