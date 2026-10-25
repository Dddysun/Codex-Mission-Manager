import SwiftUI

struct MissionMenuPanel: View {
    @ObservedObject var model: MissionModel
    var openWindow:()->Void
    var openSettings:()->Void
    var quit:()->Void
    @State private var showResults=false
    var body: some View {
        ScrollView {
        VStack(alignment:.leading,spacing:16) {
            HStack {
                Label(L("任务管家"),systemImage:"checkmark.shield").font(.headline)
                Spacer()
                Text(model.snapshot?.usage?.account?.subscription ?? L("待识别")).font(.caption).foregroundStyle(.secondary)
            }
            VStack(alignment:.leading,spacing:14) {
                ForEach(model.snapshot?.usage?.visibleWindows ?? []) { window in
                    meter(window.title,quota:window.value)
                }
                if let note=model.snapshot?.usage?.availabilityNote {
                    Text(note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                } else if let note=model.snapshot?.usage?.missingWindowNote {
                    Text(note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                }
                if !model.connected || model.snapshot?.usage?.stale != false { Label(L("额度待同步"),systemImage:"clock").font(.caption).foregroundStyle(.orange) }
            }
            HStack(spacing:8) {
                Button(model.paused ? L("恢复自动控制") : L("暂停自动控制")) { model.setGlobalAutomatic(model.paused) }.frame(maxWidth:.infinity)
                Button(L("暂停所有任务")) { model.pauseAllTasks() }.frame(maxWidth:.infinity)
                    .help(L("暂停允许接管的执行中任务，并关闭全局自动控制。手动暂停的任务需手动恢复。"))
            }.controlSize(.small).disabled(model.busy || !model.connected || model.snapshot?.bulk_pause?.state == "pending" || model.snapshot?.bulk_pause?.state == "processing")
            if let result=model.snapshot?.bulk_pause {
                HStack {
                    Text(L("暂停 %@ · 跳过 %@ · 待处理 %@",String(result.paused),String(result.skipped),String(result.failed))).font(.caption).foregroundStyle(result.failed>0 ? .orange : .secondary)
                    Spacer()
                    Button(L("查看结果")) { showResults=true }.font(.caption).buttonStyle(.plain)
                }
            }
            if !model.notice.isEmpty {
                Text(L(model.notice)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    .fixedSize(horizontal:false,vertical:true)
            }
            if !model.connectionError.isEmpty {
                Label(L(model.connectionError),systemImage:"exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
                    .fixedSize(horizontal:false,vertical:true)
            }
            Divider()
            Button(action:openWindow) { Label(L("打开任务管家"),systemImage:"macwindow").frame(maxWidth:.infinity,alignment:.leading) }.buttonStyle(.plain)
            Button(action:openSettings) { Label(L("设置"),systemImage:"gearshape").frame(maxWidth:.infinity,alignment:.leading) }.buttonStyle(.plain)
            HStack { Text(L("语言")).font(.callout); Spacer(); Picker(L("语言"),selection:$model.language) { Text(L("简体中文")).tag("zh"); Text("English").tag("en") }.labelsHidden().frame(width:180) }
            HStack { Text(L("外观")).font(.callout); Spacer(); Picker(L("外观"),selection:$model.theme) { Text(L("跟随系统")).tag("system"); Text(L("浅色")).tag("light"); Text(L("深色")).tag("dark") }.labelsHidden().frame(width:180) }
            Divider()
            HStack {
                Label(model.connected ? L("后台已连接") : L("后台未连接"),systemImage:model.connected ? "circle.fill" : "exclamationmark.circle").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(L("退出"),action:quit).buttonStyle(.plain).font(.caption)
            }
        }.padding(20).frame(maxWidth:.infinity,alignment:.leading)
        }.frame(width:400,height:570).background(Color(nsColor:.windowBackgroundColor)).preferredColorScheme(model.colorScheme)
        .sheet(isPresented:$showResults) {
            VStack(alignment:.leading,spacing:16) {
                HStack { Text(L("暂停所有任务")).font(.title2.bold()); Spacer(); Button(L("完成")) { showResults=false } }
                Text(L("暂停允许接管的执行中任务，并关闭全局自动控制。手动暂停的任务需手动恢复。")).font(.callout).foregroundStyle(.secondary)
                List(model.snapshot?.bulk_pause?.items ?? []) { item in
                    VStack(alignment:.leading,spacing:6) {
                        Text(model.snapshot?.tasks.first(where:{$0.id==item.thread_id})?.name ?? item.thread_id).fontWeight(.medium)
                        Text(L(item.state=="paused" ? "已暂停" : item.state=="skipped" ? "已跳过" : "暂停失败")).foregroundStyle(item.state=="failed" ? Color.orange : .secondary)
                        if let reason=item.reason { Text(L(reason)).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                    }.padding(.vertical,6)
                }.frame(height:260)
            }.padding(24).frame(width:540).preferredColorScheme(model.colorScheme)
        }
    }
    func meter(_ title:String,quota:MissionQuota?) -> some View {
        VStack(alignment:.leading,spacing:6) {
            HStack { Text(L(title)).font(.callout); Spacer(); Text(quota?.validRemaining.map { String(format:"%.1f%%",$0) } ?? L("未提供")).font(.callout.bold()).monospacedDigit() }
            if let remaining=quota?.validRemaining {
                ProgressView(value:remaining,total:100).tint(remaining<=10 ? .orange : .accentColor)
            }
            Text(quota?.reset.map { L("下次刷新 %@",missionTime($0)) } ?? L("刷新时间未提供")).font(.caption).foregroundStyle(.secondary)
        }
    }
}
