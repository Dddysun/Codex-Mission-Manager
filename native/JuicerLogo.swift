import AppKit
import SwiftUI

// Native geometry mirrors the layered brand SVG. Animation describes global
// control readiness, never the progress of an individual task.
struct JuicerLogo: View {
    var state: MissionLogoState
    var darkSurface = false
    var animated = true
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var animating: Bool { state == .working && animated && !reduceMotion }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !animating)) { timeline in
            JuicerArtwork(state:state,dark:darkSurface || scheme == .dark,
                          time:animating ? timeline.date.timeIntervalSinceReferenceDate : nil)
        }
        .accessibilityElement(children:.ignore)
        .accessibilityLabel(L("榨汁机"))
        .accessibilityValue(state.title)
    }
}

private struct JuicerArtwork: View {
    let state: MissionLogoState
    let dark: Bool
    let time: TimeInterval?
    func color(_ light:String,_ darkValue:String) -> Color { Color(nsColor:MissionPalette.color(dark ? darkValue : light)) }
    func energy(_ path:Path,context:GraphicsContext,gold:Color) {
        var layer=context
        layer.opacity=0.16
        layer.stroke(path,with:.color(gold),style:StrokeStyle(lineWidth:1.2,lineCap:.round,lineJoin:.round))
        layer.opacity=0.8
        let phase=time.map { -312 * $0.truncatingRemainder(dividingBy:2.8)/2.8 } ?? 0
        layer.stroke(path,with:.color(gold),style:StrokeStyle(lineWidth:2.2,lineCap:.round,lineJoin:.round,dash:[38,150,12,112],dashPhase:phase))
    }
    var body: some View {
        Canvas { context,size in
            context.scaleBy(x:size.width/256,y:size.height/256)
            let muted=state == .idle || state == .disconnected
            let blue=muted ? color("758598","637285") : color("2168D5","4878AF")
            let glass=state == .idle ? color("EFF1F4","202A38") : color("EAF3FF","172638")
            let gray=color("8795A8","7F8C9C"), gold=color("E7AA16","E7B43C")
            if state == .working {
                var back=Path()
                back.move(to:CGPoint(x:48,y:181))
                back.addCurve(to:CGPoint(x:41,y:88),control1:CGPoint(x:17,y:161),control2:CGPoint(x:18,y:119))
                back.addLine(to:CGPoint(x:35,y:78));back.addLine(to:CGPoint(x:51,y:77))
                back.addCurve(to:CGPoint(x:149,y:25),control1:CGPoint(x:66,y:47),control2:CGPoint(x:109,y:26))
                back.addLine(to:CGPoint(x:158,y:18));back.addLine(to:CGPoint(x:164,y:28))
                back.addCurve(to:CGPoint(x:236,y:91),control1:CGPoint(x:201,y:31),control2:CGPoint(x:231,y:60))
                energy(back,context:context,gold:gold)
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
                    let scale=0.97+0.06*pulse
                    symbol.opacity=0.62+0.38*pulse
                    symbol.translateBy(x:128,y:114);symbol.scaleBy(x:scale,y:scale);symbol.translateBy(x:-128,y:-114)
                }
                var bolt=Path();bolt.addLines([CGPoint(x:129,y:83),CGPoint(x:151,y:83),CGPoint(x:133,y:108),CGPoint(x:153,y:108),CGPoint(x:113,y:145),CGPoint(x:124,y:118),CGPoint(x:104,y:118)]);bolt.closeSubpath()
                symbol.fill(bolt,with:.color(state == .working ? gold : gray))
            }
            if state == .working {
                var front=Path();front.move(to:CGPoint(x:223,y:90));front.addLine(to:CGPoint(x:234,y:99));front.addLine(to:CGPoint(x:226,y:109))
                front.addCurve(to:CGPoint(x:199,y:198),control1:CGPoint(x:244,y:143),control2:CGPoint(x:229,y:180));front.addLine(to:CGPoint(x:208,y:203));front.addLine(to:CGPoint(x:190,y:205))
                front.addCurve(to:CGPoint(x:76,y:225),control1:CGPoint(x:162,y:225),control2:CGPoint(x:114,y:239));front.addLine(to:CGPoint(x:66,y:232));front.addLine(to:CGPoint(x:63,y:221))
                front.addCurve(to:CGPoint(x:26,y:174),control1:CGPoint(x:38,y:211),control2:CGPoint(x:22,y:191))
                energy(front,context:context,gold:gold)
            }
        }.aspectRatio(1,contentMode:.fit)
    }
}

struct JuicerStatusIcon: View {
    @ObservedObject var model: MissionModel
    var body: some View { JuicerLogo(state:model.logoState).padding(1).preferredColorScheme(model.colorScheme) }
}

// The native status button remains responsible for left/right clicks.
final class JuicerStatusHostingView: NSHostingView<JuicerStatusIcon> {
    override func hitTest(_ point:NSPoint) -> NSView? { nil }
}
