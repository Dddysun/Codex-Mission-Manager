// TokenMax native vector identity. Display-only; never controls a chat.
using System;
using System.Collections.Generic;
using System.IO;
using System.Windows.Media.Imaging;
using System.ComponentModel;
using System.Diagnostics;
using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace CodexMissionManager
{
    sealed class JuicerLogo : FrameworkElement
    {
        readonly DispatcherTimer animation;
        readonly Stopwatch clock = new Stopwatch();
        string state = "idle";
        bool dark, subscribed;
        static readonly Geometry Handle = Shape("M180,78 H199 Q229,78 226,110 L223,128 Q220,156 176,153");
        static readonly Geometry Cup = Shape("M62,63 H193 L181,158 Q179,177 160,177 H94 Q75,177 73,158 Z");
        static readonly Geometry Glass = Shape("M78,76 H177 L166,155 Q165,163 155,163 H99 Q89,163 88,155 Z");
        static readonly Geometry Base = Shape("M88,182 H166 Q183,182 187,199 L190,212 Q192,222 180,222 H74 Q62,222 64,212 L67,199 Q71,182 88,182 Z");
        static readonly Geometry Bolt = Shape("M129,91 H151 L133,116 H153 L113,153 L124,126 H104 Z");
        static readonly Geometry Pause = Shape("M115,94 V135 M139,94 V135");
        static readonly Geometry Disconnect = Shape("M119,98 L115,94 C110,89 102,91 100,98 C99,102 100,106 104,109 L113,118 M136,111 L145,120 C150,125 150,132 145,136 C140,140 134,138 130,134 L126,130 M111,135 L143,94");
        static readonly Geometry Error = Shape("M122,89 H134 L132,122 H124 Z");
        JuicerSequence sequence;
        double cycleStarted;
        double? fixtureTime;
        readonly Random cosmeticRandom = new Random();
        void EnsureSequence(double seconds) {
            if (sequence == null || seconds-cycleStarted >= sequence.CycleSeconds || seconds<cycleStarted) {
                sequence=JuicerMotion.Sequence((uint)cosmeticRandom.Next(1,Int32.MaxValue));cycleStarted=seconds;
            }
        }
        public JuicerLogo()
        {
            Width = 52; Height = 52; IsHitTestVisible = false;
            animation = new DispatcherTimer(DispatcherPriority.Render) { Interval = TimeSpan.FromSeconds(1.0 / 24) };
            animation.Tick += delegate { InvalidateVisual(); };
            Loaded += delegate { if (!subscribed) { SystemParameters.StaticPropertyChanged += SystemPreferenceChanged; subscribed = true; } RefreshAnimation(); };
            Unloaded += delegate { animation.Stop(); clock.Stop(); if (subscribed) { SystemParameters.StaticPropertyChanged -= SystemPreferenceChanged; subscribed = false; } };
            IsVisibleChanged += delegate { RefreshAnimation(); };
        }
        void SystemPreferenceChanged(object sender, PropertyChangedEventArgs args)
        { if (args.PropertyName == "ClientAreaAnimation") { RefreshAnimation(); InvalidateVisual(); } }
        public void SetPresentation(string value, bool darkMode)
        {
            value = value == "working" || value == "waiting" || value == "disconnected" || value == "error" ? value : "idle";
            bool changed = state != value || dark != darkMode;
            state = value; dark = darkMode;
            if (state != "working") clock.Reset();
            RefreshAnimation(); if (changed) InvalidateVisual();
        }
        void RefreshAnimation()
        {
            bool play = IsLoaded && IsVisible && state == "working" && SystemParameters.ClientAreaAnimation;
            if (play) { clock.Start(); animation.Start(); }
            else { animation.Stop(); clock.Stop(); }
        }
        static Geometry Shape(string data) { var value = Geometry.Parse(data); value.Freeze(); return value; }
        static Brush Color(string hex) { var value = new SolidColorBrush((System.Windows.Media.Color)ColorConverter.ConvertFromString(hex)); value.Freeze(); return value; }
        static Pen Stroke(Brush brush, double width)
        { var pen = new Pen(brush, width) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, LineJoin = PenLineJoin.Round }; pen.Freeze(); return pen; }
        public static string BodyColor(bool dark, string state)
        { return state == "idle" || state == "disconnected" ? (dark ? "#637285" : "#758598") : (dark ? "#5386BF" : "#2168D5"); }
        public static string ResolveState(bool paused, bool running, bool connected, bool healthy, bool available,
            string serviceError, bool usageStale, string quotaState, bool blocked, string phase, bool enabled)
        {
            if (paused || !running) return "idle";
            if (!connected) return "disconnected";
            if (!String.IsNullOrEmpty(serviceError)) return "error";
            if (!healthy || !available || usageStale || quotaState == "unknown") return "disconnected";
            if (blocked || phase == "low" || phase == "blocked") return "waiting";
            return enabled ? "working" : "idle";
        }
        public static bool SelfTest()
        {
            return ResolveState(true, true, true, true, true, "", false, "metered", false, "normal", true) == "idle"
                && ResolveState(false, true, true, true, true, "", false, "metered", false, "normal", true) == "working"
                && ResolveState(false, true, true, true, true, "", false, "metered", false, "low", true) == "waiting"
                && ResolveState(false, true, true, true, true, "", false, "service_only", true, "normal", true) == "waiting"
                && ResolveState(false, true, false, true, true, "", false, "metered", false, "normal", true) == "disconnected"
                && ResolveState(false, true, true, true, true, "sampling", false, "metered", false, "normal", true) == "error"
                && ResolveState(false, true, true, true, true, "", true, "metered", false, "normal", true) == "disconnected"
                && ResolveState(false, true, true, true, false, "", false, "metered", false, "normal", true) == "disconnected"
                && JuicerMotion.SelfTest() && BodyColor(true, "working") == "#5386BF" && BodyColor(true, "idle") == "#637285";
        }
        static Geometry Partial(JuicerStroke stroke, double progress) {
            var geometry=new StreamGeometry();
            using(var path=geometry.Open()) {
                var points=stroke.Detailed;path.BeginFigure(new Point(points[0].X,points[0].Y),false,false);
                double remaining=stroke.Length*progress;
                for(int i=1;i<points.Count && remaining>0;i++) {
                    var a=points[i-1];var b=points[i];double span=JuicerMotion.Distance(a,b);
                    double fraction=span>0 ? Math.Min(1,remaining/span):1;
                    path.LineTo(new Point(a.X+(b.X-a.X)*fraction,a.Y+(b.Y-a.Y)*fraction),true,false);remaining-=span;
                }
            }
            geometry.Freeze();return geometry;
        }
        void DrawDischarge(DrawingContext dc, Brush gold, Brush core, double seconds) {
            EnsureSequence(seconds);
            foreach(var frame in JuicerMotion.Frame(sequence,seconds-cycleStarted)) {
                if(frame.Opacity<=0 || frame.Progress<=0)continue;
                var path=Partial(frame.Stroke,frame.Progress);int level=frame.Stroke.Level;
                double[] widths={6.5,level==0 ? 2.4:level==1 ? 1.6:1.2,level==0 ? 1.3:level==1 ? .86:.62};
                double[] alphas={.17,.98,1};
                for(int i=0;i<widths.Length;i++) {
                    dc.PushOpacity(frame.Opacity*alphas[i]);dc.DrawGeometry(null,Stroke(i==2 ? core:gold,widths[i]),path);dc.Pop();
                }
            }
        }
        // Offline native rendering: no tray, backend, user preferences or chats.
        public static void ExportMotion(string directory) {
            Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory,"motion.json"),Json.Stringify(JuicerMotion.Samples()),new System.Text.UTF8Encoding(false));
            var logo=new JuicerLogo();logo.state="working";logo.dark=true;
            logo.sequence=JuicerMotion.Sequence(20261029);logo.cycleStarted=0;
            var times=new List<double>{0,1,2};foreach(var ev in logo.sequence.Events)times.Add(ev.Start+ev.Rise);
            for(int i=0;i<times.Count;i++) {
                logo.fixtureTime=times[i];logo.Measure(new Size(384,384));logo.Arrange(new Rect(0,0,384,384));logo.InvalidateVisual();logo.UpdateLayout();
                var bitmap=new RenderTargetBitmap(384,384,96,96,PixelFormats.Pbgra32);bitmap.Render(logo);
                var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bitmap));
                using(var file=File.Create(Path.Combine(directory,"frame-"+i+".png")))png.Save(file);
            }
        }
        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);
            double size = Math.Min(ActualWidth, ActualHeight); if (size <= 0) return;
            bool working = state == "working", moving = working && (fixtureTime.HasValue || SystemParameters.ClientAreaAnimation);
            var body = Color(BodyColor(dark, state)); var glass = Color(state == "idle" ? (dark ? "#202A38" : "#EFF1F4") : (dark ? "#20344C" : "#EAF3FF"));
            var gray = Color(dark ? "#7F8C9C" : "#8795A8"); var gold = Color(dark ? "#F2BA42" : "#F5B82E");
            var core = Color(dark ? "#FFF5DD" : "#FFF8E7");
            double seconds = fixtureTime ?? (moving ? clock.Elapsed.TotalSeconds : 0);
            dc.PushTransform(new TranslateTransform((ActualWidth - size) / 2, (ActualHeight - size) / 2));
            dc.PushTransform(new ScaleTransform(size / 256, size / 256));
            dc.DrawGeometry(null, Stroke(body, 15), Handle); dc.DrawGeometry(body, null, Cup); dc.DrawGeometry(glass, null, Glass);
            dc.DrawRoundedRectangle(body, null, new Rect(57, 48, 142, 22), 11, 11);
            dc.DrawRoundedRectangle(body, null, new Rect(110, 29, 35, 14), 6, 6);
            dc.DrawEllipse(glass, null, new Point(127, 36), 5, 5); dc.DrawLine(Stroke(body, 2.5), new Point(127, 32), new Point(127, 36));
            dc.DrawGeometry(body, null, Base); dc.DrawEllipse(glass, null, new Point(127, 202), 10, 10); dc.DrawLine(Stroke(body, 3), new Point(127, 196), new Point(127, 201));
            if (moving) DrawDischarge(dc,gold,core,seconds);
            if (state == "waiting") dc.DrawGeometry(null, Stroke(gold, 10), Pause);
            else if (state == "disconnected") dc.DrawGeometry(null, Stroke(gray, 6), Disconnect);
            else if (state == "error") { var red = Color(dark ? "#D67A80" : "#CD5058"); dc.DrawGeometry(red, null, Error); dc.DrawEllipse(red, null, new Point(128, 135), 6, 6); }
            else
            {
                dc.PushOpacity(moving ? JuicerMotion.Breath(seconds):1);
                dc.DrawGeometry(working ? gold : gray, null, Bolt);dc.Pop();
            }
            dc.Pop(); dc.Pop();
        }
    }
}
