import Foundation
import IOKit.ps

// A narrow root service: no shell, arbitrary commands, file paths or user scripts.
final class PowerLease: NSObject, PowerHelperProtocol {
    private let queue = DispatchQueue(label: "mission.power.lease")
    private let journal = URL(fileURLWithPath: "/Library/Application Support/CodexMissionManager/PowerLease.json")
    private var active = false
    private var lastBeat = Date.distantPast
    private var allowBattery = false
    private var timer: DispatchSourceTimer?
    private var lastReason = "未启用"

    override init() {
        super.init()
        // A root-owned journal allows recovery after helper crashes/restarts.
        if let attrs = try? FileManager.default.attributesOfItem(atPath: journal.path),
           attrs[.ownerAccountID] as? Int == 0,
           let data = try? Data(contentsOf: journal),
           let record = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           record["changedFromFalse"] as? Bool == true {
            if HardwareState.sleepDisabled == true { _ = runCommand("/usr/bin/pmset", ["-a", "disablesleep", "0"]) }
            try? FileManager.default.removeItem(at: journal)
        }
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 5, repeating: 5)
        timer.setEventHandler { [weak self] in self?.watchdog() }
        timer.resume()
        self.timer = timer
    }

    private func value() -> NSDictionary {
        ["active": active, "reason": lastReason,
         "sleepDisabled": HardwareState.sleepDisabled.map { $0 ? "1" : "0" } ?? "unknown",
         "lidClosed": HardwareState.lidClosed.map { $0 ? "yes" : "no" } ?? "unknown"]
    }

    private func restore(_ reason: String) {
        guard active else { return }
        if HardwareState.sleepDisabled == true {
            let result = runCommand("/usr/bin/pmset", ["-a", "disablesleep", "0"])
            if result.0 != 0 || HardwareState.sleepDisabled != false {
                lastReason = "恢复失败，辅助服务将继续重试"
                return
            }
        }
        active = false
        lastReason = reason
        try? FileManager.default.removeItem(at: journal)
    }

    private func watchdog() {
        guard active else { return }
        let power = HardwareState.power()
        if Date().timeIntervalSince(lastBeat) > 45 { restore("后台失联，已恢复睡眠"); return }
        if !allowBattery && !power.ac { restore("已断开外接电源，已恢复睡眠"); return }
        if !power.ac && (power.battery ?? 0) <= 20 { restore("电池余量不足20%，已恢复睡眠"); return }
        let thermal = ProcessInfo.processInfo.thermalState
        if thermal == .serious || thermal == .critical { restore("系统热压力过高，已恢复睡眠"); return }
        if HardwareState.sleepDisabled != true { active = false; lastReason = "系统睡眠覆盖已改变，保护停止"; try? FileManager.default.removeItem(at: journal) }
    }

    func status(withReply reply: @escaping (NSDictionary) -> Void) { queue.async { reply(self.value()) } }
    func heartbeat(withReply reply: @escaping (NSDictionary) -> Void) {
        queue.async { self.lastBeat = Date(); self.watchdog(); reply(self.value()) }
    }
    func disable(withReply reply: @escaping (NSDictionary) -> Void) {
        queue.async { self.restore("已停用，原睡眠行为已恢复"); reply(self.value()) }
    }
    func enableClosedLid(onBattery: Bool, withReply reply: @escaping (NSDictionary) -> Void) {
        queue.async {
            if self.active { self.lastBeat = Date(); reply(self.value()); return }
            let power = HardwareState.power()
            guard power.ac || (onBattery && (power.battery ?? 0) > 20) else {
                self.lastReason = "需要稳定接电，或电池模式余量高于20%"; reply(self.value()); return
            }
            guard ProcessInfo.processInfo.thermalState != .serious && ProcessInfo.processInfo.thermalState != .critical else {
                self.lastReason = "热压力过高，未启用"; reply(self.value()); return
            }
            guard HardwareState.sleepDisabled == false else {
                self.lastReason = "系统覆盖状态未知或已被其他工具开启，未接管"; reply(self.value()); return
            }
            do {
                let folder = self.journal.deletingLastPathComponent()
                if FileManager.default.fileExists(atPath: folder.path) {
                    let attrs = try FileManager.default.attributesOfItem(atPath: folder.path)
                    guard attrs[.type] as? FileAttributeType == .typeDirectory,
                          attrs[.ownerAccountID] as? Int == 0,
                          (attrs[.posixPermissions] as? Int ?? 0o777) & 0o022 == 0 else { throw NSError(domain: "PowerLease", code: 1) }
                } else { try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700]) }
                let record = try JSONSerialization.data(withJSONObject: ["changedFromFalse": true, "created": Date().timeIntervalSince1970])
                try record.write(to: self.journal, options: .atomic)
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: self.journal.path)
                let result = runCommand("/usr/bin/pmset", ["-a", "disablesleep", "1"])
                self.active = HardwareState.sleepDisabled == true
                self.allowBattery = onBattery
                self.lastBeat = Date()
                self.lastReason = result.0 == 0 && self.active ? "合盖保持已生效；实机端到端验收另行记录" : "系统未应用合盖保持"
                if !self.active { try? FileManager.default.removeItem(at: self.journal) }
            } catch { self.lastReason = "无法安全记录恢复信息，未启用" }
            reply(self.value())
        }
    }
}

final class HelperDelegate: NSObject, NSXPCListenerDelegate {
    let lease = PowerLease()
    func listener(_ listener: NSXPCListener, shouldAcceptNewConnection connection: NSXPCConnection) -> Bool {
        guard MissionIdentity.releaseSigned, connection.effectiveUserIdentifier != 0 else { return false }
        connection.setCodeSigningRequirement(MissionIdentity.clientRequirement)
        connection.exportedInterface = NSXPCInterface(with: PowerHelperProtocol.self)
        connection.exportedObject = lease
        connection.resume()
        return true
    }
}

@main enum HelperMain {
    static func main() {
        if CommandLine.arguments.contains("--self-test") {
            print("power-helper: fixed command set; preview identity rejects all privileged clients")
            return
        }
        guard getuid() == 0, MissionIdentity.releaseSigned else { fputs("Power helper requires a release-signed approved system service.\n", stderr); exit(78) }
        let delegate = HelperDelegate()
        let listener = NSXPCListener(machServiceName: MissionIdentity.helper)
        listener.delegate = delegate
        listener.resume()
        withExtendedLifetime(delegate) { RunLoop.main.run() }
    }
}
