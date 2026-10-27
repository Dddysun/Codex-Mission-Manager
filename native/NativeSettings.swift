import AppKit
import SwiftUI

struct MissionSettings: View {
    @ObservedObject var model: MissionModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(L("设置")).font(.largeTitle.bold())
                    Text(L("管理外观、后台运行与系统权限。")).foregroundStyle(.secondary)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 16) {
                        Label(L("外观与语言"), systemImage: "paintpalette").font(.headline)
                        HStack { Text(L("语言")); Spacer(); languagePicker.frame(width: 180) }
                        HStack { Text(L("外观")); Spacer(); themePicker.frame(width: 270) }
                        HStack { Text(L("主题色")); Spacer(); accentPicker.frame(width:360) }
                    }.padding(14)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Label(L("客户端连接"), systemImage: "network").font(.headline)
                        Text(L(model.client)).foregroundStyle(.secondary)
                        HStack {
                            Label(model.connected ? L("后台已连接") : L("后台未连接"), systemImage:model.connected ? "checkmark.circle.fill" : "exclamationmark.circle").foregroundStyle(model.connected ? Color.green : .orange)
                            Spacer()
                            Button(L("重新检查")) { model.refresh(); Task { await model.refreshControl() } }
                            if model.host == nil { Button(L("重新连接")) { model.startHost() } }
                        }
                        Text(L("关闭窗口后，任务管家继续在菜单栏运行。")).font(.caption).foregroundStyle(.secondary)
                    }.padding(14)
                }
                GroupBox {
                    VStack(spacing: 0) {
                        permission(title:L("登录时启动"), icon:"power", description:L("登录 Mac 后自动启动任务管家。"), status:model.login, isOn:Binding(get:{model.loginEnabled},set:{ if $0 { model.registerLogin() } else { model.unregisterLogin() } }), destination:"login")
                        Divider().padding(.leading, 46)
                        permission(title:L("任务通知"), icon:"bell", description:L("通知暂停、续接、发送失败及需要处理的异常。"), status:model.notificationsDenied ? L("通知已被系统关闭，请在系统设置中允许。") : model.notificationsEnabled ? L("通知已启用") : L("通知已关闭"), isOn:Binding(get:{model.notificationsEnabled},set:{model.setNotifications($0)}), destination:"notifications")
                        Divider().padding(.leading, 46)
                        permission(title:L("保持后台运行"), icon:"moon.zzz", description:L("防止空闲睡眠，允许屏幕关闭。此设置不保证合盖运行。"), status:model.awake ? L("已保持系统清醒") : L("未启用防睡眠保护"), isOn:Binding(get:{model.awake},set:{model.setAwake($0)}), destination:"battery")
                    }.padding(8)
                }
                GroupBox {
                    VStack(spacing: 0) {
                        permission(title:L("合盖运行辅助服务"), icon:"laptopcomputer", description:L("为无外接显示器的合盖运行提供电源管理支持。"), status:model.signed ? model.helper : L("当前版本暂未提供此功能。"), isOn:Binding(get:{model.helperEnabled},set:{if $0 {model.registerPower()} else {model.removePower()}}), destination:"login", available:model.signed)
                        Divider().padding(.leading, 46)
                        permission(title:L("合盖运行"), icon:"lock.laptopcomputer", description:L("需先启用辅助服务。开启后按 Control–Command–Q 锁屏。"), status:model.waitingForLock ? L("等待锁屏") : model.closedLidEnabled ? L("已启用") : L("未启用"), isOn:Binding(get:{model.waitingForLock || model.closedLidEnabled},set:{if $0 {model.prepareClosedLid()} else {model.disableClosedLid()}}), destination:"battery", available:model.helperEnabled)
                        HStack {
                            Text(L("允许使用电池")).font(.callout)
                            Spacer()
                            Toggle(L("允许使用电池"), isOn:$model.allowBattery).labelsHidden().toggleStyle(.switch).disabled(!model.helperEnabled)
                        }.padding(.horizontal, 20).padding(.bottom, 14)
                        Text(L("电量不高于 20% 或出现严重热压力时停止合盖保持。")).font(.caption).foregroundStyle(.secondary).padding(.bottom, 12)
                    }.padding(8)
                }
                HStack { Image(systemName:"bolt"); Text(L(model.power)).font(.caption); Spacer(); Text(L("最近检查：%@",model.checked)).font(.caption) }.foregroundStyle(.secondary)
                if !model.error.isEmpty { Label(L(model.error),systemImage:"exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled) }
            }.padding(28)
        }.frame(minWidth:740,minHeight:620).background(Color(nsColor:.windowBackgroundColor)).preferredColorScheme(model.colorScheme).tint(model.tint)
    }
    var languagePicker: some View {
        Picker(L("语言"),selection:$model.language) { Text(L("简体中文")).tag("zh"); Text("English").tag("en") }.labelsHidden().pickerStyle(.segmented)
    }
    var themePicker: some View {
        Picker(L("外观"),selection:$model.theme) { Text(L("跟随系统")).tag("system"); Text(L("浅色")).tag("light"); Text(L("深色")).tag("dark") }.labelsHidden().pickerStyle(.segmented)
    }
    var accentPicker: some View {
        Picker(L("主题色"),selection:$model.accent) {
            ForEach(MissionAccent.allCases,id:\.rawValue) { choice in
                Label {Text(choice.title)} icon: {Image(systemName:"circle.fill").foregroundStyle(MissionPalette.accent(choice))}.tag(choice.rawValue)
            }
        }.labelsHidden().pickerStyle(.segmented)
    }
    func permission(title:String,icon:String,description:String,status:String,isOn:Binding<Bool>,destination:String,available:Bool=true) -> some View {
        HStack(alignment:.center,spacing:14) {
            Image(systemName:icon).font(.title3).foregroundStyle(.secondary).frame(width:28)
            VStack(alignment:.leading,spacing:5) {
                Text(L(title)).font(.headline)
                Text(L(description)).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                Text(L(status)).font(.caption).foregroundStyle(.secondary)
            }.frame(maxWidth:.infinity,alignment:.leading)
            Toggle(L(title),isOn:isOn).labelsHidden().toggleStyle(.switch).disabled(!available).accessibilityLabel(L(title))
            Button { model.openSettings(destination) } label: { Image(systemName:"arrow.up.forward.square").font(.title3) }.buttonStyle(.borderless).help(L("打开系统设置")).accessibilityLabel(L("打开系统设置"))
        }.padding(14)
    }
}
