import Foundation
import IOKit
import IOKit.pwr_mgt
import IOKit.ps
import Security

enum MissionIdentity {
    static let bundle = "com.dddysun.CodexMissionManager"
    static let helper = "com.dddysun.CodexMissionManager.PowerHelper"
    static let helperPlist = helper + ".plist"
    static let version = "0.3.1"
    // Substituted at build time. Empty in the local preview: helper rejects all peers.
    static let team = "__TEAM_ID__"
    static var releaseSigned: Bool { !team.isEmpty && team != "__TEAM_ID__" }
    static var clientRequirement: String {
        "anchor apple generic and identifier \"\(bundle)\" and certificate leaf[subject.OU] = \"\(team)\""
    }
}

@objc protocol PowerHelperProtocol {
    func status(withReply reply: @escaping (NSDictionary) -> Void)
    func enableClosedLid(onBattery: Bool, withReply reply: @escaping (NSDictionary) -> Void)
    func heartbeat(withReply reply: @escaping (NSDictionary) -> Void)
    func disable(withReply reply: @escaping (NSDictionary) -> Void)
}

enum HardwareState {
    static func rootProperty(_ key: String) -> Any? {
        let entry = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOPMrootDomain"))
        guard entry != 0 else { return nil }
        defer { IOObjectRelease(entry) }
        return IORegistryEntryCreateCFProperty(entry, key as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
    }
    static var sleepDisabled: Bool? { (rootProperty("SleepDisabled") as? NSNumber)?.boolValue }
    static var lidClosed: Bool? { (rootProperty("AppleClamshellState") as? NSNumber)?.boolValue }
    static func power() -> (ac: Bool, battery: Int?) {
        guard let info = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let sources = IOPSCopyPowerSourcesList(info)?.takeRetainedValue() as? [CFTypeRef] else { return (false, nil) }
        for source in sources {
            guard let value = IOPSGetPowerSourceDescription(info, source)?.takeUnretainedValue() as? [String: Any] else { continue }
            let ac = value[kIOPSPowerSourceStateKey] as? String == kIOPSACPowerValue
            let current = value[kIOPSCurrentCapacityKey] as? Int
            let maximum = value[kIOPSMaxCapacityKey] as? Int
            return (ac, current.flatMap { n in maximum.flatMap { $0 > 0 ? n * 100 / $0 : nil } })
        }
        return (false, nil)
    }
}

func runCommand(_ path: String, _ arguments: [String]) -> (Int32, String) {
    let task = Process(), pipe = Pipe()
    task.executableURL = URL(fileURLWithPath: path)
    task.arguments = arguments
    task.standardOutput = pipe
    task.standardError = pipe
    do {
        try task.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        task.waitUntilExit()
        return (task.terminationStatus, String(data: data, encoding: .utf8) ?? "")
    } catch { return (-1, error.localizedDescription) }
}
