import AppKit
import SwiftUI

// Isolated rendering shares the production painter, with a deterministic clock.
// It never creates MissionModel or opens private runtime data.
enum JuicerPreview {
    static func export(to directory:String) throws {
        let folder=URL(fileURLWithPath:directory,isDirectory:true)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        try JSONSerialization.data(withJSONObject:JuicerMotion.samples,options:[.sortedKeys])
            .write(to:folder.appendingPathComponent("motion.json"))
        if CommandLine.arguments.contains("--data-only") { return }
        let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
        let sequence=JuicerMotion.sequence(seed:20261029)
        let times=[0.0,1.0,2.0]+sequence.events.map{$0.start+$0.rise}
        for (index,time) in times.enumerated() {
            let root=JuicerArtwork(state:.working,dark:true,time:time,
                discharge:JuicerMotion.frame(sequence,at:time)).frame(width:384,height:384)
            let controller=NSHostingController(rootView:root)
            let window=NSWindow(contentViewController:controller)
            window.setContentSize(NSSize(width:384,height:384))
            let view=controller.view;view.layoutSubtreeIfNeeded()
            RunLoop.current.run(until:Date().addingTimeInterval(0.05))
            guard let bitmap=view.bitmapImageRepForCachingDisplay(in:view.bounds) else {throw CocoaError(.fileWriteUnknown)}
            view.cacheDisplay(in:view.bounds,to:bitmap)
            guard let png=bitmap.representation(using:.png,properties:[:]) else {throw CocoaError(.fileWriteUnknown)}
            try png.write(to:folder.appendingPathComponent("frame-\(index).png"))
            window.close()
        }
    }
}
