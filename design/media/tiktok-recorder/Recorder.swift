import AppKit
import SwiftUI
import AVFoundation
import CoreVideo
import CoreImage

final class RecordingClock: ObservableObject {
    static let shared=RecordingClock()
    @Published var seconds=0.0
    var epoch=0.0
    var detailsExpanded=false
}

struct RecordingStep: Decodable {
    var at:Double
    var snapshot:MissionSnapshot
    var notice:String?,theme:String?,accent:String?,section:String?,filter:String?
    var expanded:Bool?,typing:Bool?
}
struct RecordingScene: Decodable {
    var key:String,title:String,subtitle:String,view:String
    var duration:Double
    var focus:[Double]
    var theme:String?
    var media:String?
    var sourceCredit:String?
    var steps:[RecordingStep]
}
struct RecordingPlan: Decodable {
    var schema:Int,product:String,version:String,brand:String
    var simulation:Bool
    var prompt:String
    var scenes:[RecordingScene]
}

final class RecordingDriver: ObservableObject {
    let model=MissionModel()
    @Published var section="tasks"
    @Published var filter=MissionActivityFilter.all
    @Published var rootIdentity=""
    var currentStep = -1
    var typedText:String?
    func update(_ scene:RecordingScene,at t:Double,prompt:String) {
        let index=scene.steps.lastIndex(where:{$0.at<=t}) ?? 0
        let step=scene.steps[index]
        if index != currentStep {
            currentStep=index
            RecordingClock.shared.detailsExpanded=step.expanded ?? false
            model.snapshot=step.snapshot;model.connected=true;model.paused=step.snapshot.control_paused
            model.notice=step.notice ?? "";model.theme=step.theme ?? scene.theme ?? "light"
            model.accent=step.accent ?? "blue"
            section=step.section ?? "tasks";filter=MissionActivityFilter(rawValue:step.filter ?? "all") ?? .all
            rootIdentity="\(section)-\(filter.rawValue)-\(step.expanded ?? false)"
            NSApplication.shared.appearance=NSAppearance(named:model.theme == "dark" ? .darkAqua:.aqua)
        }
        RecordingClock.shared.epoch=(step.snapshot.observed_at ?? 0)+t-step.at
        if step.typing == true, let chat=model.snapshot?.tasks.first {
            precondition(chat.id.hasPrefix("demo-"))
            let progress=max(0,min(1,(t-1.5)/6.5)),count=Int(Double(prompt.count)*progress)
            let value=String(prompt.prefix(count))
            typedText=value
        } else {typedText=nil;if !model.drafts.isEmpty {model.drafts=[:]}}
        RecordingClock.shared.seconds=t
        precondition(model.host == nil && model.baseURL == nil && model.stateDirectory == nil)
        precondition(NativeLocalization.testLanguage == "zh")
    }
}

struct RecordingRoot: View {
    @ObservedObject var driver:RecordingDriver
    let kind:String
    var body:some View {
        Group {
            if kind == "menu" {MissionMenuPanel(model:driver.model,openWindow:{},openSettings:{},quit:{})}
            else if kind == "outro" {RecordingEndCard(driver:driver)}
            else if kind == "brand" {
                VStack(spacing:22) {
                    JuicerLogo(state:.working,darkSurface:true).frame(width:270,height:270)
                    Text("TokenMax").font(.system(size:60,weight:.bold))
                    Text("Token榨汁机").font(.system(size:25,weight:.medium)).foregroundStyle(.secondary)
                }.frame(maxWidth:.infinity,maxHeight:.infinity).background(Color(nsColor:MissionPalette.color("101A29")))
            } else {
                MissionWindow(model:driver.model,showSettings:{},initialSection:driver.section,
                              initialActivityFilter:driver.filter).id(driver.rootIdentity)
            }
        }.preferredColorScheme(driver.model.colorScheme).environment(\.controlActiveState,.key)
    }
}

struct RecordingEndCard: View {
    @ObservedObject var driver:RecordingDriver
    @ObservedObject var clock=RecordingClock.shared
    private var progress:Double {let x=max(0,min(1,(clock.seconds-0.6)/1.6));return x*x*(3-2*x)}
    var body:some View {
        VStack(spacing:14) {
                JuicerLogo(state:.working,darkSurface:true).frame(width:225,height:225)
                Text("Token榨汁机").font(.system(size:38,weight:.bold)).foregroundStyle(.white)
                Text("TokenMax").font(.system(size:52,weight:.bold)).foregroundStyle(.white)
                RoundedRectangle(cornerRadius:2).fill(Color(nsColor:MissionPalette.color("F2BA42")))
                    .frame(width:48,height:3).padding(.top,12)
                Text("把会员权益，用到位。")
                    .font(.system(size:16,weight:.medium)).foregroundStyle(.white.opacity(0.76)).padding(.top,8)
        }.frame(maxWidth:.infinity,maxHeight:.infinity)
            .opacity(progress).offset(y:16*(1-progress)).background(Color.clear)
    }
}

// Layer blur can disappear in AppKit's offscreen cache. Composite an explicit
// Gaussian-filtered native backdrop so the delivered frames contain the blur.
final class RecordingGaussianBackdrop {
    let original:CGImage
    let processor=CIContext(options:[.cacheIntermediates:false])
    private var level = -1
    private var blurred:CGImage?
    init(_ image:CGImage) {original=image}
    func frame(foreground:CGImage,time:Double)throws->CGImage {
        let x=max(0,min(1,(time-0.6)/1.6)),progress=x*x*(3-2*x)
        let next=Int((progress*20).rounded())
        if next != level {
            level=next
            let source=CIImage(cgImage:original)
            let filtered=source.clampedToExtent().applyingFilter("CIGaussianBlur",parameters:[kCIInputRadiusKey:Double(level)*2.6])
            guard let result=processor.createCGImage(filtered.cropped(to:source.extent),from:source.extent)
            else {throw RecordingError.message("Cannot render Gaussian backdrop")}
            blurred=result
        }
        guard let context=CGContext(data:nil,width:original.width,height:original.height,bitsPerComponent:8,bytesPerRow:0,
                                    space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)
        else {throw RecordingError.message("Cannot composite ending")}
        let rect=CGRect(x:0,y:0,width:original.width,height:original.height)
        context.draw(blurred ?? original,in:rect)
        context.setFillColor(NSColor.black.withAlphaComponent(0.62*progress).cgColor);context.fill(rect)
        context.draw(foreground,in:rect)
        guard let result=context.makeImage() else {throw RecordingError.message("Cannot produce ending frame")}
        return result
    }
}

enum RecordingError:Error {case message(String)}

final class RecordingWindow:NSWindow {
    override var isKeyWindow:Bool {true}
    override var isMainWindow:Bool {true}
}

final class RecordingApplication:NSApplication {
    override var isActive:Bool {true}
}

func recordingEditor(_ root:NSView)->NSTextView? {
    func collect(_ view:NSView)->[NSTextView] {
        (view as? NSTextView).map{[$0]} ?? view.subviews.flatMap{collect($0)}
    }
    return collect(root).filter{root.convert($0.bounds,from:$0).intersects(root.bounds)}.sorted {
        let a=root.convert($0.bounds,from:$0),b=root.convert($1.bounds,from:$1)
        return root.isFlipped ? a.minY<b.minY:a.maxY>b.maxY
    }.first
}

final class MovieWriter {
    let writer:AVAssetWriter,input:AVAssetWriterInput,adaptor:AVAssetWriterInputPixelBufferAdaptor
    let width:Int,height:Int
    init(url:URL,width:Int,height:Int,bitrate:Int) throws {
        guard !FileManager.default.fileExists(atPath:url.path) else {throw RecordingError.message("Output already exists: \(url.lastPathComponent)")}
        self.width=width;self.height=height
        writer=try AVAssetWriter(outputURL:url,fileType:.mp4)
        input=AVAssetWriterInput(mediaType:.video,outputSettings:[
            AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:width,AVVideoHeightKey:height,
            AVVideoColorPropertiesKey:[AVVideoColorPrimariesKey:AVVideoColorPrimaries_ITU_R_709_2,
                AVVideoTransferFunctionKey:AVVideoTransferFunction_ITU_R_709_2,
                AVVideoYCbCrMatrixKey:AVVideoYCbCrMatrix_ITU_R_709_2],
            AVVideoCompressionPropertiesKey:[AVVideoAverageBitRateKey:bitrate,
                AVVideoExpectedSourceFrameRateKey:30,AVVideoMaxKeyFrameIntervalKey:60,
                AVVideoProfileLevelKey:AVVideoProfileLevelH264HighAutoLevel,
                AVVideoAllowFrameReorderingKey:false]])
        input.expectsMediaDataInRealTime=false
        adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[
            kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String:width,kCVPixelBufferHeightKey as String:height,
            kCVPixelBufferCGImageCompatibilityKey as String:true,
            kCVPixelBufferCGBitmapContextCompatibilityKey as String:true])
        guard writer.canAdd(input) else {throw RecordingError.message("Cannot attach video encoder")}
        writer.add(input)
        guard writer.startWriting() else {throw writer.error ?? RecordingError.message("Cannot start encoder")}
        writer.startSession(atSourceTime:.zero)
    }
    func append(frame:Int,poster:URL?,draw:(CGContext)->Void) throws {
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed {throw writer.error ?? RecordingError.message("Encoder failed")}
            RunLoop.current.run(until:Date().addingTimeInterval(0.002))
        }
        guard let pool=adaptor.pixelBufferPool else {throw RecordingError.message("Missing frame buffer pool")}
        var buffer:CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil,pool,&buffer)==kCVReturnSuccess,let buffer else {throw RecordingError.message("Cannot allocate frame")}
        CVPixelBufferLockBaseAddress(buffer,[])
        let context=CGContext(data:CVPixelBufferGetBaseAddress(buffer),width:width,height:height,
            bitsPerComponent:8,bytesPerRow:CVPixelBufferGetBytesPerRow(buffer),space:CGColorSpace(name:CGColorSpace.sRGB)!,
            bitmapInfo:CGImageAlphaInfo.premultipliedFirst.rawValue|CGBitmapInfo.byteOrder32Little.rawValue)!
        draw(context)
        if let poster, let image=context.makeImage(),let data=NSBitmapImageRep(cgImage:image).representation(using:.png,properties:[:]) {
            try data.write(to:poster)
        }
        CVPixelBufferUnlockBaseAddress(buffer,[])
        guard adaptor.append(buffer,withPresentationTime:CMTime(value:Int64(frame),timescale:30)) else {throw writer.error ?? RecordingError.message("Cannot append frame")}
    }
    func finish() throws {
        input.markAsFinished()
        let semaphore=DispatchSemaphore(value:0)
        writer.finishWriting {semaphore.signal()}
        while semaphore.wait(timeout:.now()) != .success {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
        guard writer.status == .completed else {throw writer.error ?? RecordingError.message("Cannot finalize movie")}
    }
}

func recordText(_ text:String,context:CGContext,x:Double,top:Double,width:Double,height:Double,
                canvasHeight:Double,size:Double,color:NSColor,weight:NSFont.Weight = .regular) {
    let style=NSMutableParagraphStyle();style.lineBreakMode = .byWordWrapping
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current=NSGraphicsContext(cgContext:context,flipped:false)
    NSAttributedString(string:text,attributes:[.font:NSFont.systemFont(ofSize:size,weight:weight),
        .foregroundColor:color,.paragraphStyle:style]).draw(in:NSRect(x:x,y:canvasHeight-top-height,width:width,height:height))
    NSGraphicsContext.restoreGraphicsState()
}
func recordingBackground(_ context:CGContext,width:Int,height:Int) {
    context.setFillColor(MissionPalette.color("0B1422").cgColor)
    context.fill(CGRect(x:0,y:0,width:width,height:height))
}
func recordingCanvasImage(_ image:CGImage)->CGImage {
    let context=CGContext(data:nil,width:2560,height:1600,bitsPerComponent:8,bytesPerRow:0,
                          space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
    recordingBackground(context,width:2560,height:1600)
    let scale=min(2560/Double(image.width),1600/Double(image.height))
    let width=Double(image.width)*scale,height=Double(image.height)*scale
    context.draw(image,in:CGRect(x:(2560-width)/2,y:(1600-height)/2,width:width,height:height))
    return context.makeImage()!
}
func drawSource(_ image:CGImage,scene:RecordingScene,time:Double,context:CGContext) {
    recordingBackground(context,width:2560,height:1600)
    let scale=min(2560/Double(image.width),1600/Double(image.height))
    let w=Double(image.width)*scale,h=Double(image.height)*scale
    let zoom=scene.media == nil ? 1:1+0.035*min(1,time/scene.duration)
    context.draw(image,in:CGRect(x:(2560-w*zoom)/2,y:(1600-h*zoom)/2,width:w*zoom,height:h*zoom))
    context.setFillColor(NSColor.black.withAlphaComponent(0.67).cgColor)
    context.fill(CGRect(x:22,y:14,width:495,height:42))
    recordText(scene.sourceCredit ?? "界面演示 · 模拟数据 · 时间已压缩",context:context,x:38,top:1554,width:475,height:32,
               canvasHeight:1600,size:22,color:.white)
}
func drawPortrait(_ image:CGImage,logical:NSSize,scene:RecordingScene,time:Double,context:CGContext) {
    recordingBackground(context,width:1080,height:1920)
    let white=NSColor.white,muted=MissionPalette.color("A7B7CF")
    if scene.view == "outro" {
        let scale=max(1080/Double(image.width),1920/Double(image.height))
        let width=Double(image.width)*scale,height=Double(image.height)*scale
        context.draw(image,in:CGRect(x:(1080-width)/2,y:(1920-height)/2,width:width,height:height))
        recordText("原生界面演示 · 模拟数据",context:context,x:70,top:1780,width:940,height:45,
                   canvasHeight:1920,size:22,color:muted)
        return
    }
    context.setFillColor(MissionPalette.color("F2BA42").cgColor);context.fill(CGRect(x:70,y:1670,width:50,height:5))
    recordText("TokenMax / Token榨汁机",context:context,x:70,top:180,width:940,height:45,
               canvasHeight:1920,size:27,color:muted,weight:.semibold)
    recordText(scene.title,context:context,x:66,top:282,width:950,height:160,
               canvasHeight:1920,size:64,color:white,weight:.bold)
    recordText(scene.subtitle,context:context,x:70,top:440,width:930,height:85,
               canvasHeight:1920,size:30,color:muted)
    let frame=CGRect(x:46,y:270,width:988,height:1080)
    context.saveGState()
    context.addPath(CGPath(roundedRect:frame,cornerWidth:26,cornerHeight:26,transform:nil));context.clip()
    context.setFillColor(MissionPalette.color("142035").cgColor);context.fill(frame)
    let initial=CGRect(x:0,y:0,width:logical.width,height:logical.height)
    let end=CGRect(x:scene.focus[0],y:scene.focus[1],width:scene.focus[2],height:scene.focus[3])
    let phase=max(0,min(1,(time-1.1)/2.8)),ease=phase*phase*(3-2*phase)
    let focus=CGRect(x:initial.minX+(end.minX-initial.minX)*ease,y:initial.minY+(end.minY-initial.minY)*ease,
                     width:initial.width+(end.width-initial.width)*ease,height:initial.height+(end.height-initial.height)*ease)
    let scale=min(frame.width/focus.width,frame.height/focus.height)
    let rect=CGRect(x:frame.midX-focus.midX*scale,
                    y:frame.midY-(logical.height-focus.midY)*scale,
                    width:logical.width*scale,height:logical.height*scale)
    context.interpolationQuality = .high;context.draw(image,in:rect);context.restoreGState()
    recordText(scene.sourceCredit ?? "原生界面演示 · 模拟数据 · 时间已压缩",context:context,x:70,top:1700,width:940,height:45,
               canvasHeight:1920,size:24,color:muted)
    recordText("TokenMax  0.4.2 / build 13",context:context,x:70,top:1760,width:940,height:38,
               canvasHeight:1920,size:23,color:muted)
}

@main enum TokenMaxMediaRecorder {
    static func main() {
        do {try run()} catch {fputs("Media recording failed: \(error)\n",stderr);exit(1)}
    }
    static func run() throws {
        let args=CommandLine.arguments
        guard args.count>=3 else {throw RecordingError.message("Usage: recorder PLAN.json OUTPUT [--scene PREFIX] [--preview]")}
        let plan=try JSONDecoder().decode(RecordingPlan.self,from:Data(contentsOf:URL(fileURLWithPath:args[1])))
        precondition(plan.simulation && plan.schema == 1)
        let output=URL(fileURLWithPath:args[2],isDirectory:true)
        let vertical=output.appendingPathComponent("01_竖屏_1080x1920"),horizontal=output.appendingPathComponent("02_横屏原始_2560x1600"),posters=output.appendingPathComponent("03_封面与预览")
        for folder in [vertical,horizontal,posters] {try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)}
        NativeLocalization.testLanguage="zh"
        NSTimeZone.default=TimeZone(secondsFromGMT:14400)!
        let app=RecordingApplication.shared;app.setActivationPolicy(.prohibited)
        let preview=args.contains("--preview")
        let selection=args.firstIndex(of:"--scene").flatMap {args.count>$0+1 ? args[$0+1]:nil}
        for scene in plan.scenes where selection == nil || scene.key.hasPrefix(selection!) {
            try autoreleasepool {try render(scene,plan:plan,vertical:vertical,horizontal:horizontal,posters:posters,preview:preview)}
        }
        print("MEDIA_RECORDING_COMPLETE");fflush(stdout)
    }
    static func render(_ scene:RecordingScene,plan:RecordingPlan,vertical:URL,horizontal:URL,posters:URL,preview:Bool) throws {
        let driver=RecordingDriver();driver.update(scene,at:0,prompt:plan.prompt)
        let logical=scene.view == "menu" ? NSSize(width:400,height:570):NSSize(width:1280,height:800)
        let controller=NSHostingController(rootView:RecordingRoot(driver:driver,kind:scene.view))
        let window=RecordingWindow(contentViewController:controller);window.isReleasedWhenClosed=false
        window.isOpaque=false;window.backgroundColor = .clear
        window.setContentSize(logical);window.appearance=NSApplication.shared.appearance
        let view=controller.view;view.layoutSubtreeIfNeeded()
        view.wantsLayer=true;view.layer?.backgroundColor=NSColor.clear.cgColor
        let externalImage:CGImage? = try scene.media.map {path in
            guard let image=NSImage(contentsOfFile:path)?.cgImage(forProposedRect:nil,context:nil,hints:nil)
            else {throw RecordingError.message("Cannot read public demonstration image")}
            return recordingCanvasImage(image)
        }
        RunLoop.current.run(until:Date().addingTimeInterval(0.15))
        var backdrop:RecordingGaussianBackdrop?
        if scene.view == "outro" {
            let backgroundController=NSHostingController(rootView:RecordingRoot(driver:driver,kind:"app"))
            let backgroundWindow=RecordingWindow(contentViewController:backgroundController)
            backgroundWindow.isReleasedWhenClosed=false;backgroundWindow.setContentSize(logical)
            let backgroundView=backgroundController.view
            RunLoop.current.run(until:Date().addingTimeInterval(0.12));backgroundView.layoutSubtreeIfNeeded()
            guard let bitmap=backgroundView.bitmapImageRepForCachingDisplay(in:backgroundView.bounds)
            else {throw RecordingError.message("Cannot capture native ending backdrop")}
            backgroundView.effectiveAppearance.performAsCurrentDrawingAppearance {
                backgroundView.cacheDisplay(in:backgroundView.bounds,to:bitmap)
            }
            guard let image=bitmap.cgImage else {throw RecordingError.message("Missing ending backdrop")}
            backdrop=RecordingGaussianBackdrop(image);backgroundWindow.close()
        }
        let source:MovieWriter? = preview ? nil:try MovieWriter(url:horizontal.appendingPathComponent(scene.key+".mp4"),width:2560,height:1600,bitrate:12_000_000)
        let portrait:MovieWriter? = preview ? nil:try MovieWriter(url:vertical.appendingPathComponent(scene.key+".mp4"),width:1080,height:1920,bitrate:7_000_000)
        let count=preview ? 1:Int(scene.duration*30)
        for i in 0..<count {
            try autoreleasepool {
                let t=preview ? min(scene.duration-0.1,6):Double(i)/30
                driver.update(scene,at:t,prompt:plan.prompt);window.appearance=NSApplication.shared.appearance
                RunLoop.current.run(until:Date().addingTimeInterval(preview ? 0.12:0.003));view.layoutSubtreeIfNeeded()
                if let text=driver.typedText,let editor=recordingEditor(view),editor.string != text {
                    // This is the isolated fixture's own NSTextView. Its normal
                    // edit delegate updates only the in-memory demonstration draft.
                    window.makeFirstResponder(editor)
                    editor.insertText(text,replacementRange:NSRange(location:0,length:(editor.string as NSString).length))
                    view.layoutSubtreeIfNeeded()
                }
                guard let bitmap=view.bitmapImageRepForCachingDisplay(in:view.bounds) else {throw RecordingError.message("Cannot capture native view")}
                view.effectiveAppearance.performAsCurrentDrawingAppearance {view.cacheDisplay(in:view.bounds,to:bitmap)}
                guard var image=externalImage ?? bitmap.cgImage else {throw RecordingError.message("Cannot produce native frame")}
                if let backdrop {image=try backdrop.frame(foreground:image,time:t)}
                if preview {
                    try NSBitmapImageRep(cgImage:image).representation(using:.png,properties:[:])!.write(to:posters.appendingPathComponent(scene.key+"_原生.png"))
                } else {
                    let sample=(i==0 || i==count/2 || i==count-1)
                    let stamp=i==0 ? "开始":i==count-1 ? "结束":"中间"
                    try source!.append(frame:i,poster:sample ? posters.appendingPathComponent(scene.key+"_横屏_"+stamp+".png"):nil) {drawSource(image,scene:scene,time:t,context:$0)}
                    try portrait!.append(frame:i,poster:sample ? posters.appendingPathComponent(scene.key+"_竖屏_"+stamp+".png"):nil) {drawPortrait(image,logical:logical,scene:scene,time:t,context:$0)}
                }
            }
        }
        try source?.finish();try portrait?.finish()
        driver.model.session.invalidateAndCancel();window.close()
        print("RECORDED \(scene.key) \(scene.duration)s preview=\(preview)");fflush(stdout)
    }
}
