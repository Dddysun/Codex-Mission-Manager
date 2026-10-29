import AppKit
import SwiftUI

// Native geometry mirrors the layered brand SVG. Animation describes global
// control readiness, never the progress of an individual task.
// Geometry is generated once per cosmetic cycle, never once per frame.
final class JuicerMotionSession: ObservableObject {
    private var sequence=JuicerMotion.sequence(seed:UInt32.random(in:1...UInt32.max))
    private var started:Double?
    func frame(at time:Double)->[JuicerStrokeFrame] {
        if started == nil { started=time }
        if time-started! >= sequence.cycleSeconds || time < started! {
            sequence=JuicerMotion.sequence(seed:UInt32.random(in:1...UInt32.max));started=time
        }
        return JuicerMotion.frame(sequence,at:time-started!)
    }
}

struct JuicerLogo: View {
    var state: MissionLogoState
    var darkSurface = false
    var animated = true
    var compact = false
    @StateObject private var motion=JuicerMotionSession()
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var animating: Bool { state == .working && animated && !reduceMotion && !compact }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !animating)) { timeline in
            JuicerArtwork(state:state,dark:darkSurface || scheme == .dark,
                          time:animating ? timeline.date.timeIntervalSinceReferenceDate : nil,compact:compact,
                          discharge:animating ? motion.frame(at:timeline.date.timeIntervalSinceReferenceDate):[])
        }
        .accessibilityElement(children:.ignore)
        .accessibilityLabel(L("TOKEN榨汁机"))
        .accessibilityValue(state.title)
    }
}

struct JuicerArtwork: View {
    let state: MissionLogoState
    let dark: Bool
    let time: TimeInterval?
    var compact = false
    func color(_ light:String,_ darkValue:String) -> Color { Color(nsColor:MissionPalette.color(dark ? darkValue : light)) }
    var discharge:[JuicerStrokeFrame] = []
    func drawDischarge(_ context:GraphicsContext,gold:Color) {
        for frame in discharge where frame.opacity>0 && frame.progress>0 {
            var path=Path();path.addLines(frame.stroke.detailed.map{CGPoint(x:$0.x,y:$0.y)})
            let partial=path.trimmedPath(from:0,to:frame.progress),level=frame.stroke.level
            for (width,alpha,ink) in [(6.5,0.17,gold),(level==0 ? 2.4:level==1 ? 1.6:1.2,0.98,gold),
                                    (level==0 ? 1.3:level==1 ? 0.86:0.62,1.0,color("FFF8E7","FFF5DD"))] {
                var layer=context;layer.opacity=frame.opacity*alpha
                layer.stroke(partial,with:.color(ink),style:StrokeStyle(lineWidth:width,lineCap:.round,lineJoin:.round))
            }
        }
    }
    var body: some View {
        Canvas { context,size in
            context.scaleBy(x:size.width/(compact ? 208 : 256),y:size.height/(compact ? 208 : 256))
            if compact { context.translateBy(x:-35,y:-23) }
            let muted=state == .idle || state == .disconnected
            let blue=compact ? Color(nsColor:MissionPalette.color(muted ? "889EB8" : "4599F5")) : (muted ? color("758598","637285") : color("2168D5","5386BF"))
            let glass=compact ? Color(nsColor:MissionPalette.color("DFEEFF")) : (state == .idle ? color("EFF1F4","202A38") : color("EAF3FF","20344C"))
            let gray=color("8795A8","7F8C9C"), gold=color("F5B82E","F2BA42")
            var handle=Path()
            handle.move(to:CGPoint(x:180,y:78));handle.addLine(to:CGPoint(x:199,y:78))
            handle.addQuadCurve(to:CGPoint(x:226,y:110),control:CGPoint(x:229,y:78))
            handle.addLine(to:CGPoint(x:223,y:128));handle.addQuadCurve(to:CGPoint(x:176,y:153),control:CGPoint(x:220,y:156))
            context.stroke(handle,with:.color(blue),style:StrokeStyle(lineWidth:15,lineJoin:.round))
            var cup=Path()
            cup.move(to:CGPoint(x:62,y:63));cup.addLine(to:CGPoint(x:193,y:63));cup.addLine(to:CGPoint(x:181,y:158))
            cup.addQuadCurve(to:CGPoint(x:160,y:177),control:CGPoint(x:179,y:177));cup.addLine(to:CGPoint(x:94,y:177))
            cup.addQuadCurve(to:CGPoint(x:73,y:158),control:CGPoint(x:75,y:177));cup.closeSubpath()
            context.fill(cup,with:.color(blue))
            var inner=Path()
            inner.move(to:CGPoint(x:78,y:76));inner.addLine(to:CGPoint(x:177,y:76));inner.addLine(to:CGPoint(x:166,y:155))
            inner.addQuadCurve(to:CGPoint(x:155,y:163),control:CGPoint(x:165,y:163));inner.addLine(to:CGPoint(x:99,y:163))
            inner.addQuadCurve(to:CGPoint(x:88,y:155),control:CGPoint(x:89,y:163));inner.closeSubpath()
            context.fill(inner,with:.color(glass))
            context.fill(Path(roundedRect:CGRect(x:57,y:48,width:142,height:22),cornerRadius:11),with:.color(blue))
            context.fill(Path(roundedRect:CGRect(x:110,y:29,width:35,height:14),cornerRadius:6),with:.color(blue))
            let knob=context
            knob.fill(Path(ellipseIn:CGRect(x:122,y:31,width:10,height:10)),with:.color(glass))
            var tick=Path();tick.move(to:CGPoint(x:127,y:32));tick.addLine(to:CGPoint(x:127,y:36))
            knob.stroke(tick,with:.color(blue),style:StrokeStyle(lineWidth:2.5,lineCap:.round))
            var base=Path()
            base.move(to:CGPoint(x:88,y:182));base.addLine(to:CGPoint(x:166,y:182));base.addQuadCurve(to:CGPoint(x:187,y:199),control:CGPoint(x:183,y:182))
            base.addLine(to:CGPoint(x:190,y:212));base.addQuadCurve(to:CGPoint(x:180,y:222),control:CGPoint(x:192,y:222));base.addLine(to:CGPoint(x:74,y:222))
            base.addQuadCurve(to:CGPoint(x:64,y:212),control:CGPoint(x:62,y:222));base.addLine(to:CGPoint(x:67,y:199));base.addQuadCurve(to:CGPoint(x:88,y:182),control:CGPoint(x:71,y:182));base.closeSubpath()
            context.fill(base,with:.color(blue));context.fill(Path(ellipseIn:CGRect(x:117,y:192,width:20,height:20)),with:.color(glass))
            var power=Path();power.move(to:CGPoint(x:127,y:196));power.addLine(to:CGPoint(x:127,y:201))
            context.stroke(power,with:.color(blue),style:StrokeStyle(lineWidth:3,lineCap:.round))
            if state == .working && !compact { drawDischarge(context,gold:gold) }
            var symbol=context
            switch state {
            case .waiting:
                var pause=Path();pause.move(to:CGPoint(x:115,y:94));pause.addLine(to:CGPoint(x:115,y:135));pause.move(to:CGPoint(x:139,y:94));pause.addLine(to:CGPoint(x:139,y:135))
                symbol.stroke(pause,with:.color(gold),style:StrokeStyle(lineWidth:10,lineCap:.round))
            case .disconnected:
                var link=Path();link.move(to:CGPoint(x:119,y:98));link.addLine(to:CGPoint(x:115,y:94))
                link.addCurve(to:CGPoint(x:100,y:98),control1:CGPoint(x:110,y:89),control2:CGPoint(x:102,y:91))
                link.addCurve(to:CGPoint(x:104,y:109),control1:CGPoint(x:99,y:102),control2:CGPoint(x:100,y:106));link.addLine(to:CGPoint(x:113,y:118))
                link.move(to:CGPoint(x:136,y:111));link.addLine(to:CGPoint(x:145,y:120))
                link.addCurve(to:CGPoint(x:145,y:136),control1:CGPoint(x:150,y:125),control2:CGPoint(x:150,y:132))
                link.addCurve(to:CGPoint(x:130,y:134),control1:CGPoint(x:140,y:140),control2:CGPoint(x:134,y:138));link.addLine(to:CGPoint(x:126,y:130))
                link.move(to:CGPoint(x:111,y:135));link.addLine(to:CGPoint(x:143,y:94))
                symbol.stroke(link,with:.color(gray),style:StrokeStyle(lineWidth:6,lineCap:.round,lineJoin:.round))
            case .error:
                let red=color("CD5058","D67A80")
                var mark=Path();mark.addLines([CGPoint(x:122,y:89),CGPoint(x:134,y:89),CGPoint(x:132,y:122),CGPoint(x:124,y:122)]);mark.closeSubpath()
                symbol.fill(mark,with:.color(red));symbol.fill(Path(ellipseIn:CGRect(x:122,y:129,width:12,height:12)),with:.color(red))
            case .idle,.working:
                if state == .working, let time {
                    symbol.opacity=JuicerMotion.breath(time)
                }
                var bolt=Path();bolt.addLines([CGPoint(x:129,y:91),CGPoint(x:151,y:91),CGPoint(x:133,y:116),CGPoint(x:153,y:116),CGPoint(x:113,y:153),CGPoint(x:124,y:126),CGPoint(x:104,y:126)]);bolt.closeSubpath()
                symbol.fill(bolt,with:.color(state == .working ? gold : gray))
            }
        }.aspectRatio(1,contentMode:.fit)
    }
}

struct JuicerStatusIcon: View {
    @ObservedObject var model: MissionModel
    var body: some View { JuicerLogo(state:model.logoState,animated:false,compact:true).padding(1).preferredColorScheme(.light) }
}

// The native status button remains responsible for left/right clicks.
final class JuicerStatusHostingView: NSHostingView<JuicerStatusIcon> {
    override func hitTest(_ point:NSPoint) -> NSView? { nil }
}
