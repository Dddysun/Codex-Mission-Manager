import AppKit
import SwiftUI

// Native geometry mirrors the layered brand SVG. Animation describes global
// control readiness, never the progress of an individual task.
struct JuicerLogo: View {
    var state: MissionLogoState
    var darkSurface = false
    var animated = true
    var compact = false
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var animating: Bool { state == .working && animated && !reduceMotion && !compact }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !animating)) { timeline in
            JuicerArtwork(state:state,dark:darkSurface || scheme == .dark,
                          time:animating ? timeline.date.timeIntervalSinceReferenceDate : nil,compact:compact)
        }
        .accessibilityElement(children:.ignore)
        .accessibilityLabel(L("TOKEN榨汁机"))
        .accessibilityValue(state.title)
    }
}

private struct JuicerArtwork: View {
    let state: MissionLogoState
    let dark: Bool
    let time: TimeInterval?
    var compact = false
    func color(_ light:String,_ darkValue:String) -> Color { Color(nsColor:MissionPalette.color(dark ? darkValue : light)) }
    func electricPath(_ points:[CGPoint]) -> Path { var p=Path();p.addLines(points);return p }
    func energy(_ path:Path,context:GraphicsContext,gold:Color,offset:Double=0,branch:Bool=false) {
        // Broad amber trail, saturated filament, and a warm bright core.
        // Continuous flow, with no flashes or rotating circular outline.
        let phase=time.map { -130 * ($0/1.8+offset).truncatingRemainder(dividingBy:1) } ?? -20
        let dash: [CGFloat] = branch ? [18,10,5,22] : [62,18,14,36]
        for (width,alpha,ink) in [(9.0,0.12,gold),(4.5,0.28,gold),(2.4,0.92,gold),(0.85,0.95,color("FFF2C9","FFE6A8"))] {
            var layer=context; layer.opacity=branch ? alpha*0.65 : alpha
            layer.stroke(path,with:.color(ink),style:StrokeStyle(lineWidth:width,lineCap:.round,lineJoin:.round,dash:dash,dashPhase:phase))
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
            if state == .working && !compact {
                energy(electricPath([CGPoint(x:74,y:214),CGPoint(x:57,y:197),CGPoint(x:61,y:184),CGPoint(x:43,y:169),CGPoint(x:49,y:154),CGPoint(x:33,y:137),CGPoint(x:42,y:123),CGPoint(x:35,y:103),CGPoint(x:51,y:89),CGPoint(x:46,y:73),CGPoint(x:64,y:61)]),context:context,gold:gold,offset:0.35)
                energy(electricPath([CGPoint(x:49,y:154),CGPoint(x:62,y:144),CGPoint(x:58,y:131)]),context:context,gold:gold,offset:0.35,branch:true)
            }
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
            var knob=context
            let angle=time.map { $0.truncatingRemainder(dividingBy:3.2)/3.2*360 } ?? 0
            knob.translateBy(x:127,y:36);knob.rotate(by:.degrees(angle));knob.translateBy(x:-127,y:-36)
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
                    let pulse=(1-cos(time*2*Double.pi/2.4))/2
                    let scale=0.985+0.03*pulse
                    symbol.opacity=0.78+0.22*pulse
                    symbol.translateBy(x:128,y:122);symbol.scaleBy(x:scale,y:scale);symbol.translateBy(x:-128,y:-122)
                }
                var bolt=Path();bolt.addLines([CGPoint(x:129,y:91),CGPoint(x:151,y:91),CGPoint(x:133,y:116),CGPoint(x:153,y:116),CGPoint(x:113,y:153),CGPoint(x:124,y:126),CGPoint(x:104,y:126)]);bolt.closeSubpath()
                symbol.fill(bolt,with:.color(state == .working ? gold : gray))
            }
            if state == .working && !compact {
                energy(electricPath([CGPoint(x:153,y:38),CGPoint(x:177,y:46),CGPoint(x:174,y:55),CGPoint(x:203,y:66),CGPoint(x:213,y:83),CGPoint(x:205,y:96),CGPoint(x:229,y:113),CGPoint(x:220,y:127),CGPoint(x:230,y:143),CGPoint(x:216,y:157),CGPoint(x:221,y:175),CGPoint(x:199,y:187),CGPoint(x:202,y:199),CGPoint(x:178,y:208),CGPoint(x:153,y:215),CGPoint(x:137,y:207),CGPoint(x:109,y:221),CGPoint(x:90,y:214)]),context:context,gold:gold)
                energy(electricPath([CGPoint(x:213,y:83),CGPoint(x:232,y:78),CGPoint(x:237,y:59)]),context:context,gold:gold,branch:true)
                energy(electricPath([CGPoint(x:199,y:187),CGPoint(x:215,y:199),CGPoint(x:226,y:195)]),context:context,gold:gold,offset:0.6,branch:true)
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
