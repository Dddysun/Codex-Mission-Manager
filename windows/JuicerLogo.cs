// TokenMax native vector identity. Display-only; never controls a chat.
using System;
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
        static readonly Geometry EnergyBack = Shape("M74,214 L57,197 L61,184 L43,169 L49,154 L33,137 L42,123 L35,103 L51,89 L46,73 L64,61");
        static readonly Geometry EnergyFront = Shape("M153,38 L177,46 L174,55 L203,66 L213,83 L205,96 L229,113 L220,127 L230,143 L216,157 L221,175 L199,187 L202,199 L178,208 L153,215 L137,207 L109,221 L90,214");
        static readonly Geometry BranchLeft = Shape("M49,154 L62,144 L58,131");
        static readonly Geometry BranchTop = Shape("M213,83 L232,78 L237,59");
        static readonly Geometry BranchBase = Shape("M199,187 L215,199 L226,195");
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
                && BodyColor(true, "working") == "#5386BF" && BodyColor(true, "idle") == "#637285";
        }
        static void DrawEnergy(DrawingContext dc, Geometry path, Brush gold, Brush core, double seconds, double offset = 0, bool branch = false)
        {
            double phase = -130 * ((seconds / 1.8 + offset) % 1);
            double[] widths = { 9, 4.5, 2.4, 0.85 }, opacity = { 0.12, 0.28, 0.92, 0.95 };
            double[] pattern = branch ? new double[] { 18, 10, 5, 22 } : new double[] { 62, 18, 14, 36 };
            for (int i = 0; i < widths.Length; i++)
            {
                double w = widths[i]; var dashes = new DoubleCollection(); foreach (double value in pattern) dashes.Add(value / w);
                var trace = new Pen(i == 3 ? core : gold, w) { DashStyle = new DashStyle(dashes, phase / w),
                    StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, DashCap = PenLineCap.Round, LineJoin = PenLineJoin.Round };
                trace.Freeze(); dc.PushOpacity(opacity[i] * (branch ? 0.65 : 1)); dc.DrawGeometry(null, trace, path); dc.Pop();
            }
        }
        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);
            double size = Math.Min(ActualWidth, ActualHeight); if (size <= 0) return;
            bool working = state == "working", moving = working && SystemParameters.ClientAreaAnimation;
            var body = Color(BodyColor(dark, state)); var glass = Color(state == "idle" ? (dark ? "#202A38" : "#EFF1F4") : (dark ? "#20344C" : "#EAF3FF"));
            var gray = Color(dark ? "#7F8C9C" : "#8795A8"); var gold = Color(dark ? "#F2BA42" : "#F5B82E");
            var core = Color(dark ? "#FFE6A8" : "#FFF2C9");
            double seconds = moving ? clock.Elapsed.TotalSeconds : 0;
            dc.PushTransform(new TranslateTransform((ActualWidth - size) / 2, (ActualHeight - size) / 2));
            dc.PushTransform(new ScaleTransform(size / 256, size / 256));
            if (working) { DrawEnergy(dc, EnergyBack, gold, core, seconds, 0.35); DrawEnergy(dc, BranchLeft, gold, core, seconds, 0.35, true); }
            dc.DrawGeometry(null, Stroke(body, 15), Handle); dc.DrawGeometry(body, null, Cup); dc.DrawGeometry(glass, null, Glass);
            dc.DrawRoundedRectangle(body, null, new Rect(57, 48, 142, 22), 11, 11);
            dc.DrawRoundedRectangle(body, null, new Rect(110, 29, 35, 14), 6, 6);
            dc.PushTransform(new RotateTransform(seconds / 3.2 * 360, 127, 36)); dc.DrawEllipse(glass, null, new Point(127, 36), 5, 5); dc.DrawLine(Stroke(body, 2.5), new Point(127, 32), new Point(127, 36)); dc.Pop();
            dc.DrawGeometry(body, null, Base); dc.DrawEllipse(glass, null, new Point(127, 202), 10, 10); dc.DrawLine(Stroke(body, 3), new Point(127, 196), new Point(127, 201));
            if (state == "waiting") dc.DrawGeometry(null, Stroke(gold, 10), Pause);
            else if (state == "disconnected") dc.DrawGeometry(null, Stroke(gray, 6), Disconnect);
            else if (state == "error") { var red = Color(dark ? "#D67A80" : "#CD5058"); dc.DrawGeometry(red, null, Error); dc.DrawEllipse(red, null, new Point(128, 135), 6, 6); }
            else
            {
                double breath = moving ? (1 - Math.Cos(seconds / 2.4 * Math.PI * 2)) / 2 : 1;
                dc.PushOpacity(moving ? 0.78 + 0.22 * breath : 1);
                double scale = moving ? 0.985 + 0.03 * breath : 1;
                dc.PushTransform(new ScaleTransform(scale, scale, 128, 122)); dc.DrawGeometry(working ? gold : gray, null, Bolt); dc.Pop(); dc.Pop();
            }
            if (working) { DrawEnergy(dc, EnergyFront, gold, core, seconds); DrawEnergy(dc, BranchTop, gold, core, seconds, 0, true); DrawEnergy(dc, BranchBase, gold, core, seconds, 0.6, true); }
            dc.Pop(); dc.Pop();
        }
    }
}
