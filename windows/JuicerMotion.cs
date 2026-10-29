using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace CodexMissionManager
{
    sealed class JuicerStrokeSpec
    {
        internal readonly int Parent;
        internal readonly double[][] Points;
        internal JuicerStrokeSpec(int parent, double[][] points) { Parent=parent; Points=points; }
    }
    sealed class JuicerSceneSpec
    {
        internal readonly int Id;
        internal readonly double Gain;
        internal readonly JuicerStrokeSpec[] Strokes;
        internal JuicerSceneSpec(int id,double gain,JuicerStrokeSpec[] strokes) { Id=id;Gain=gain;Strokes=strokes; }
    }
    sealed class JuicerPoint
    {
        internal readonly double X,Y;
        internal JuicerPoint(double x,double y) { X=x;Y=y; }
        internal double[] Values { get { return new double[] {X,Y}; } }
    }
    sealed class JuicerStroke
    {
        internal int Tree,Parent,Level;
        internal double Gain,Length;
        internal List<JuicerPoint> Points,Detailed;
        internal object Export() { return new Dictionary<string,object> {
            {"tree",Tree},{"parent",Parent<0?null:(object)Parent},{"level",Level},{"gain",Gain},
            {"points",Points.Select(p=>p.Values).ToArray()},{"detailed",Detailed.Select(p=>p.Values).ToArray()}}; }
    }
    sealed class JuicerEvent
    {
        internal int Id;
        internal double Start,Duration,Rise,Gain,LengthScale;
        internal List<JuicerStroke> Paths;
        internal object Export() { return new Dictionary<string,object> {{"id",Id},{"start",Start},{"duration",Duration},
            {"rise",Rise},{"gain",Gain},{"lengthScale",LengthScale},{"paths",Paths.Select(p=>p.Export()).ToArray()}}; }
    }
    sealed class JuicerSequence
    {
        internal uint Seed;
        internal double CycleSeconds;
        internal List<JuicerEvent> Events;
        internal object Export() { return new Dictionary<string,object> {{"seed",Seed},{"cycleSeconds",CycleSeconds},
            {"events",Events.Select(e=>e.Export()).ToArray()}}; }
    }
    sealed class JuicerStrokeFrame
    {
        internal JuicerStroke Stroke;
        internal double Opacity,Progress;
    }
    static class JuicerMotion
    {
        struct Random
        {
            uint value;
            internal Random(uint seed) { value=seed; }
            internal double Next()
            {
                unchecked {
                    value+=0x6D2B79F5U;
                    uint mixed=(value^(value>>15))*(1U|value);
                    mixed^=mixed+((mixed^(mixed>>7))*(61U|mixed));
                    return (mixed^(mixed>>14))/4294967296.0;
                }
            }
        }
        static double Rounded(double value) { return Math.Floor(value*100+.5)/100; }
        internal static double Distance(JuicerPoint a,JuicerPoint b) { return Math.Sqrt((a.X-b.X)*(a.X-b.X)+(a.Y-b.Y)*(a.Y-b.Y)); }
        static string Key(int tree,double[] point) { return tree+":"+point[0].ToString("R",CultureInfo.InvariantCulture)+","+point[1].ToString("R",CultureInfo.InvariantCulture); }
        static List<JuicerStroke> Instantiate(JuicerSceneSpec scene,uint seed,out double scale)
        {
            var rng=new Random(seed);scale=.76+rng.Next()*.33;
            var transformed=new Dictionary<string,JuicerPoint>();var paths=new List<JuicerStroke>();
            for(int index=0;index<scene.Strokes.Length;index++) {
                var item=scene.Strokes[index];int tree=item.Parent<0?index:paths[item.Parent].Tree;
                var origin=scene.Strokes[tree].Points[0];
                transformed[Key(tree,origin)]=new JuicerPoint(origin[0],origin[1]);
                var points=new List<JuicerPoint>();
                for(int i=0;i<item.Points.Length;i++) {
                    var point=item.Points[i];
                    if(item.Parent<0&&i==0){points.Add(new JuicerPoint(origin[0],origin[1]));continue;}
                    string key=Key(tree,point);JuicerPoint current;
                    if(!transformed.TryGetValue(key,out current)) {
                        double x=origin[0]+(point[0]-origin[0])*scale+(rng.Next()-.5)*2.2;
                        double y=origin[1]+(point[1]-origin[1])*scale+(rng.Next()-.5)*2.2;
                        current=new JuicerPoint(Rounded(Math.Max(55,Math.Min(216,x))),Rounded(Math.Max(60,Math.Min(181,y))));
                        transformed[key]=current;
                    }
                    points.Add(current);
                }
                var detailed=new List<JuicerPoint>{points[0]};double length=0;
                for(int i=1;i<points.Count;i++) {
                    var a=points[i-1];var b=points[i];double span=Distance(a,b);
                    double bend=(rng.Next()-.5)*Math.Min(3.3,span*.28);
                    if(span>0)detailed.Add(new JuicerPoint(Rounded((a.X+b.X)/2-(b.Y-a.Y)/span*bend),Rounded((a.Y+b.Y)/2+(b.X-a.X)/span*bend)));
                    detailed.Add(b);
                }
                for(int i=1;i<detailed.Count;i++)length+=Distance(detailed[i-1],detailed[i]);
                paths.Add(new JuicerStroke {Tree=tree,Parent=item.Parent,Level=item.Parent<0?0:paths[item.Parent].Level+1,
                    Points=points,Detailed=detailed,Gain=Rounded(.9+rng.Next()*.1),Length=length});
            }
            return paths;
        }
        internal static JuicerSequence Sequence(uint seed)
        {
            var rng=new Random(seed);var order=Enumerable.Range(0,JuicerMotionData.Scenes.Length).ToArray();
            for(int i=order.Length-1;i>0;i--){int j=(int)Math.Floor(rng.Next()*(i+1));int swap=order[i];order[i]=order[j];order[j]=swap;}
            double time=.17;var events=new List<JuicerEvent>();
            foreach(int index in order) {
                var scene=JuicerMotionData.Scenes[index];double duration=Rounded(.29+rng.Next()*.3),rise=Rounded(.045+rng.Next()*.055),scale;
                var paths=Instantiate(scene,(uint)Math.Floor(rng.Next()*4294967296.0),out scale);
                double gain=Rounded(scene.Gain*(.88+rng.Next()*.14));
                events.Add(new JuicerEvent {Id=scene.Id,Start=Rounded(time),Duration=duration,Rise=rise,Gain=gain,LengthScale=scale,Paths=paths});
                time+=duration+.29+rng.Next()*.65;
            }
            return new JuicerSequence {Seed=seed,CycleSeconds=Math.Ceiling((time+.24)/2)*2,Events=events};
        }
        static double Interpolate(double value,double[][] stops)
        {
            if(value<=stops[0][0])return stops[0][1];
            for(int i=1;i<stops.Length;i++)if(value<=stops[i][0]){
                var a=stops[i-1];var b=stops[i];return a[1]+(b[1]-a[1])*(value-a[0])/(b[0]-a[0]);
            }
            return stops[stops.Length-1][1];
        }
        internal static List<JuicerStrokeFrame> Frame(JuicerSequence sequence,double time)
        {
            var result=new List<JuicerStrokeFrame>();
            if(Double.IsNaN(time)||Double.IsInfinity(time)||time<0)return result;
            time%=sequence.CycleSeconds;
            foreach(var e in sequence.Events) {
                double elapsed=time-e.Start;if(elapsed<0||elapsed>=e.Duration)continue;
                double opacity=Interpolate(elapsed,new double[][] {new[]{0.0,0.0},new[]{e.Rise*.48,e.Gain*.7},new[]{e.Rise,e.Gain},
                    new[]{e.Duration*.36,e.Gain*.9},new[]{e.Duration*.7,e.Gain*.24},new[]{e.Duration,0.0}});
                foreach(var stroke in e.Paths) {
                    double onset=stroke.Level*.014,grow=e.Rise*.85+stroke.Level*.004;
                    result.Add(new JuicerStrokeFrame {Stroke=stroke,Opacity=opacity*Rounded(stroke.Gain*(stroke.Level>1?.82:1)),
                        Progress=Math.Max(0,Math.Min(1,(elapsed-onset)/grow))});
                }
            }
            return result;
        }
        internal static double Breath(double seconds)
        {
            if(Double.IsNaN(seconds)||Double.IsInfinity(seconds))return 1;
            double t=(seconds%2+2)%2,x=t<=1?t:2-t,low=0,high=1;
            for(int i=0;i<24;i++) {
                double u=(low+high)/2,v=1-u,position=3*v*v*u*.42+3*v*u*u*.58+u*u*u;
                if(position<x)low=u;else high=u;
            }
            double phase=(low+high)/2;return .58+.42*(3*(1-phase)*phase*phase+phase*phase*phase);
        }
        internal static bool SelfTest()
        {
            var seq=Sequence(20261029);
            return JuicerMotionData.Scenes.Length==10&&seq.Events.Select(e=>e.Id).Distinct().Count()==10
                &&seq.Events.Select(e=>e.Id).SequenceEqual(new[]{6,7,8,4,1,3,10,2,5,9})&&seq.CycleSeconds==12
                &&Math.Abs(Breath(0)-.58)<.00001&&Math.Abs(Breath(1)-1)<.00001&&Math.Abs(Breath(2)-.58)<.00001
                &&Frame(seq,.3).Count>0&&Frame(seq,Double.NaN).Count==0;
        }
        internal static object Samples() { return new uint[]{1,17,888,20261029}.Select(seed=>Sequence(seed).Export()).ToArray(); }
    }
}
