import AppKit
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
for size in [16,32,64,128,256,512,1024] {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let n = CGFloat(size)
    NSColor(calibratedRed: 0.09, green: 0.20, blue: 0.15, alpha: 1).setFill()
    NSBezierPath(roundedRect: NSRect(x: n*0.04,y:n*0.04,width:n*0.92,height:n*0.92), xRadius:n*0.2,yRadius:n*0.2).fill()
    let shield = NSBezierPath()
    shield.move(to: NSPoint(x:n*0.5,y:n*0.79)); shield.line(to:NSPoint(x:n*0.76,y:n*0.68));shield.line(to:NSPoint(x:n*0.73,y:n*0.43))
    shield.curve(to:NSPoint(x:n*0.5,y:n*0.20),controlPoint1:NSPoint(x:n*0.7,y:n*0.32),controlPoint2:NSPoint(x:n*0.59,y:n*0.23))
    shield.curve(to:NSPoint(x:n*0.27,y:n*0.43),controlPoint1:NSPoint(x:n*0.41,y:n*0.23),controlPoint2:NSPoint(x:n*0.3,y:n*0.32))
    shield.line(to:NSPoint(x:n*0.24,y:n*0.68));shield.close()
    NSColor.white.setStroke();shield.lineWidth=n*0.035;shield.stroke()
    let check=NSBezierPath();check.move(to:NSPoint(x:n*0.36,y:n*0.5));check.line(to:NSPoint(x:n*0.46,y:n*0.4));check.line(to:NSPoint(x:n*0.65,y:n*0.61));check.lineWidth=n*0.045;check.lineCapStyle = .round;check.lineJoinStyle = .round;check.stroke()
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
