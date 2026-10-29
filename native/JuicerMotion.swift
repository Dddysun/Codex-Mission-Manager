import Foundation

struct JuicerStrokeSpec { let parent:Int?; let points:[[Double]] }
struct JuicerSceneSpec { let id:Int; let gain:Double; let strokes:[JuicerStrokeSpec] }
struct JuicerPoint { let x:Double; let y:Double; var array:[Double] {[x,y]} }
struct JuicerStroke {
    let tree:Int, parent:Int?, level:Int
    let points:[JuicerPoint], detailed:[JuicerPoint]
    let gain:Double
    var dictionary:[String:Any] { ["tree":tree,"parent":parent.map{ $0 as Any } ?? NSNull(),"level":level,
        "points":points.map(\.array),"detailed":detailed.map(\.array),"gain":gain] }
}
struct JuicerEvent {
    let id:Int
    let start:Double, duration:Double, rise:Double, gain:Double, lengthScale:Double
    let paths:[JuicerStroke]
    var dictionary:[String:Any] { ["id":id,"start":start,"duration":duration,"rise":rise,
        "gain":gain,"lengthScale":lengthScale,"paths":paths.map(\.dictionary)] }
}
struct JuicerSequence {
    let seed:UInt32, cycleSeconds:Double
    let events:[JuicerEvent]
    var dictionary:[String:Any] { ["seed":seed,"cycleSeconds":cycleSeconds,"events":events.map(\.dictionary)] }
}
struct JuicerStrokeFrame { let stroke:JuicerStroke; let opacity:Double; let progress:Double }

enum JuicerMotion {
    struct Random {
        var value:UInt32
        mutating func next()->Double {
            value = value &+ 0x6D2B79F5
            var mixed=(value ^ (value >> 15)) &* (1 | value)
            mixed ^= mixed &+ ((mixed ^ (mixed >> 7)) &* (61 | mixed))
            return Double(mixed ^ (mixed >> 14))/4294967296
        }
    }
    static func rounded(_ value:Double)->Double { floor(value*100+0.5)/100 }
    static func distance(_ a:JuicerPoint,_ b:JuicerPoint)->Double { hypot(a.x-b.x,a.y-b.y) }
    static func instantiate(_ scene:JuicerSceneSpec,seed:UInt32)->(Double,[JuicerStroke]) {
        var rng=Random(value:seed)
        let scale=0.76+rng.next()*0.33
        var transformed=[String:JuicerPoint](), paths=[JuicerStroke]()
        func key(_ tree:Int,_ point:[Double])->String { "\(tree):\(point[0]),\(point[1])" }
        for (index,item) in scene.strokes.enumerated() {
            let tree=item.parent.map{paths[$0].tree} ?? index
            let origin=scene.strokes[tree].points[0]
            transformed[key(tree,origin)]=JuicerPoint(x:origin[0],y:origin[1])
            var points=[JuicerPoint]()
            for (i,point) in item.points.enumerated() {
                if item.parent == nil && i == 0 { points.append(JuicerPoint(x:origin[0],y:origin[1]));continue }
                let cacheKey=key(tree,point)
                if transformed[cacheKey] == nil {
                    let x=origin[0]+(point[0]-origin[0])*scale+(rng.next()-0.5)*2.2
                    let y=origin[1]+(point[1]-origin[1])*scale+(rng.next()-0.5)*2.2
                    transformed[cacheKey]=JuicerPoint(x:rounded(max(55,min(216,x))),y:rounded(max(60,min(181,y))))
                }
                points.append(transformed[cacheKey]!)
            }
            var detailed=[points[0]]
            for i in 1..<points.count {
                let a=points[i-1], b=points[i], span=distance(a,b)
                let bend=(rng.next()-0.5)*min(3.3,span*0.28)
                if span > 0 {
                    detailed.append(JuicerPoint(x:rounded((a.x+b.x)/2-(b.y-a.y)/span*bend),
                                                y:rounded((a.y+b.y)/2+(b.x-a.x)/span*bend)))
                }
                detailed.append(b)
            }
            paths.append(JuicerStroke(tree:tree,parent:item.parent,level:item.parent.map{paths[$0].level+1} ?? 0,
                points:points,detailed:detailed,gain:rounded(0.9+rng.next()*0.1)))
        }
        return (scale,paths)
    }
    static func sequence(seed:UInt32)->JuicerSequence {
        var rng=Random(value:seed), order=Array(JuicerMotionData.scenes.indices)
        for i in stride(from:order.count-1,through:1,by:-1) {
            let j=Int(floor(rng.next()*Double(i+1)));order.swapAt(i,j)
        }
        var time=0.17, events=[JuicerEvent]()
        for index in order {
            let scene=JuicerMotionData.scenes[index]
            let duration=rounded(0.29+rng.next()*0.3),rise=rounded(0.045+rng.next()*0.055)
            let result=instantiate(scene,seed:UInt32(floor(rng.next()*4294967296)))
            let gain=rounded(scene.gain*(0.88+rng.next()*0.14))
            events.append(JuicerEvent(id:scene.id,start:rounded(time),duration:duration,rise:rise,gain:gain,lengthScale:result.0,paths:result.1))
            time += duration+0.29+rng.next()*0.65
        }
        return JuicerSequence(seed:seed,cycleSeconds:ceil((time+0.24)/2)*2,events:events)
    }
    static func interpolate(_ value:Double,_ stops:[(Double,Double)])->Double {
        if value <= stops[0].0 { return stops[0].1 }
        for index in 1..<stops.count where value <= stops[index].0 {
            let a=stops[index-1],b=stops[index]
            return a.1+(b.1-a.1)*(value-a.0)/(b.0-a.0)
        }
        return stops.last!.1
    }
    static func frame(_ sequence:JuicerSequence,at time:Double)->[JuicerStrokeFrame] {
        guard time.isFinite && time >= 0 else { return [] }
        let time=time.truncatingRemainder(dividingBy:sequence.cycleSeconds)
        var result=[JuicerStrokeFrame]()
        for event in sequence.events {
            let elapsed=time-event.start
            if elapsed < 0 || elapsed >= event.duration { continue }
            let opacity=interpolate(elapsed,[(0,0),(event.rise*0.48,event.gain*0.7),
                (event.rise,event.gain),(event.duration*0.36,event.gain*0.9),
                (event.duration*0.7,event.gain*0.24),(event.duration,0)])
            for stroke in event.paths {
                let onset=Double(stroke.level)*0.014
                let grow=event.rise*0.85+Double(stroke.level)*0.004
                let progress=max(0,min(1,(elapsed-onset)/grow))
                result.append(JuicerStrokeFrame(stroke:stroke,opacity:opacity*rounded(stroke.gain*(stroke.level>1 ? 0.82:1)),progress:progress))
            }
        }
        return result
    }
    // CSS ease-in-out (.42,0,.58,1), one second up and one second down.
    static func breath(_ seconds:Double)->Double {
        guard seconds.isFinite else { return 1 }
        let t=(seconds.truncatingRemainder(dividingBy:2)+2).truncatingRemainder(dividingBy:2)
        let x=t<=1 ? t:2-t
        var low=0.0,high=1.0
        for _ in 0..<24 {
            let u=(low+high)/2, v=1-u
            let position=3*v*v*u*0.42+3*v*u*u*0.58+u*u*u
            if position<x {low=u}else{high=u}
        }
        let u=(low+high)/2
        return 0.58+0.42*(3*(1-u)*u*u+u*u*u)
    }
    static func selfTest()->Bool {
        let seq=sequence(seed:20261029)
        return JuicerMotionData.scenes.count == 10 && Set(seq.events.map(\.id)).count == 10
            && seq.events.map(\.id) == [6,7,8,4,1,3,10,2,5,9] && seq.cycleSeconds == 12
            && abs(breath(0)-0.58)<0.00001 && abs(breath(1)-1)<0.00001 && abs(breath(2)-0.58)<0.00001
            && frame(seq,at:0.3).count>0 && frame(seq,at:Double.nan).isEmpty
    }
    static var samples:[[String:Any]] { [UInt32(1),17,888,20261029].map{sequence(seed:$0).dictionary} }
}
