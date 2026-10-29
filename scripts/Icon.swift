import AppKit

// Static application icon. Live status and motion are rendered by JuicerLogo.swift.
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255) / 255,
            green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: 1)
}
func path(_ points: [(CGFloat, CGFloat)]) -> NSBezierPath {
    let p = NSBezierPath()
    guard let first = points.first else { return p }
    p.move(to: NSPoint(x: first.0, y: first.1))
    for q in points.dropFirst() { p.line(to: NSPoint(x: q.0, y: q.1)) }
    p.close(); return p
}
for size in [16,32,64,128,256,512,1024] {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let transform = AffineTransform(translationByX: 0, byY: CGFloat(size))
    let t = NSAffineTransform(transform: transform)
    t.scaleX(by: CGFloat(size) / 256, yBy: -CGFloat(size) / 256)
    t.concat()
    color(0xF1F5FA).setFill()
    NSBezierPath(roundedRect: NSRect(x: 8, y: 8, width: 240, height: 240), xRadius: 52, yRadius: 52).fill()
    let blue = color(0x2168D5), glass = color(0xEAF3FF)
    let handle = NSBezierPath()
    handle.move(to: NSPoint(x:180,y:78)); handle.line(to:NSPoint(x:199,y:78))
    handle.curve(to:NSPoint(x:226,y:110),controlPoint1:NSPoint(x:219,y:78),controlPoint2:NSPoint(x:228,y:89))
    handle.line(to:NSPoint(x:223,y:128))
    handle.curve(to:NSPoint(x:176,y:153),controlPoint1:NSPoint(x:221,y:147),controlPoint2:NSPoint(x:205,y:155))
    blue.setStroke(); handle.lineWidth=15; handle.lineJoinStyle = .round; handle.stroke()
    let cup = NSBezierPath()
    cup.move(to:NSPoint(x:62,y:63));cup.line(to:NSPoint(x:193,y:63));cup.line(to:NSPoint(x:181,y:158))
    cup.curve(to:NSPoint(x:160,y:177),controlPoint1:NSPoint(x:180,y:171),controlPoint2:NSPoint(x:173,y:177))
    cup.line(to:NSPoint(x:94,y:177));cup.curve(to:NSPoint(x:73,y:158),controlPoint1:NSPoint(x:81,y:177),controlPoint2:NSPoint(x:74,y:171));cup.close()
    blue.setFill();cup.fill()
    let inner = NSBezierPath()
    inner.move(to:NSPoint(x:78,y:76));inner.line(to:NSPoint(x:177,y:76));inner.line(to:NSPoint(x:166,y:155))
    inner.curve(to:NSPoint(x:155,y:163),controlPoint1:NSPoint(x:165,y:160),controlPoint2:NSPoint(x:162,y:163))
    inner.line(to:NSPoint(x:99,y:163));inner.curve(to:NSPoint(x:88,y:155),controlPoint1:NSPoint(x:92,y:163),controlPoint2:NSPoint(x:89,y:160));inner.close();glass.setFill();inner.fill()
    blue.setFill();NSBezierPath(roundedRect:NSRect(x:57,y:48,width:142,height:22),xRadius:11,yRadius:11).fill()
    NSBezierPath(roundedRect:NSRect(x:110,y:29,width:35,height:14),xRadius:6,yRadius:6).fill()
    glass.setFill();NSBezierPath(ovalIn:NSRect(x:122,y:31,width:10,height:10)).fill()
    let base = NSBezierPath()
    base.move(to:NSPoint(x:88,y:182));base.line(to:NSPoint(x:166,y:182))
    base.curve(to:NSPoint(x:187,y:199),controlPoint1:NSPoint(x:177,y:182),controlPoint2:NSPoint(x:184,y:188))
    base.line(to:NSPoint(x:190,y:212));base.curve(to:NSPoint(x:180,y:222),controlPoint1:NSPoint(x:191,y:219),controlPoint2:NSPoint(x:188,y:222))
    base.line(to:NSPoint(x:74,y:222));base.curve(to:NSPoint(x:64,y:212),controlPoint1:NSPoint(x:66,y:222),controlPoint2:NSPoint(x:63,y:219))
    base.line(to:NSPoint(x:67,y:199));base.curve(to:NSPoint(x:88,y:182),controlPoint1:NSPoint(x:70,y:188),controlPoint2:NSPoint(x:77,y:182));base.close();blue.setFill();base.fill()
    glass.setFill();NSBezierPath(ovalIn:NSRect(x:117,y:192,width:20,height:20)).fill()
    let tick = NSBezierPath();tick.move(to:NSPoint(x:127,y:196));tick.line(to:NSPoint(x:127,y:201));blue.setStroke();tick.lineWidth=3;tick.lineCapStyle = .round;tick.stroke()
    color(0x8795A8).setFill();path([(129,91),(151,91),(133,116),(153,116),(113,153),(124,126),(104,126)]).fill()
    NSGraphicsContext.restoreGraphicsState()
    let data=bitmap.representation(using:.png,properties:[:])!
    let names: [String]
    switch size {
    case 16:names=["icon_16x16.png"]
    case 32:names=["icon_16x16@2x.png","icon_32x32.png"]
    case 64:names=["icon_32x32@2x.png"]
    case 128:names=["icon_128x128.png"]
    case 256:names=["icon_128x128@2x.png","icon_256x256.png"]
    case 512:names=["icon_256x256@2x.png","icon_512x512.png"]
    default:names=["icon_512x512@2x.png"]
    }
    for name in names { try data.write(to:folder.appendingPathComponent(name)) }
}
