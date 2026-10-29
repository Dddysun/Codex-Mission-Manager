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
        static readonly Geometry Bolt = Shape("M129,83 H151 L133,108 H153 L113,145 L124,118 H104 Z");
        static readonly Geometry Pause = Shape("M115,94 V135 M139,94 V135");
        static readonly Geometry Disconnect = Shape("M119,98 L115,94 C110,89 102,91 100,98 C99,102 100,106 104,109 L113,118 M136,111 L145,120 C150,125 150,132 145,136 C140,140 134,138 130,134 L126,130 M111,135 L143,94");
        static readonly Geometry Error = Shape("M122,89 H134 L132,122 H124 Z");
        static readonly Geometry EnergyBack = Shape("M48,181 C17,161 18,119 41,88 L35,78 L51,77 C66,47 109,26 149,25 L158,18 L164,28 C201,31 231,60 236,91");
        static readonly Geometry EnergyFront = Shape("M223,90 L234,99 L226,109 C244,143 229,180 199,198 L208,203 L190,205 C162,225 114,239 76,225 L66,232 L63,221 C38,211 22,191 26,174");
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
        { return state == "idle" || state == "disconnected" ? (dark ? "#637285" : "#758598") : (dark ? "#4878AF" : "#2168D5"); }
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
                && BodyColor(true, "working") == "#4878AF" && BodyColor(true, "idle") == "#637285";
        }
        static void DrawEnergy(DrawingContext dc, Geometry path, Brush gold, double seconds)
        {
            dc.PushOpacity(0.16); dc.DrawGeometry(null, Stroke(gold, 1.2), path); dc.Pop();
            // WPF dash values are multiples of stroke width, SVG values are pixels.
            var trace = new Pen(gold, 2.2) { DashStyle = new DashStyle(new[] { 38 / 2.2, 150 / 2.2, 12 / 2.2, 112 / 2.2 }, -(seconds % 2.8) / 2.8 * 312 / 2.2),
                StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, DashCap = PenLineCap.Round, LineJoin = PenLineJoin.Round };
            trace.Freeze(); dc.PushOpacity(0.8); dc.DrawGeometry(null, trace, path); dc.Pop();
        }
        protected override void OnRender(DrawingContext dc)
        {
            base.OnRender(dc);
            double size = Math.Min(ActualWidth, ActualHeight); if (size <= 0) return;
            bool working = state == "working", moving = working && SystemParameters.ClientAreaAnimation;
            var body = Color(BodyColor(dark, state)); var glass = Color(state == "idle" ? (dark ? "#202A38" : "#EFF1F4") : (dark ? "#172638" : "#EAF3FF"));
            var gray = Color(dark ? "#7F8C9C" : "#8795A8"); var gold = Color(dark ? "#E7B43C" : "#E7AA16");
            double seconds = moving ? clock.Elapsed.TotalSeconds : 0;
            dc.PushTransform(new TranslateTransform((ActualWidth - size) / 2, (ActualHeight - size) / 2));
            dc.PushTransform(new ScaleTransform(size / 256, size / 256));
            if (working) DrawEnergy(dc, EnergyBack, gold, seconds);
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
                dc.PushOpacity(moving ? 0.62 + 0.38 * breath : 1);
                double scale = moving ? 0.97 + 0.06 * breath : 1;
                dc.PushTransform(new ScaleTransform(scale, scale, 128, 114)); dc.DrawGeometry(working ? gold : gray, null, Bolt); dc.Pop(); dc.Pop();
            }
            if (working) DrawEnergy(dc, EnergyFront, gold, seconds);
            dc.Pop(); dc.Pop();
        }
    }
}
