// Native Windows preview. Built with the Windows .NET Framework C# 5 compiler.
// The UI never runs inference or bypasses backend permission/identity checks.
using System;
using System.Collections;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;
using Forms = System.Windows.Forms;

namespace CodexMissionManager
{
    static class Json
    {
        public static JavaScriptSerializer Serializer()
        {
            return new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024, RecursionLimit = 100 };
        }
        public static Dictionary<string, object> Parse(string text) { return Object(Serializer().DeserializeObject(text)); }
        public static string Stringify(object value) { return Serializer().Serialize(value); }
        public static Dictionary<string, object> Object(object value)
        {
            return value as Dictionary<string, object> ?? new Dictionary<string, object>();
        }
        public static object Get(Dictionary<string, object> value, string key)
        {
            object result; return value != null && value.TryGetValue(key, out result) ? result : null;
        }
        public static Dictionary<string, object> Child(Dictionary<string, object> value, string key) { return Object(Get(value, key)); }
        public static string Text(Dictionary<string, object> value, string key, string fallback = "")
        {
            object result = Get(value, key); return result as string ?? fallback;
        }
        public static bool Bool(Dictionary<string, object> value, string key, bool fallback = false)
        {
            object result = Get(value, key); return result is bool ? (bool)result : fallback;
        }
        public static double Number(Dictionary<string, object> value, string key, double fallback = 0)
        {
            object result = Get(value, key);
            if (result == null || result is bool) return fallback;
            try { return Convert.ToDouble(result, CultureInfo.InvariantCulture); } catch { return fallback; }
        }
        public static int Integer(Dictionary<string, object> value, string key, int fallback = 0)
        {
            return (int)Number(value, key, fallback);
        }
        public static List<Dictionary<string, object>> Rows(Dictionary<string, object> value, string key)
        {
            IEnumerable list = Get(value, key) as IEnumerable;
            var result = new List<Dictionary<string, object>>();
            if (list == null || list is string) return result;
            foreach (object item in list) if (item is Dictionary<string, object>) result.Add(Object(item));
            return result;
        }
        public static Dictionary<string, object> Values(params object[] values)
        {
            var result = new Dictionary<string, object>();
            for (int i = 0; i + 1 < values.Length; i += 2) result[(string)values[i]] = values[i + 1];
            return result;
        }
    }

    sealed class Preferences
    {
        public string Language = CultureInfo.CurrentUICulture.Name.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh" : "en";
        public string Theme = "system";
        public bool Notifications;
        public bool KeepAwake;
        public readonly string DirectoryPath;
        public Preferences(bool readPersisted = true)
        {
            DirectoryPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CodexMissionManager");
            if (!readPersisted) return;
            try
            {
                var data = Json.Parse(File.ReadAllText(Path.Combine(DirectoryPath, "native-preferences.json")));
                Language = Json.Text(data, "language", Language); Theme = Json.Text(data, "theme", "system");
                Notifications = Json.Bool(data, "notifications");
                KeepAwake = Json.Bool(data, "keep_awake");
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            catch (ArgumentException) { }
        }
        public void Save()
        {
            try
            {
                Directory.CreateDirectory(DirectoryPath);
                string file = Path.Combine(DirectoryPath, "native-preferences.json");
                File.WriteAllText(file + ".tmp", Json.Stringify(Json.Values("language", Language, "theme", Theme, "notifications", Notifications, "keep_awake", KeepAwake)), new UTF8Encoding(false));
                if (File.Exists(file)) File.Replace(file + ".tmp", file, null);
                else File.Move(file + ".tmp", file);
            }
            catch (Exception) { }
        }
    }

    sealed class MissionWindow : Window
    {
        readonly Preferences preferences;
        readonly bool fixtureMode;
        readonly Dictionary<string, ChatRow> rowCache = new Dictionary<string, ChatRow>();
        readonly CookieContainer cookies = new CookieContainer();
        readonly HashSet<string> notificationKeys = new HashSet<string>();
        readonly HttpClient client;
        Dictionary<string, object> snapshot = new Dictionary<string, object>();
        Process host;
        Uri baseUri;
        Forms.NotifyIcon tray;
        System.Drawing.Icon trayBrandIcon;
        DispatcherTimer timer;
        bool refreshing, busy, quitting, firstNotices = true;
        string notice = "", connectionError = "", currentView = "tasks", source = "all", search = "";
        string statusFilter = "all";
        Brush background, surface, foreground, secondary, border, accent, accentText, sideBackground, groupSurface;
        Grid root;
        StackPanel sidebar, quotaPanel, content;
        StackPanel accountPanel;
        Grid pageRoot, mainWorkspace;
        ContentControl pageHost;
        Border noticeBanner, connectionBanner;
        TextBlock breadcrumb, lastSync, navCount;
        readonly TextBlock[] statValues = new TextBlock[4];
        readonly Dictionary<string, Button> navButtons = new Dictionary<string, Button>();
        readonly Dictionary<string, Draft> drafts = new Dictionary<string, Draft>();
        TextBlock noticeBlock, stateBlock, syncBlock;
        Button globalButton;
        StackPanel rowsPanel;
        TextBox searchBox;
        ComboBox filterBox;
        Window settingsWindow, trayPanelWindow;

        sealed class Draft { public string Text; public int Revision; }

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint SetThreadExecutionState(uint flags);
        const uint ExecutionContinuous = 0x80000000;
        const uint ExecutionSystemRequired = 0x00000001;

        public MissionWindow(bool fixture, Dictionary<string, object> initial, string fixtureLanguage = "zh", string fixtureTheme = "system")
        {
            fixtureMode = fixture;
            preferences = new Preferences(!fixture);
            if (fixture)
            {
                if (fixtureLanguage != "zh" && fixtureLanguage != "en") throw new ArgumentException("Fixture language must be zh or en.");
                if (fixtureTheme != "system" && fixtureTheme != "light" && fixtureTheme != "dark") throw new ArgumentException("Fixture theme must be system, light or dark.");
                // Preview choices never load or save the real user's settings.
                preferences.Language = fixtureLanguage; preferences.Theme = fixtureTheme;
            }
            if (initial != null) snapshot = initial;
            var handler = new HttpClientHandler { CookieContainer = cookies, UseCookies = true, UseProxy = false };
            client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(20) };
            Width = 1380; Height = 900; MinWidth = 1080; MinHeight = 660;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI"); FontSize = 13;
            Title = T("任务管家", "Mission Manager");
            Closing += OnClosing;
            ApplyTheme(); BuildShell(); RenderSnapshot();
            if (!fixtureMode)
            {
                if (preferences.KeepAwake) SetAwake(true);
                BuildTray();
                timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
                timer.Tick += async delegate { await RefreshAsync(); ReadNotifications(); CheckSystemTheme(); };
                timer.Start();
                Loaded += delegate { StartHost(); };
            }
        }
        public string T(string chinese, string english) { return preferences.Language == "en" ? english : chinese; }
        public Brush ForegroundBrush { get { return foreground; } }
        public Brush SecondaryBrush { get { return secondary; } }
        public Brush SurfaceBrush { get { return surface; } }
        public Brush CardBorderBrush { get { return border; } }
        public Brush AccentBrush { get { return accent; } }
        public Brush StageBrush { get { return Tint(accent, 0.05); } }
        public bool IsDark { get { return dark; } }
        public bool IsBusy { get { return busy; } }
        public bool BackendConnected { get { return fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError)); } }
        public bool CanSubmitLocalChange { get { return fixtureMode || (!quitting && baseUri != null); } }
        public bool Healthy { get { return (fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError))) && Json.Bool(snapshot, "healthy") && !Json.Bool(snapshot, "stale", true); } }
        public bool ControlAvailable { get { return Json.Bool(snapshot, "control_available", true); } }
        public Dictionary<string, object> Snapshot { get { return snapshot; } }
        bool SystemDark()
        {
            try { return Convert.ToInt32(Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1)) == 0; }
            catch { return false; }
        }
        bool dark;
        void ApplyTheme()
        {
            dark = preferences.Theme == "dark" || (preferences.Theme == "system" && SystemDark());
            background = ColorBrush(dark ? "#323232" : "#ECECEC"); surface = ColorBrush(dark ? "#1E1E1E" : "#FFFFFF");
            groupSurface = ColorBrush(dark ? "#252525" : "#F7F7F7");
            foreground = ColorBrush(dark ? "#DCDCDC" : "#262626"); secondary = ColorBrush(dark ? "#9E9E9E" : "#808080");
            border = ColorBrush(dark ? "#3D3D3D" : "#DFDFDF"); accent = ColorBrush(dark ? "#7ABA91" : "#427A5C");
            sideBackground = ColorBrush(dark ? "#0D1712" : "#192822");
            accentText = ColorBrush(dark ? "#102819" : "#FFFFFF"); Background = background; Foreground = foreground;
        }
        static Brush ColorBrush(string value) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(value)); }
        public static Brush Tint(Brush source, double opacity)
        {
            var solid = source as SolidColorBrush; Color color = solid == null ? Colors.Gray : solid.Color;
            return new SolidColorBrush(Color.FromArgb((byte)Math.Round(255 * opacity), color.R, color.G, color.B));
        }
        void CheckSystemTheme()
        {
            if (preferences.Theme == "system" && dark != SystemDark()) RebuildPresentation();
        }
        void RebuildPresentation()
        {
            ApplyTheme(); rowCache.Clear(); BuildShell(); RefreshSettingsWindow(); BuildTrayMenu(); RenderSnapshot();
        }
        public static double TextLineHeight(double size)
        { return size <= 10 ? 12 : size <= 11 ? 13 : size <= 12 ? 15 : size <= 13 ? 16 : size <= 15 ? 18 : size <= 17 ? 20 : size <= 22 ? 26 : size <= 26 ? 30 : size <= 28 ? 33 : Math.Ceiling(size * 1.2); }
        TextBlock Text(string value, double size, bool bold = false)
        {
            return new TextBlock { Text = value, FontSize = size, FontWeight = bold ? FontWeights.Bold : FontWeights.Normal,
                Foreground = foreground, TextWrapping = TextWrapping.Wrap, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, LineHeight = TextLineHeight(size), Margin = new Thickness(0, 0, 0, 8) };
        }
        public Button MakeButton(string label, Action action, bool prominent = false)
        {
            var result = new Button { Content = label, Padding = new Thickness(10, 3, 10, 3), MinHeight = 24,
                FontSize = 13, Background = prominent ? accent : ColorBrush(dark ? "#414141" : "#FFFFFF"),
                Foreground = prominent ? accentText : foreground, BorderBrush = ColorBrush(dark ? "#595959" : "#D5D5D5"), BorderThickness = new Thickness(prominent ? 0 : 1),
                Cursor = System.Windows.Input.Cursors.Hand, HorizontalContentAlignment = HorizontalAlignment.Center };
            var template = new ControlTemplate(typeof(Button));
            var frame = new FrameworkElementFactory(typeof(Border), "ButtonFrame");
            frame.SetValue(Border.CornerRadiusProperty, new CornerRadius(6));
            frame.SetBinding(Border.BackgroundProperty, ParentBinding("Background"));
            frame.SetBinding(Border.BorderBrushProperty, ParentBinding("BorderBrush")); frame.SetBinding(Border.BorderThicknessProperty, ParentBinding("BorderThickness"));
            frame.SetBinding(Border.PaddingProperty, ParentBinding("Padding"));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
            presenter.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
            presenter.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            presenter.SetBinding(ContentPresenter.ContentProperty, ParentBinding("Content"));
            frame.AppendChild(presenter); template.VisualTree = frame;
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true };
            hover.Setters.Add(new Setter(UIElement.OpacityProperty, 0.86, "ButtonFrame")); template.Triggers.Add(hover);
            var press = new Trigger { Property = System.Windows.Controls.Primitives.ButtonBase.IsPressedProperty, Value = true };
            press.Setters.Add(new Setter(UIElement.OpacityProperty, 0.66, "ButtonFrame")); template.Triggers.Add(press);
            var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.36, "ButtonFrame")); template.Triggers.Add(disabled);
            result.Template = template;
            result.Click += delegate { action(); }; return result;
        }
        static System.Windows.Data.Binding ParentBinding(string property)
        { return new System.Windows.Data.Binding(property) { RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent }; }
        public Button MakePlainButton(object label, Action action)
        {
            var button = MakeButton("", action); button.Content = label; button.Background = Brushes.Transparent;
            button.Padding = new Thickness(0); button.MinHeight = 0; button.HorizontalContentAlignment = HorizontalAlignment.Left;
            var template = new ControlTemplate(typeof(Button));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter), "PlainContent");
            presenter.SetBinding(ContentPresenter.ContentProperty, ParentBinding("Content"));
            presenter.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            template.VisualTree = presenter;
            var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.4, "PlainContent")); template.Triggers.Add(disabled);
            button.Template = template; return button;
        }
        public FrameworkElement Glyph(string name, Brush stroke, double size = 16)
        {
            var paths = new Dictionary<string, string> {
                {"shield","M12,2 L22,6 L22,13 C22,20 17,25 12,28 C7,25 2,20 2,13 L2,6 Z M6.5,14 L10.5,18 L17.5,9"},
                {"grid","M3,3 H9 V9 H3 Z M15,3 H21 V9 H15 Z M3,15 H9 V21 H3 Z M15,15 H21 V21 H15 Z"},
                {"history","M4,7 A9,9 0 1 1 3,16 M4,2 V8 H10 M12,6 V12 L16,15"},
                {"rules","M3,6 H21 M3,12 H21 M3,18 H21 M7,3 V9 M16,9 V15 M9,15 V21"},
                {"settings","M12,3 A9,9 0 1 0 12,21 A9,9 0 1 0 12,3 M12,8 A4,4 0 1 0 12,16 A4,4 0 1 0 12,8 M12,0 V4 M12,20 V24 M0,12 H4 M20,12 H24 M3,3 L6,6 M18,18 L21,21 M3,21 L6,18 M18,6 L21,3"},
                {"terminal","M2,4 H22 V20 H2 Z M6,8 L10,12 L6,16 M13,16 H18"},
                {"chat","M2,3 H17 V14 H10 L6,18 V14 H2 Z M17,7 H22 V20 H18 L15,23 V20 H11 V16"},
                {"refresh","M20,8 A9,9 0 1 0 21,15 M20,2 V8 H14"},
                {"copy","M8,2 H17 L22,7 V19 H8 Z M17,2 V7 H22 M5,6 H2 V23 H16 V21"},
                {"eye","M1,12 C5,4 19,4 23,12 C19,20 5,20 1,12 Z M12,8 A4,4 0 1 0 12,16 A4,4 0 1 0 12,8"},
                {"external","M14,2 H22 V10 M22,2 L11,13 M19,13 V22 H2 V5 H11"},
                {"power","M12,1 V12 M6,5 A9,9 0 1 0 18,5"},
                {"bell","M5,17 H19 L17,14 V9 A5,5 0 0 0 7,9 V14 Z M9,21 Q12,24 15,21"},
                {"moon","M19,16 A9,9 0 0 1 8,3 A9,9 0 1 0 19,16"},
                {"laptop","M4,3 H20 V16 H4 Z M1,20 H23 M8,20 L9,18 H15 L16,20"},
                {"network","M12,1 V5 M12,19 V23 M1,12 H5 M19,12 H23 M5,5 L8,8 M16,16 L19,19 M5,19 L8,16 M16,8 L19,5 M12,6 A6,6 0 1 0 12,18 A6,6 0 1 0 12,6"},
                {"palette","M12,2 C4,2 1,8 2,14 C3,20 9,23 13,20 C15,18 9,17 13,14 C17,11 22,17 22,10 C22,5 17,2 12,2 Z M7,7 L7,7.1 M12,5 L12,5.1 M17,8 L17,8.1"},
                {"window","M2,3 H22 V21 H2 Z M2,8 H22 M6,5.5 H6.1 M9,5.5 H9.1"},
                {"check","M4,12 L10,18 L21,5"}, {"close","M5,5 L19,19 M19,5 L5,19"},
                {"search","M10,2 A8,8 0 1 0 10,18 A8,8 0 1 0 10,2 M16,16 L23,23"},
                {"clock","M12,2 A10,10 0 1 0 12,22 A10,10 0 1 0 12,2 M12,6 V12 L17,15"},
                {"warning","M12,2 L23,22 H1 Z M12,9 V15 M12,18 V19"},
                {"info","M12,2 A10,10 0 1 0 12,22 A10,10 0 1 0 12,2 M12,10 V18 M12,6 V7"}
            };
            string geometry; if (!paths.TryGetValue(name, out geometry)) geometry = paths["info"];
            return new System.Windows.Shapes.Path { Data = Geometry.Parse(geometry), Width = size, Height = size,
                Stroke = stroke, StrokeThickness = 1.5, StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round,
                StrokeLineJoin = PenLineJoin.Round, Stretch = Stretch.Uniform, Fill = Brushes.Transparent, VerticalAlignment = VerticalAlignment.Center };
        }
        public void StyleTextBox(TextBox box)
        {
            box.Background = ColorBrush(dark ? "#1E1E1E" : "#FFFFFF"); box.Foreground = foreground; box.BorderBrush = border;
            var template = new ControlTemplate(typeof(TextBox));
            var frame = new FrameworkElementFactory(typeof(Border), "InputFrame");
            frame.SetValue(Border.CornerRadiusProperty, new CornerRadius(6)); frame.SetValue(Border.BorderThicknessProperty, new Thickness(1));
            frame.SetBinding(Border.BackgroundProperty, ParentBinding("Background")); frame.SetBinding(Border.BorderBrushProperty, ParentBinding("BorderBrush"));
            var scroll = new FrameworkElementFactory(typeof(ScrollViewer), "PART_ContentHost");
            scroll.SetBinding(FrameworkElement.MarginProperty, ParentBinding("Padding")); frame.AppendChild(scroll); template.VisualTree = frame;
            var focused = new Trigger { Property = UIElement.IsKeyboardFocusWithinProperty, Value = true };
            focused.Setters.Add(new Setter(Border.BorderBrushProperty, Tint(accent, 0.6), "InputFrame")); template.Triggers.Add(focused);
            box.Template = template;
        }
        public void StyleSwitch(CheckBox check, bool small = true)
        {
            var template = new ControlTemplate(typeof(CheckBox));
            var line = new FrameworkElementFactory(typeof(DockPanel), "SwitchRoot");
            var track = new FrameworkElementFactory(typeof(Border), "SwitchTrack");
            track.SetValue(DockPanel.DockProperty, Dock.Right);
            track.SetValue(FrameworkElement.WidthProperty, small ? 32.0 : 50.0); track.SetValue(FrameworkElement.HeightProperty, small ? 18.0 : 26.0);
            track.SetValue(Border.CornerRadiusProperty, new CornerRadius(small ? 9 : 13)); track.SetValue(Border.BackgroundProperty, ColorBrush(dark ? "#383838" : "#DDDDDF"));
            track.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            var thumb = new FrameworkElementFactory(typeof(System.Windows.Shapes.Ellipse), "SwitchThumb");
            thumb.SetValue(FrameworkElement.WidthProperty, small ? 14.0 : 22.0); thumb.SetValue(FrameworkElement.HeightProperty, small ? 14.0 : 22.0);
            thumb.SetValue(FrameworkElement.MarginProperty, new Thickness(2)); thumb.SetValue(System.Windows.Shapes.Shape.FillProperty, Brushes.White);
            thumb.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Left); track.AppendChild(thumb); line.AppendChild(track);
            var label = new FrameworkElementFactory(typeof(ContentPresenter));
            label.SetValue(FrameworkElement.MarginProperty, new Thickness(0, 0, 8, 0)); label.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            label.SetBinding(ContentPresenter.ContentProperty, new System.Windows.Data.Binding("Content") { RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent });
            line.AppendChild(label); template.VisualTree = line;
            var on = new Trigger { Property = CheckBox.IsCheckedProperty, Value = true };
            on.Setters.Add(new Setter(Border.BackgroundProperty, accent, "SwitchTrack"));
            on.Setters.Add(new Setter(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Right, "SwitchThumb")); template.Triggers.Add(on);
            var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.42, "SwitchRoot")); template.Triggers.Add(disabled);
            check.FontSize = 10; check.HorizontalAlignment = HorizontalAlignment.Left; check.Template = template;
        }
        Border Card(UIElement child, Thickness margin)
        {
            return new Border { Background = groupSurface, BorderBrush = border, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6),
                Padding = new Thickness(24), Margin = margin, Child = child };
        }
        TextBlock SideText(string value, double size = 10, bool bold = false)
        {
            return new TextBlock { Text = value, FontSize = size, Foreground = Tint(Brushes.White, bold ? 0.88 : 0.58),
                FontWeight = bold ? FontWeights.Bold : FontWeights.Normal, TextWrapping = TextWrapping.Wrap, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, LineHeight = TextLineHeight(size) };
        }
        Border DividerLine(Brush brush, Thickness margin)
        { return new Border { Height = 1, Background = brush, Margin = margin }; }
        Button Navigation(string title, string iconName, string key)
        {
            var line = new DockPanel();
            if (key == "tasks") { navCount = SideText("0", 10, true); navCount.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(navCount, Dock.Right); line.Children.Add(navCount); }
            var icon = Glyph(iconName, Tint(Brushes.White, 0.8), 15); icon.Margin = new Thickness(0, 0, 11, 0); DockPanel.SetDock(icon, Dock.Left); line.Children.Add(icon);
            line.Children.Add(SideText(title, 13, true));
            var button = MakeButton("", delegate { currentView = key; BuildContent(); });
            button.Content = line; button.Height = 40; button.Padding = new Thickness(12); button.Margin = new Thickness(0, 0, 0, 6);
            button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            var template = new ControlTemplate(typeof(Button)); var frame = new FrameworkElementFactory(typeof(Border), "NavFrame");
            frame.SetValue(Border.CornerRadiusProperty, new CornerRadius(8)); frame.SetBinding(Border.BackgroundProperty, ParentBinding("Background")); frame.SetBinding(Border.PaddingProperty, ParentBinding("Padding"));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter)); presenter.SetBinding(ContentPresenter.ContentProperty, ParentBinding("Content")); frame.AppendChild(presenter); template.VisualTree = frame;
            var hover = new Trigger { Property = UIElement.IsMouseOverProperty, Value = true }; hover.Setters.Add(new Setter(UIElement.OpacityProperty, 0.8, "NavFrame")); template.Triggers.Add(hover);
            button.Template = template; navButtons[key] = button; return button;
        }
        void UpdateNavigation()
        {
            foreach (var pair in navButtons) pair.Value.Background = pair.Key == currentView ? ColorBrush(dark ? "#2A332F" : "#35423D") : Brushes.Transparent;
            if (navCount != null) navCount.Text = Json.Rows(snapshot, "tasks").Count.ToString(CultureInfo.InvariantCulture);
            if (breadcrumb != null) breadcrumb.Text = currentView == "events" ? T("操作记录", "Activity") : currentView == "rules" ? T("运行规则", "Rules") : T("任务控制", "Task control");
        }
        void BuildShell()
        {
            Title = T("任务管家", "Mission Manager"); navButtons.Clear();
            root = new Grid { Background = background }; root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(290) });
            root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }); Content = root;
            var side = new Grid { Background = sideBackground }; side.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); side.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); root.Children.Add(side);
            sidebar = new StackPanel { Margin = new Thickness(22, 22, 22, 0) };
            var brand = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 38) };
            brand.Children.Add(new Border { Width = 50, Height = 52, CornerRadius = new CornerRadius(12), Background = Tint(Brushes.White, 0.08), Padding = new Thickness(10), Child = Glyph("shield", Tint(Brushes.White, 0.88), 28) });
            var brandText = new StackPanel { Margin = new Thickness(12, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            brandText.Children.Add(SideText(T("任务管家", "Mission Manager"), 17, true));
            var signature = SideText("M I S S I O N  /  L O C A L", 9); signature.FontFamily = new FontFamily("Consolas"); signature.Margin = new Thickness(0, 5, 0, 0); brandText.Children.Add(signature); brand.Children.Add(brandText); sidebar.Children.Add(brand);
            var workspace = SideText(T("工作空间", "Workspace"), 10); workspace.Margin = new Thickness(0, 0, 0, 22); sidebar.Children.Add(workspace);
            sidebar.Children.Add(Navigation(T("任务控制", "Task control"), "grid", "tasks"));
            sidebar.Children.Add(Navigation(T("操作记录", "Activity"), "history", "events"));
            sidebar.Children.Add(Navigation(T("运行规则", "Rules"), "rules", "rules"));
            sidebar.Children.Add(DividerLine(Tint(Brushes.White, 0.22), new Thickness(0, 16, 0, 22)));
            quotaPanel = new StackPanel(); sidebar.Children.Add(quotaPanel);
            side.Children.Add(Scroller(sidebar));
            var bottom = new StackPanel { Margin = new Thickness(22, 12, 22, 22) }; Grid.SetRow(bottom, 1); side.Children.Add(bottom);
            accountPanel = new StackPanel(); bottom.Children.Add(accountPanel);
            bottom.Children.Add(DividerLine(Tint(Brushes.White, 0.22), new Thickness(0, 22, 0, 22)));
            var settingsLine = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 4, 0, 4) };
            var gear = Glyph("settings", Tint(Brushes.White, 0.82), 16); gear.Margin = new Thickness(0, 0, 10, 0); settingsLine.Children.Add(gear); settingsLine.Children.Add(SideText(T("设置与系统权限", "Settings & permissions"), 13, true));
            bottom.Children.Add(MakePlainButton(settingsLine, ShowSettingsWindow));
            var foot = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 22, 0, 0) };
            foot.Children.Add(new System.Windows.Shapes.Ellipse { Width = 9, Height = 9, Fill = Tint(Brushes.White, 0.5), Margin = new Thickness(0, 0, 10, 0), VerticalAlignment = VerticalAlignment.Center });
            foot.Children.Add(SideText(T("关闭窗口后继续工作", "Runs after closing the window"), 10)); bottom.Children.Add(foot);
            mainWorkspace = new Grid { Margin = new Thickness(1, 0, 0, 0) }; Grid.SetColumn(mainWorkspace, 1); root.Children.Add(mainWorkspace);
            mainWorkspace.RowDefinitions.Add(new RowDefinition { Height = new GridLength(54) });
            mainWorkspace.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            mainWorkspace.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            mainWorkspace.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            var toolbar = new DockPanel { Margin = new Thickness(26, 0, 26, 0), LastChildFill = true, VerticalAlignment = VerticalAlignment.Center };
            var toolbarRight = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            lastSync = Text("", 10); lastSync.Margin = new Thickness(0, 0, 10, 0); lastSync.Foreground = secondary; lastSync.VerticalAlignment = VerticalAlignment.Center; toolbarRight.Children.Add(lastSync);
            var refresh = MakeButton("", async delegate { await RefreshAsync(); }); refresh.Content = Glyph("refresh", foreground, 14); refresh.Width = 38; refresh.Height = 24; refresh.Padding = new Thickness(9, 4, 9, 4); refresh.ToolTip = T("刷新状态", "Refresh status"); toolbarRight.Children.Add(refresh); DockPanel.SetDock(toolbarRight, Dock.Right); toolbar.Children.Add(toolbarRight);
            var trail = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            var workspaceLabel = Text(T("本机工作空间", "Local workspace"), 13); workspaceLabel.Foreground = secondary; workspaceLabel.Margin = new Thickness(0); trail.Children.Add(workspaceLabel);
            var slash = Text("/", 13); slash.Foreground = Tint(secondary, 0.5); slash.Margin = new Thickness(9, 0, 9, 0); trail.Children.Add(slash);
            breadcrumb = Text("", 13, true); breadcrumb.Margin = new Thickness(0); trail.Children.Add(breadcrumb); toolbar.Children.Add(trail);
            mainWorkspace.Children.Add(new Border { BorderBrush = Tint(secondary, 0.18), BorderThickness = new Thickness(0, 0, 0, 1), Child = toolbar });
            connectionBanner = new Border { Background = Tint(Brushes.Orange, 0.1), Padding = new Thickness(14), Visibility = Visibility.Collapsed }; Grid.SetRow(connectionBanner, 1); mainWorkspace.Children.Add(connectionBanner);
            noticeBanner = new Border { Background = Tint(accent, 0.12), Padding = new Thickness(12), Visibility = Visibility.Collapsed }; Grid.SetRow(noticeBanner, 2); mainWorkspace.Children.Add(noticeBanner);
            var noticeLine = new DockPanel(); var close = MakePlainButton(Glyph("close", secondary, 12), delegate { notice = ""; UpdateNotices(); }); DockPanel.SetDock(close, Dock.Right); noticeLine.Children.Add(close);
            var noticeIcon = Glyph("info", accent, 14); noticeIcon.Margin = new Thickness(0, 0, 10, 0); DockPanel.SetDock(noticeIcon, Dock.Left); noticeLine.Children.Add(noticeIcon);
            noticeBlock = Text("", 12); noticeBlock.Margin = new Thickness(0); noticeLine.Children.Add(noticeBlock); noticeBanner.Child = noticeLine;
            pageHost = new ContentControl { HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch }; Grid.SetRow(pageHost, 3); mainWorkspace.Children.Add(pageHost);
            BuildContent();
        }
        void UpdateNotices()
        {
            if (noticeBanner != null) { noticeBanner.Visibility = String.IsNullOrEmpty(notice) ? Visibility.Collapsed : Visibility.Visible; noticeBlock.Text = notice; }
            if (connectionBanner == null) return;
            bool connected = fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError));
            connectionBanner.Visibility = connected && Json.Bool(snapshot, "healthy") ? Visibility.Collapsed : Visibility.Visible;
            if (connectionBanner.Visibility != Visibility.Visible) return;
            var row = new DockPanel(); var check = MakeButton(T("重新检查", "Check again"), async delegate { await RefreshAsync(); }); DockPanel.SetDock(check, Dock.Right); row.Children.Add(check);
            var icon = Glyph("warning", Brushes.DarkOrange, 15); icon.Margin = new Thickness(0, 2, 10, 0); icon.VerticalAlignment = VerticalAlignment.Top; DockPanel.SetDock(icon, Dock.Left); row.Children.Add(icon);
            var copy = new StackPanel(); var title = Text(connected ? T("检查状态待恢复", "Status check pending") : T("正在连接本机后台", "Connecting to the local service"), 12, true); title.Margin = new Thickness(0, 0, 0, 4); copy.Children.Add(title);
            var description = Text(String.IsNullOrEmpty(connectionError) ? T("正在核对账号、额度和聊天状态；取得可靠状态后才能自动续接。", "Checking the account, quota and chat status. Automatic recovery requires a reliable reading.") : connectionError, 12); description.Margin = new Thickness(0); copy.Children.Add(description); row.Children.Add(copy); connectionBanner.Child = row;
        }
        void BuildContent()
        {
            if (pageHost == null) return; UpdateNavigation();
            // Cached rows may survive navigation. Detach them before replacing
            // the page so WPF never assigns a second logical parent. Drafts
            // remain in their row instances and in the owner draft cache.
            if (rowsPanel != null) rowsPanel.Children.Clear();
            rowsPanel = null; globalButton = null; stateBlock = null;
            if (currentView == "tasks") { pageHost.Content = BuildTaskPage(); }
            else
            {
                content = new StackPanel { Margin = new Thickness(26) };
                if (currentView == "events") BuildEvents(); else BuildRules();
                pageHost.Content = Scroller(content);
            }
            UpdateNotices();
        }
        Grid BuildTaskPage()
        {
            pageRoot = new Grid { Margin = new Thickness(26) };
            for (int index = 0; index < 4; index++) pageRoot.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            pageRoot.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); pageRoot.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var hero = new DockPanel();
            var controls = new StackPanel { HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
            stateBlock = Text("", 10); stateBlock.Foreground = secondary; stateBlock.TextAlignment = TextAlignment.Right; stateBlock.Margin = new Thickness(0, 0, 0, 8); controls.Children.Add(stateBlock);
            globalButton = MakeButton(T("启用自动控制", "Enable automation"), delegate { ToggleGlobal(); }); globalButton.HorizontalAlignment = HorizontalAlignment.Right; controls.Children.Add(globalButton); DockPanel.SetDock(controls, Dock.Right); hero.Children.Add(controls);
            var heading = new StackPanel(); var title = Text(T("任务控制", "Task control"), 28, true); title.Margin = new Thickness(0, 0, 0, 8); heading.Children.Add(title);
            var subtitle = Text(T("根据可用额度管理任务暂停、恢复和预约执行。", "Manage pauses, recovery and scheduled instructions using available quota."), 13); subtitle.Foreground = secondary; subtitle.Margin = new Thickness(0); heading.Children.Add(subtitle); hero.Children.Add(heading); pageRoot.Children.Add(hero);
            var statistics = new Grid();
            string[] labels = { T("聊天目录", "Chats"), T("正在执行", "Running"), T("等待恢复 / 预约", "Recovery / Scheduled"), T("需要留意", "Needs attention") };
            for (int index = 0; index < 4; index++)
            {
                statistics.ColumnDefinitions.Add(new ColumnDefinition()); var cell = new StackPanel { Margin = new Thickness(20, 14, 20, 14) };
                var label = Text(labels[index], 10); label.Foreground = secondary; label.Margin = new Thickness(0, 0, 0, 7); cell.Children.Add(label);
                statValues[index] = Text("0", 26, true); statValues[index].FontWeight = FontWeights.SemiBold; statValues[index].Margin = new Thickness(0); cell.Children.Add(statValues[index]); Grid.SetColumn(cell, index); statistics.Children.Add(cell);
            }
            var statsFrame = new Border { CornerRadius = new CornerRadius(10), Background = surface, Margin = new Thickness(0, 18, 0, 0), Child = statistics }; Grid.SetRow(statsFrame, 1); pageRoot.Children.Add(statsFrame);
            var filters = new Grid { Margin = new Thickness(0, 18, 0, 0) }; filters.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(240) }); filters.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(198) }); filters.ColumnDefinitions.Add(new ColumnDefinition());
            var sourceLine = new DockPanel(); var sourceLabel = Text(T("来源", "Source"), 13); sourceLabel.Margin = new Thickness(0, 0, 8, 0); sourceLabel.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(sourceLabel, Dock.Left); sourceLine.Children.Add(sourceLabel);
            sourceLine.Children.Add(Segments(new[] { T("全部", "All"), "Codex", "ChatGPT" }, new[] { "all", "codex", "chatgpt" }, source, delegate(string value) { source = value; BuildSourceSelection(); RenderChats(); })); filters.Children.Add(sourceLine);
            var filterLine = new DockPanel { Margin = new Thickness(8, 0, 0, 0) }; Grid.SetColumn(filterLine, 1); var filterLabel = Text(T("筛选", "Filter"), 13); filterLabel.Margin = new Thickness(0, 0, 8, 0); filterLabel.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(filterLabel, Dock.Left); filterLine.Children.Add(filterLabel);
            filterBox = Choice(new[] { T("全部状态", "All statuses"), T("等待恢复", "Waiting for recovery"), T("已预约", "Scheduled"), T("需留意", "Needs attention") });
            filterBox.SelectedIndex = statusFilter == "waiting" ? 1 : statusFilter == "scheduled" ? 2 : statusFilter == "attention" ? 3 : 0;
            filterBox.SelectionChanged += delegate { statusFilter = filterBox.SelectedIndex == 1 ? "waiting" : filterBox.SelectedIndex == 2 ? "scheduled" : filterBox.SelectedIndex == 3 ? "attention" : "all"; RenderChats(); }; filterLine.Children.Add(filterBox); filters.Children.Add(filterLine);
            var searchFrame = new Grid { Width = 240, HorizontalAlignment = HorizontalAlignment.Right }; Grid.SetColumn(searchFrame, 2);
            searchBox = new TextBox { Text = search, Height = 22, Padding = new Thickness(7, 2, 7, 2), FontSize = 12 }; StyleTextBox(searchBox); searchFrame.Children.Add(searchBox);
            var placeholder = Text(T("搜索聊天名称或 ID", "Search chats or IDs"), 12); placeholder.Foreground = secondary; placeholder.Margin = new Thickness(7, 0, 0, 0); placeholder.VerticalAlignment = VerticalAlignment.Center; placeholder.IsHitTestVisible = false; placeholder.Visibility = String.IsNullOrEmpty(search) ? Visibility.Visible : Visibility.Collapsed; searchFrame.Children.Add(placeholder);
            searchBox.TextChanged += delegate { search = searchBox.Text; placeholder.Visibility = String.IsNullOrEmpty(search) ? Visibility.Visible : Visibility.Collapsed; RenderChats(); }; filters.Children.Add(searchFrame); Grid.SetRow(filters, 2); pageRoot.Children.Add(filters);
            var columns = new Grid { Margin = new Thickness(16, 18, 16, 0) }; columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(138) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(310) });
            var first = Text(T("聊天 / 当前执行阶段", "Chat / Execution stage"), 10); first.Foreground = secondary; first.Margin = new Thickness(0); columns.Children.Add(first);
            var second = Text(T("当前状态 / 自动控制", "Status / Automatic control"), 10); second.Foreground = secondary; second.Margin = new Thickness(0); Grid.SetColumn(second, 1); columns.Children.Add(second);
            var third = Text(T("额度恢复后执行 · 一次性", "Run once after quota recovery"), 10); third.Foreground = secondary; third.Margin = new Thickness(0); Grid.SetColumn(third, 3); columns.Children.Add(third); Grid.SetRow(columns, 3); pageRoot.Children.Add(columns);
            rowsPanel = new StackPanel { Margin = new Thickness(0, 0, 4, 0) }; var list = Scroller(rowsPanel, new Thickness(0, 18, 0, 0)); Grid.SetRow(list, 4); pageRoot.Children.Add(list);
            var footer = new DockPanel { Margin = new Thickness(0, 18, 0, 0) }; syncBlock = Text("", 10); syncBlock.Foreground = secondary; syncBlock.Margin = new Thickness(0); footer.Children.Add(syncBlock);
            var directoryNote = Text(T("ChatGPT 仅目录，不自动执行", "ChatGPT directory only · Execution unavailable"), 10); directoryNote.Foreground = secondary; directoryNote.Margin = new Thickness(0); directoryNote.HorizontalAlignment = HorizontalAlignment.Right; footer.Children.Add(directoryNote); Grid.SetRow(footer, 5); pageRoot.Children.Add(footer);
            RenderHeader(); RenderChats(); return pageRoot;
        }
        readonly Dictionary<string, Button> sourceTabs = new Dictionary<string, Button>();
        FrameworkElement Segments(string[] labels, string[] values, string selected, Action<string> changed)
        {
            var grid = new Grid(); for (int index = 0; index < labels.Length; index++)
            {
                grid.ColumnDefinitions.Add(new ColumnDefinition()); string value = values[index];
                var button = MakeButton(labels[index], delegate { changed(value); }); button.Padding = new Thickness(6, 3, 6, 3); button.FontSize = 12; button.Height = 22; button.MinHeight = 22;
                button.Background = value == selected ? ColorBrush(dark ? "#555555" : "#CCCCCC") : Brushes.Transparent;
                if (values.Length == 3 && values[0] == "all") sourceTabs[value] = button;
                Grid.SetColumn(button, index); grid.Children.Add(button);
            }
            return new Border { Background = ColorBrush(dark ? "#333333" : "#EBEBEB"), CornerRadius = new CornerRadius(6), Padding = new Thickness(1), Child = grid };
        }
        void BuildSourceSelection()
        { foreach (var pair in sourceTabs) pair.Value.Background = pair.Key == source ? ColorBrush(dark ? "#555555" : "#CCCCCC") : Brushes.Transparent; }
        ComboBox Choice(string[] labels)
        {
            var combo = new ComboBox { FontSize = 12, MinHeight = 22, Height = 22, Foreground = foreground, Background = ColorBrush(dark ? "#333333" : "#EEEEEE") };
            foreach (string label in labels) combo.Items.Add(label);
            string fill = dark ? "#333333" : "#EEEEEE", popup = dark ? "#2A2A2A" : "#FFFFFF", ink = dark ? "#DDDDDD" : "#262626", stroke = dark ? "#4A4A4A" : "#DADADA";
            string xaml = @"<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' TargetType='ComboBox'><Grid><ToggleButton Foreground='"+ink+@"' Focusable='False' IsChecked='{Binding IsDropDownOpen, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}'><ToggleButton.Template><ControlTemplate TargetType='ToggleButton'><Border Background='"+fill+@"' BorderBrush='"+stroke+@"' BorderThickness='1' CornerRadius='6'><Grid><ContentPresenter TextElement.Foreground='"+ink+@"' Margin='9,1,24,1' VerticalAlignment='Center' Content='{Binding SelectionBoxItem, RelativeSource={RelativeSource AncestorType=ComboBox}}'/><Path Data='M1,4 L4,1 L7,4 M1,9 L4,12 L7,9' Stroke='"+ink+@"' StrokeThickness='1' Width='7' Height='12' Stretch='Uniform' HorizontalAlignment='Right' Margin='0,0,8,0'/></Grid></Border></ControlTemplate></ToggleButton.Template></ToggleButton><Popup x:Name='PART_Popup' AllowsTransparency='True' Placement='Bottom' IsOpen='{TemplateBinding IsDropDownOpen}' Focusable='False' PopupAnimation='None'><Border Background='"+popup+@"' TextElement.Foreground='"+ink+@"' BorderBrush='"+stroke+@"' BorderThickness='1' CornerRadius='6' Padding='4' MinWidth='{Binding ActualWidth, RelativeSource={RelativeSource TemplatedParent}}'><ScrollViewer CanContentScroll='True' HorizontalScrollBarVisibility='Disabled' VerticalScrollBarVisibility='Auto'><ItemsPresenter/></ScrollViewer></Border></Popup></Grid></ControlTemplate>";
            combo.Template = (ControlTemplate)System.Windows.Markup.XamlReader.Parse(xaml);
            var itemStyle = new Style(typeof(ComboBoxItem)); itemStyle.Setters.Add(new Setter(Control.ForegroundProperty, foreground)); itemStyle.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(8, 4, 8, 4)));
            string itemXaml = @"<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ComboBoxItem'><Border x:Name='ItemFrame' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' CornerRadius='4' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}'><ContentPresenter TextElement.Foreground='{TemplateBinding Foreground}'/></Border><ControlTemplate.Triggers><Trigger Property='IsHighlighted' Value='True'><Setter TargetName='ItemFrame' Property='Background' Value='"+(dark ? "#405447" : "#D8E6DD")+@"'/></Trigger><Trigger Property='IsSelected' Value='True'><Setter TargetName='ItemFrame' Property='Background' Value='"+(dark ? "#37483D" : "#E3EAE5")+@"'/></Trigger><Trigger Property='IsEnabled' Value='False'><Setter TargetName='ItemFrame' Property='Opacity' Value='0.45'/></Trigger></ControlTemplate.Triggers></ControlTemplate>";
            itemStyle.Setters.Add(new Setter(Control.TemplateProperty, (ControlTemplate)System.Windows.Markup.XamlReader.Parse(itemXaml))); combo.ItemContainerStyle = itemStyle; return combo;
        }
        ScrollViewer Scroller(UIElement body, Thickness? margin = null)
        {
            var scroll = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Margin = margin ?? new Thickness(0) };
            string thumb = dark ? "#666666" : "#B3B3B3";
            string template = @"<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' TargetType='ScrollViewer'><Grid Background='{TemplateBinding Background}'><ScrollContentPresenter x:Name='PART_ScrollContentPresenter' Content='{TemplateBinding Content}' ContentTemplate='{TemplateBinding ContentTemplate}' CanContentScroll='{TemplateBinding CanContentScroll}' Margin='{TemplateBinding Padding}'/><ScrollBar x:Name='PART_VerticalScrollBar' Orientation='Vertical' Width='8' HorizontalAlignment='Right' VerticalAlignment='Stretch' Minimum='0' Maximum='{TemplateBinding ScrollableHeight}' ViewportSize='{TemplateBinding ViewportHeight}' Value='{Binding VerticalOffset, RelativeSource={RelativeSource TemplatedParent}, Mode=OneWay}' Visibility='{TemplateBinding ComputedVerticalScrollBarVisibility}'><ScrollBar.Template><ControlTemplate TargetType='ScrollBar'><Grid Background='Transparent' Width='8'><Track x:Name='PART_Track' Orientation='Vertical' Minimum='{TemplateBinding Minimum}' Maximum='{TemplateBinding Maximum}' ViewportSize='{TemplateBinding ViewportSize}' Value='{Binding Value, RelativeSource={RelativeSource TemplatedParent}, Mode=TwoWay}' IsDirectionReversed='True'><Track.DecreaseRepeatButton><RepeatButton Focusable='False' Command='ScrollBar.PageUpCommand' Opacity='0'/></Track.DecreaseRepeatButton><Track.Thumb><Thumb MinHeight='24'><Thumb.Template><ControlTemplate TargetType='Thumb'><Border CornerRadius='3' Background='"+thumb+@"' Margin='1.5,2'/></ControlTemplate></Thumb.Template></Thumb></Track.Thumb><Track.IncreaseRepeatButton><RepeatButton Focusable='False' Command='ScrollBar.PageDownCommand' Opacity='0'/></Track.IncreaseRepeatButton></Track></Grid></ControlTemplate></ScrollBar.Template></ScrollBar></Grid></ControlTemplate>";
            scroll.Template = (ControlTemplate)System.Windows.Markup.XamlReader.Parse(template); return scroll;
        }
        void RenderSnapshot()
        {
            RenderQuota(); UpdateNavigation(); UpdateNotices();
            if (lastSync != null) lastSync.Text = T("最近同步 ", "Last updated ") + FormatTime(Json.Number(snapshot, "observed_at"));
            if (currentView == "tasks") { RenderHeader(); RenderChats(); }
            else if (currentView == "events" && !busy) BuildContent();
            else if (currentView == "rules") BuildContent();
            RefreshSettingsWindow(); BuildTrayMenu();
        }
        static bool Attention(Dictionary<string, object> chat)
        {
            var runtime = Json.Child(chat, "runtime"); IEnumerable flags = Json.Get(runtime, "activeFlags") as IEnumerable;
            return Json.Text(chat, "auto_connection") == "failed" || Json.Get(chat, "connection_error") != null
                || Json.Text(chat, "state") == "needs_review" || Json.Text(Json.Child(chat, "plan"), "state") == "needs_review"
                || (flags != null && flags.Cast<object>().Any()) || Json.Text(runtime, "type") == "systemError";
        }
        static bool Waiting(Dictionary<string, object> chat)
        { string value = Json.Text(chat, "state"); return value == "paused" || value == "pause_intent" || value == "resume_intent"; }
        void RenderHeader()
        {
            if (stateBlock == null || globalButton == null) return;
            bool enabled = Json.Bool(snapshot, "control_enabled") && String.IsNullOrEmpty(connectionError);
            stateBlock.Text = enabled ? T("自动控制已启用", "Automation enabled") : T("自动控制未生效", "Automation inactive");
            globalButton.Content = !Json.Bool(snapshot, "running") ? T("启动后台服务", "Start background service") : Json.Bool(snapshot, "control_paused", true) ? T("启用自动控制", "Enable automation") : T("暂停自动控制", "Pause automation");
            globalButton.IsEnabled = !busy && (fixtureMode || host == null || (baseUri != null && Json.Bool(snapshot, "running")
                && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy))));
            var chats = Json.Rows(snapshot, "tasks");
            int[] counts = { chats.Count, chats.Count(x => !Attention(x) && !Waiting(x) && Json.Text(Json.Child(x, "runtime"), "type") == "active"),
                chats.Count(x => Waiting(x) || Scheduled(Json.Child(x, "plan"))), chats.Count(Attention) };
            for (int index = 0; index < statValues.Length; index++) if (statValues[index] != null) statValues[index].Text = counts[index].ToString(CultureInfo.InvariantCulture);
        }
        string ControlConnectionNote()
        {
            string error = Json.Text(snapshot, "desktop_connection_error");
            if (error == "desktop_version_not_verified") return T("当前 Windows 客户端版本尚未通过控制核验", "This Windows client version has not passed control verification");
            if (error == "desktop_control_disabled") return T("本机客户端控制通道尚未启用", "The local client-control channel is not enabled");
            return T("额度与目录已连接，客户端控制待恢复", "Usage and directory are connected; client control is unavailable");
        }
        public static bool Scheduled(Dictionary<string, object> plan) { string s = Json.Text(plan, "state"); return s == "armed" || s == "sending"; }
        void RenderChats()
        {
            if (rowsPanel == null || currentView != "tasks") return;
            var all = Json.Rows(snapshot, "tasks");
            var filtered = all.Where(x => (source == "all" || Json.Text(x, "category", "codex") == source)
                && (String.IsNullOrWhiteSpace(search) || (Json.Text(x, "name") + " " + Json.Text(x, "id")).IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0)
                && (statusFilter == "all" || statusFilter == "waiting" && (Waiting(x) || Scheduled(Json.Child(x, "plan")))
                    || statusFilter == "scheduled" && Scheduled(Json.Child(x, "plan")) || statusFilter == "attention" && Attention(x))).ToList();
            var wanted = new List<UIElement>();
            foreach (var chat in filtered)
            {
                string key = Json.Text(chat, "key"); ChatRow row;
                if (!rowCache.TryGetValue(key, out row)) { row = new ChatRow(this); rowCache[key] = row; }
                row.Update(chat); wanted.Add(row);
            }
            if (wanted.Count == 0)
            {
                var empty = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(30) };
                empty.Children.Add(Glyph("chat", secondary, 38));
                var title = Text(snapshot.Count == 0 ? T("正在读取聊天目录", "Reading the chat directory") : T("没有匹配的聊天", "No matching chats"), 17, true); title.TextAlignment = TextAlignment.Center; title.Margin = new Thickness(0, 14, 0, 8); empty.Children.Add(title);
                var note = Text(T("Codex 目录随后台更新；ChatGPT 仅显示已知目录。", "The Codex directory follows background updates. ChatGPT shows known entries only."), 12); note.Foreground = secondary; note.TextAlignment = TextAlignment.Center; empty.Children.Add(note);
                wanted.Add(new Border { MinHeight = 220, Child = empty });
            }
            bool same = rowsPanel.Children.Count == wanted.Count;
            if (same) for (int index = 0; index < wanted.Count; index++) if (rowsPanel.Children[index] != wanted[index]) same = false;
            if (!same && !rowsPanel.IsKeyboardFocusWithin) { rowsPanel.Children.Clear(); foreach (var element in wanted) rowsPanel.Children.Add(element); }
            if (syncBlock != null) syncBlock.Text = preferences.Language == "en" ? filtered.Count + " of " + all.Count + " chats · Updates every 5 seconds"
                : "显示 " + filtered.Count + " / " + all.Count + " 个聊天 · 每 5 秒同步";
        }
        void RenderQuota()
        {
            if (quotaPanel == null) return; quotaPanel.Children.Clear();
            var usage = Json.Child(snapshot, "usage"); var account = Json.Child(usage, "account");
            string plan = Subscription(account);
            var heading = new DockPanel(); var chipText = SideText(plan, 10, true);
            var chip = new Border { Background = Tint(Brushes.White, 0.12), CornerRadius = new CornerRadius(12), Padding = new Thickness(8, 4, 8, 4), Child = chipText }; DockPanel.SetDock(chip, Dock.Right); heading.Children.Add(chip);
            var headingText = SideText(T("当前额度", "Available quota"), 11, true); headingText.VerticalAlignment = VerticalAlignment.Center; heading.Children.Add(headingText); quotaPanel.Children.Add(heading);
            foreach (var window in VisibleWindows(usage))
            {
                var group = new StackPanel { Margin = new Thickness(0, 16, 0, 0) };
                double remaining = Json.Number(window, "remaining", Double.NaN);
                var labels = new DockPanel(); var value = SideText(Double.IsNaN(remaining) ? T("未提供", "Not provided") : remaining.ToString("0.0", CultureInfo.InvariantCulture) + "%", 10, true); DockPanel.SetDock(value, Dock.Right); labels.Children.Add(value); labels.Children.Add(SideText(WindowTitle(Json.Number(window, "minutes")), 10, true)); group.Children.Add(labels);
                if (!Double.IsNaN(remaining) && remaining >= 0 && remaining <= 100)
                {
                    var track = new Grid { Height = 8, Margin = new Thickness(0, 7, 0, 7) };
                    track.Children.Add(new Border { Background = Tint(Brushes.White, 0.05), CornerRadius = new CornerRadius(4) });
                    var fill = new Grid(); fill.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(Math.Max(0.0001, remaining), GridUnitType.Star) }); fill.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(Math.Max(0.0001, 100 - remaining), GridUnitType.Star) });
                    fill.Children.Add(new Border { Background = remaining <= 10 ? Brushes.Orange : ColorBrush("#B0B0B0"), CornerRadius = new CornerRadius(4) }); track.Children.Add(fill); group.Children.Add(track);
                }
                var reset = SideText(T("下次刷新 ", "Next reset ") + FormatTime(Json.Number(window, "reset")), 10); reset.Foreground = Tint(Brushes.White, 0.58); group.Children.Add(reset); quotaPanel.Children.Add(group);
            }
            string quotaState = Json.Text(usage, "quota_state"), note = "";
            if (Json.Bool(usage, "blocked")) note = T("服务暂不允许使用，等待重新核验", "The service currently blocks usage. Waiting for verification.");
            else if (quotaState == "service_only" && Json.Bool(usage, "service_allowed")) note = T("服务已允许使用，未提供固定额度窗口", "Usage is permitted; no fixed quota window was provided.");
            else if (VisibleWindows(usage).Count == 0) note = T("额度信息尚未核实", "Allowance has not been verified");
            if (note.Length > 0) { var message = SideText(note, 10); message.Margin = new Thickness(0, 16, 0, 0); quotaPanel.Children.Add(message); }
            bool stale = UsageStale(usage); var freshness = SideText(stale ? T("额度待同步 · 上次记录", "Quota awaiting update · Saved reading") : T("服务实际限额 · 本机时区", "Service-reported limits · Local time"), 10);
            freshness.Foreground = stale ? Brushes.DarkOrange : Tint(Brushes.White, 0.5); freshness.Margin = new Thickness(0, 16, 0, 0); quotaPanel.Children.Add(freshness);
            if (accountPanel == null) return; accountPanel.Children.Clear();
            string name = Json.Text(account, "name", Json.Text(account, "email", T("未识别账号", "Account not identified")));
            var identity = new StackPanel { Orientation = Orientation.Horizontal };
            string initials = String.IsNullOrWhiteSpace(name) ? "?" : String.Concat(name.Split(new[]{' '}, StringSplitOptions.RemoveEmptyEntries).Take(2).Select(x => x.Substring(0, 1))).ToUpperInvariant();
            var avatarText = SideText(initials, 13, true); avatarText.HorizontalAlignment = HorizontalAlignment.Center; avatarText.VerticalAlignment = VerticalAlignment.Center;
            identity.Children.Add(new Border { Width = 38, Height = 38, CornerRadius = new CornerRadius(19), Background = Tint(Brushes.White, 0.12), Child = avatarText });
            var accountCopy = new StackPanel { Margin = new Thickness(10, 2, 0, 0), Width = 190 };
            var nameText = SideText(name, 11, true); nameText.TextWrapping = TextWrapping.NoWrap; nameText.TextTrimming = TextTrimming.CharacterEllipsis; accountCopy.Children.Add(nameText);
            var email = SideText(Json.Text(account, "email", T("登录信息未提供", "Sign-in details unavailable")), 10); email.Margin = new Thickness(0, 3, 0, 0); email.TextWrapping = TextWrapping.NoWrap; email.TextTrimming = TextTrimming.CharacterEllipsis; accountCopy.Children.Add(email); identity.Children.Add(accountCopy); accountPanel.Children.Add(identity);
            var idHeading = SideText(T("账号 ID", "Account ID"), 10); idHeading.Margin = new Thickness(0, 10, 0, 10); accountPanel.Children.Add(idHeading);
            string id = Json.Text(account, "id", T("接口暂未提供", "Not provided by the client")); var idRow = new DockPanel();
            if (Json.Get(account, "id") != null) { var copy = MakePlainButton(Glyph("copy", Tint(Brushes.White, 0.82), 14), delegate { try { Clipboard.SetText(id); } catch { } }); copy.Margin = new Thickness(8, 0, 0, 0); copy.ToolTip = T("复制账号 ID", "Copy account ID"); copy.VerticalAlignment = VerticalAlignment.Top; DockPanel.SetDock(copy, Dock.Right); idRow.Children.Add(copy); }
            var idText = SideText(id, 10, true); idText.FontFamily = new FontFamily("Consolas"); idText.MaxHeight = 40; idRow.Children.Add(idText); accountPanel.Children.Add(idRow);
        }
        string Subscription(Dictionary<string, object> account)
        {
            string plan = Json.Text(account, "plan_type", T("待识别", "Not identified"));
            var known = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) { {"free","Free"}, {"go","Go"}, {"plus","Plus"}, {"pro","Pro"}, {"team","Team"}, {"business","Business"}, {"enterprise","Enterprise"}, {"edu","Edu"} };
            string value; return known.TryGetValue(plan, out value) ? value : plan;
        }
        bool UsageStale(Dictionary<string, object> usage)
        { return Json.Bool(usage, "stale", true) || !String.IsNullOrEmpty(connectionError) || Json.Number(usage, "observed_at") < (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds - 90; }
        public void RememberDraft(string key, string text, int revision) { drafts[key] = new Draft { Text = text, Revision = revision }; }
        public bool ReadDraft(string key, out string text, out int revision)
        { Draft draft; bool found = drafts.TryGetValue(key, out draft); text = found ? draft.Text : ""; revision = found ? draft.Revision : 0; return found; }
        public void ClearDraft(string key, string text)
        { Draft draft; if (drafts.TryGetValue(key, out draft) && draft.Text == text) drafts.Remove(key); }
        void ConfigureAuxiliaryOwner(Window window)
        {
            // Sign-in startup can run entirely in the tray. An unshown main
            // window cannot own a WPF HWND, so auxiliary windows center on
            // screen until the main window has actually loaded once.
            if (IsLoaded) { window.Owner = this; window.WindowStartupLocation = WindowStartupLocation.CenterOwner; }
            else window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
        }
        void ShowSettingsWindow()
        {
            if (fixtureMode) return;
            if (settingsWindow != null) { settingsWindow.Activate(); return; }
            settingsWindow = new Window { Title = T("设置", "Settings"), Width = 800, Height = 780, MinWidth = 740, MinHeight = 620,
                FontFamily = FontFamily, FontSize = 13, Background = background, Foreground = foreground,
                Content = BuildSettingsSurface(), WindowStartupLocation = WindowStartupLocation.CenterOwner };
            ConfigureAuxiliaryOwner(settingsWindow); settingsWindow.Closed += delegate { settingsWindow = null; }; settingsWindow.Show();
        }
        public void ShowChatDetails(Dictionary<string, object> chat)
        {
            if (fixtureMode) return;
            var body = new StackPanel { Margin = new Thickness(26) };
            var heading = new DockPanel(); var done = MakeButton(T("完成", "Done"), delegate { }); DockPanel.SetDock(done, Dock.Right); heading.Children.Add(done);
            var title = Text(Json.Text(chat, "name"), 17, true); title.Margin = new Thickness(0, 0, 16, 0); heading.Children.Add(title); body.Children.Add(heading);
            var stage = Text(Json.Text(Json.Child(chat, "execution_stage"), "text", T("暂未读取到公开执行进展", "No public execution progress is available")), 13); stage.Margin = new Thickness(0, 18, 0, 18); body.Children.Add(stage);
            body.Children.Add(DividerLine(border, new Thickness(0, 0, 0, 18)));
            body.Children.Add(Text(T("来源：", "Source: ") + Json.Text(chat, "source_label"), 13));
            body.Children.Add(Text(T("上次暂停：", "Last paused: ") + FormatTime(Json.Number(chat, "paused_at")), 13));
            body.Children.Add(Text(T("上次续做：", "Last resumed: ") + FormatTime(Json.Number(chat, "resumed_at")), 13));
            var identifier = new TextBox { Text = T("聊天 ID：", "Chat ID: ") + Json.Text(chat, "id"), IsReadOnly = true, TextWrapping = TextWrapping.Wrap, BorderThickness = new Thickness(0), Background = Brushes.Transparent, Foreground = foreground, FontFamily = new FontFamily("Consolas"), FontSize = 11, Margin = new Thickness(0, 6, 0, 14) }; body.Children.Add(identifier);
            string reason = Json.Text(chat, "reason", Json.Text(chat, "connection_error", Json.Text(chat, "capability_note"))); if (reason.Length > 0) { var note = Text(reason, 12); note.Foreground = secondary; body.Children.Add(note); }
            var immediate = Json.Child(chat, "immediate");
            if (immediate.Count > 0)
            {
                body.Children.Add(DividerLine(border, new Thickness(0, 12, 0, 18)));
                string state = Json.Text(immediate, "state");
                string delivery = state == "sent" ? T("已确认发送", "Delivery confirmed") : state == "failed" ? T("未发送", "Not sent") : state == "unknown" ? T("结果待核对", "Result unconfirmed") : T("正在检查并确认发送", "Checking and confirming delivery");
                body.Children.Add(Text(T("立刻执行：", "Run now: ") + delivery, 13, true));
                string receipt = T("发送标识：", "Dispatch ID: ") + Json.Text(immediate, "id", T("未提供", "Not provided"));
                string turn = Json.Text(immediate, "turn_id"); if (turn.Length > 0) receipt += "\n" + T("确认回合：", "Confirmed turn: ") + turn;
                string message = Json.Text(immediate, "message"); if (message.Length > 0) receipt += "\n" + message;
                body.Children.Add(new TextBox { Text = receipt, IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
                    BorderThickness = new Thickness(0), Padding = new Thickness(0), Background = Brushes.Transparent, Foreground = secondary,
                    FontFamily = new FontFamily("Consolas, Microsoft YaHei UI"), FontSize = 11, Margin = new Thickness(0, 4, 0, 18) });
            }
            body.Children.Add(MakeButton(T("在客户端打开聊天", "Open chat in client"), delegate { OpenChat(Json.Text(chat, "id")); }));
            var detail = new Window { Title = Json.Text(chat, "name"), Width = 640, Height = 520, MinHeight = 360, WindowStartupLocation = WindowStartupLocation.CenterOwner, Background = background, Foreground = foreground, FontFamily = FontFamily, FontSize = 13, Content = Scroller(body) };
            ConfigureAuxiliaryOwner(detail); done.Click += delegate { detail.Close(); }; detail.Show();
        }
        public static List<Dictionary<string, object>> VisibleWindows(Dictionary<string, object> usage)
        {
            if (Json.Get(usage, "quota_windows") != null) return Json.Rows(usage, "quota_windows");
            var result = new List<Dictionary<string, object>>(); var windows = Json.Child(usage, "windows");
            foreach (var pair in new[] { new KeyValuePair<string, int>("five_hour", 300), new KeyValuePair<string, int>("weekly", 10080) })
            {
                var raw = Json.Child(windows, pair.Key); if (raw.Count == 0) continue;
                result.Add(Json.Values("minutes", pair.Value, "remaining", Json.Get(raw, "remaining"), "reset", Json.Get(raw, "reset")));
            }
            return result;
        }
        public string WindowTitle(double minutes)
        {
            if (minutes == 300) return T("五小时额度", "Five-hour quota");
            if (minutes == 10080) return T("周额度", "Weekly quota");
            if (minutes > 0 && minutes % 1440 == 0) return (minutes / 1440).ToString("0") + T("天额度", "-day quota");
            if (minutes > 0 && minutes % 60 == 0) return (minutes / 60).ToString("0") + T("小时额度", "-hour quota");
            return minutes.ToString("0") + T("分钟额度", "-minute quota");
        }
        public static string FormatTime(double epoch)
        {
            if (Double.IsNaN(epoch) || Double.IsInfinity(epoch) || epoch <= 0) return "—";
            try { return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(epoch).ToLocalTime().ToString("MM/dd HH:mm:ss"); }
            catch { return "—"; }
        }
        void BuildEvents()
        {
            var title = Text(T("操作记录", "Activity"), 26, true); title.Margin = new Thickness(0, 0, 0, 20); content.Children.Add(title);
            var description = Text(T("查看最近 200 条任务控制与指令发送记录。", "Review the latest 200 task-control and instruction-delivery records."), 13); description.Foreground = secondary; description.Margin = new Thickness(0, 0, 0, 20); content.Children.Add(description);
            var events = Json.Rows(snapshot, "events");
            foreach (var item in events.Take(200))
            {
                var row = new DockPanel { Margin = new Thickness(12, 10, 12, 10) };
                var icon = Glyph("clock", accent, 16); icon.Margin = new Thickness(0, 2, 18, 0); icon.VerticalAlignment = VerticalAlignment.Top; DockPanel.SetDock(icon, Dock.Left); row.Children.Add(icon);
                var stamp = Text(FormatTime(Json.Number(item, "created")), 10); stamp.Foreground = secondary; stamp.Margin = new Thickness(18, 1, 0, 0); DockPanel.SetDock(stamp, Dock.Right); row.Children.Add(stamp);
                var labels = new StackPanel(); var heading = Text(EventLabel(Json.Text(item, "state")), 13, true); heading.Margin = new Thickness(0, 0, 0, 5); labels.Children.Add(heading);
                var name = Text(Json.Text(item, "name", T("全局控制", "Global control")), 13); name.Margin = new Thickness(0); labels.Children.Add(name);
                string reason = Json.Text(Json.Child(item, "detail"), "reason"); if (reason.Length > 0) { var detail = Text(reason, 12); detail.Foreground = secondary; detail.Margin = new Thickness(0, 5, 0, 0); labels.Children.Add(detail); }
                row.Children.Add(labels); content.Children.Add(row); content.Children.Add(DividerLine(Tint(secondary, 0.15), new Thickness(46, 0, 12, 0)));
            }
            if (events.Count == 0) { var empty = Text(T("暂无控制操作记录", "No control activity has been recorded"), 13); empty.Foreground = secondary; content.Children.Add(empty); }
        }
        string EventLabel(string value)
        {
            var labels = new Dictionary<string, string[]> {
                {"watching",new[]{"纳入监测","Monitoring enabled"}}, {"paused",new[]{"已确认暂停","Pause confirmed"}},
                {"pause_intent",new[]{"开始暂停","Pause requested"}}, {"resume_intent",new[]{"提交续做","Resume requested"}},
                {"running",new[]{"已续做","Resumed"}}, {"needs_review",new[]{"需要核对","Review required"}},
                {"held",new[]{"手动保持","Manual hold"}}, {"disabled",new[]{"已撤销控制","Control revoked"}},
                {"plan_armed",new[]{"已预约下一窗口","Scheduled for next window"}}, {"plan_sending",new[]{"提交预约指令","Scheduled instruction submitted"}},
                {"plan_sent",new[]{"预约指令已确认发送","Scheduled delivery confirmed"}}, {"plan_cancelled",new[]{"已取消预约","Schedule cancelled"}},
                {"immediate_pending",new[]{"提交立刻执行","Immediate execution requested"}}, {"immediate_sent",new[]{"立刻执行已确认发送","Immediate delivery confirmed"}},
                {"immediate_failed",new[]{"立刻执行未发送","Immediate delivery failed"}} };
            string[] label; return labels.TryGetValue(value, out label) ? T(label[0],label[1]) : value;
        }
        void BuildRules()
        {
            content.Margin = new Thickness(30); content.MaxWidth = 850; content.HorizontalAlignment = HorizontalAlignment.Left;
            var title = Text(T("运行规则", "Rules"), 26, true); title.Margin = new Thickness(0, 0, 0, 22); content.Children.Add(title);
            var policy = Json.Child(snapshot, "policy");
            Rule(T("自动暂停与续接", "Automatic pause and recovery"), preferences.Language == "en"
                ? "Control tasks using actual service-reported quota windows. Pause when five-hour or other non-weekly allowance is at or below " + Json.Number(policy, "pause", 10) + "%, then recheck at " + Json.Number(policy, "resume", 20) + "% or above. Exhausted weekly allowance and service restrictions also block sending. Confirm recovery for at least " + Json.Number(policy, "confirm_seconds", 5) + " seconds and verify the account, original chat and usage permission."
                : "按服务返回的实际额度窗口控制任务。五小时及其他非周窗口剩余 ≤" + Json.Number(policy, "pause", 10) + "% 时暂停，恢复至 ≥" + Json.Number(policy, "resume", 20) + "% 后复核；周窗口用尽或服务禁止使用时也暂停。连续复核至少 " + Json.Number(policy, "confirm_seconds", 5) + " 秒，并核对账号、原聊天与使用许可。");
            Rule(T("下个窗口执行一次", "Run once in the next window"), T("预约开关独立于单聊自动控制，按服务提供的实际刷新窗口执行一次。没有固定窗口时可使用立刻执行。保存指令不会立刻发送；关闭全局自动控制会阻止预约发送。", "The one-time schedule is independent of a chat's automatic-control switch and uses the actual service reset window. Run now is available when no fixed window is provided. Saving a scheduled instruction does not send it immediately. Pausing global automation blocks scheduled delivery."));
            Rule(T("订阅与额度", "Subscription and quota"), T("订阅名称只用于显示。缺失额度不会视为无限；未提供固定窗口时，只有服务明确允许使用才能发送。额度信息不完整时暂停自动发送。", "Subscription names are display metadata. Missing quota is never treated as unlimited. Without a fixed window, sending requires explicit service permission. Incomplete quota information blocks automatic sending."));
            Rule(T("立刻执行", "Run now"), T("发送当前指令框内容，不等待刷新。发送后等待真实回执，不把提交成功当作已执行。执行中、等待审批、额度或账号异常时，后台会拒绝发送。结果不明确时不会自动重复发送。", "Send the current instruction without waiting for a reset, then wait for a real delivery receipt. Submission is not proof of execution. Busy chats, pending approvals, or quota and account issues can block delivery. An uncertain result is not retried automatically."));
            Rule(T("手动操作优先", "Manual actions take priority"), T("人工新指令、审批与 Goal 约束优先。聊天完成后等待下一条指令，不会无限续做。ChatGPT 普通聊天仅显示目录。", "New user instructions, approvals and Goal constraints take priority. Completed chats wait for a new instruction and are not continued indefinitely. Ordinary ChatGPT chats are directory-only."));
            Rule(T("后台运行", "Background operation"), T("关闭主窗口后继续运行。退出应用停止管家和自身电源保护，不中断原客户端正在执行的聊天。锁屏、熄屏与合盖是不同的运行条件。", "Closing the window keeps the app running. Exiting stops Mission Manager and its own keep-awake request, without interrupting client chats. Locking, display-off and lid closure are different operating conditions."));
            var settings = MakeButton(T("后台运行与系统权限…", "Background operation and permissions…"), ShowSettingsWindow); settings.HorizontalAlignment = HorizontalAlignment.Left; content.Children.Add(settings);
        }
        void Rule(string title, string description)
        {
            var group = new StackPanel(); var heading = Text(title, 13, true); heading.Margin = new Thickness(0, 0, 0, 10); group.Children.Add(heading);
            var text = Text(description, 13); text.Foreground = secondary; text.LineHeight = 18; text.Margin = new Thickness(0); group.Children.Add(text);
            content.Children.Add(Card(group, new Thickness(0, 0, 0, 22)));
        }
        Border SettingsGroup(UIElement body, Thickness? padding = null)
        { return new Border { Background = groupSurface, BorderBrush = border, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6), Padding = padding ?? new Thickness(14), Margin = new Thickness(0, 0, 0, 24), Child = body }; }
        FrameworkElement GroupHeading(string iconName, string title)
        {
            var line = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 16) };
            var icon = Glyph(iconName, secondary, 16); icon.Margin = new Thickness(0, 0, 8, 0); line.Children.Add(icon);
            var text = Text(title, 13, true); text.Margin = new Thickness(0); line.Children.Add(text); return line;
        }
        FrameworkElement SettingsChoiceRow(string label, FrameworkElement choice, double width)
        {
            var row = new DockPanel { Margin = new Thickness(0, 0, 0, 12) }; choice.Width = width; DockPanel.SetDock(choice, Dock.Right); row.Children.Add(choice);
            var text = Text(label, 13); text.VerticalAlignment = VerticalAlignment.Center; text.Margin = new Thickness(0); row.Children.Add(text); return row;
        }
        FrameworkElement PermissionRow(string title, string iconName, string description, string status, bool enabled, Action<bool> changed, string destination, bool available = true)
        {
            var row = new Grid { Margin = new Thickness(14) }; row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(42) }); row.ColumnDefinitions.Add(new ColumnDefinition()); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(64) }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(28) });
            var icon = Glyph(iconName, secondary, 20); icon.HorizontalAlignment = HorizontalAlignment.Left; row.Children.Add(icon);
            var labels = new StackPanel { Margin = new Thickness(0, 0, 14, 0) }; Grid.SetColumn(labels, 1); row.Children.Add(labels);
            var heading = Text(title, 13, true); heading.Margin = new Thickness(0, 0, 0, 5); labels.Children.Add(heading);
            var detail = Text(description, 12); detail.Foreground = secondary; detail.Margin = new Thickness(0, 0, 0, 5); labels.Children.Add(detail);
            var state = Text(status, 10); state.Foreground = secondary; state.Margin = new Thickness(0); labels.Children.Add(state);
            var toggle = new CheckBox { Content = "", Width = 50, IsChecked = enabled, IsEnabled = available, VerticalAlignment = VerticalAlignment.Center }; StyleSwitch(toggle, false); Grid.SetColumn(toggle, 2); row.Children.Add(toggle);
            toggle.Click += delegate { if (!fixtureMode) changed(toggle.IsChecked == true); };
            var open = MakePlainButton(Glyph("external", secondary, 18), delegate { if (!fixtureMode) OpenUri(destination); }); open.Width = 22; open.Height = 24; open.VerticalAlignment = VerticalAlignment.Center; open.ToolTip = T("打开系统设置", "Open system settings"); Grid.SetColumn(open, 3); row.Children.Add(open);
            return row;
        }
        string CompatibilityLabel()
        {
            var value = Json.Child(snapshot, "compatibility"); string state = Json.Text(value, "status");
            if (state == "client_missing") return T("尚未检测到客户端", "Client not detected");
            if (value.Count == 0) return T("正在检查客户端兼容性", "Checking client compatibility");
            string version = Json.Text(value, "version", Json.Text(value, "build"));
            string label = state == "supported" ? T("已适配", "Compatible") : state == "update_required" ? T("需要更新任务管家", "Mission Manager update required") : T("正在检查客户端兼容性", "Checking client compatibility");
            return version.Length > 0 ? version + " · " + label : label;
        }
        FrameworkElement BuildSettingsSurface()
        {
            var body = new StackPanel { Margin = new Thickness(28) };
            var title = Text(T("设置", "Settings"), 26, true); title.Margin = new Thickness(0, 0, 0, 8); body.Children.Add(title);
            var description = Text(T("管理外观、后台运行与系统权限。", "Manage appearance, background operation and system permissions."), 13); description.Foreground = secondary; description.Margin = new Thickness(0, 0, 0, 24); body.Children.Add(description);
            var appearance = new StackPanel(); appearance.Children.Add(GroupHeading("palette", T("外观与语言", "Appearance and language")));
            appearance.Children.Add(SettingsChoiceRow(T("语言", "Language"), Segments(new[] { "简体中文", "English" }, new[] { "zh", "en" }, preferences.Language,
                delegate(string value) { preferences.Language = value; SavePreferences(); RebuildPresentation(); }), 180));
            appearance.Children.Add(SettingsChoiceRow(T("外观", "Appearance"), Segments(new[] { T("跟随系统", "System"), T("浅色", "Light"), T("深色", "Dark") }, new[] { "system", "light", "dark" }, preferences.Theme,
                delegate(string value) { preferences.Theme = value; SavePreferences(); RebuildPresentation(); }), 270)); body.Children.Add(SettingsGroup(appearance));
            var connection = new StackPanel(); connection.Children.Add(GroupHeading("network", T("客户端连接", "Client connection")));
            var version = Text(CompatibilityLabel(), 13); version.Foreground = secondary; version.Margin = new Thickness(0, 0, 0, 12); connection.Children.Add(version);
            var statusLine = new DockPanel(); var checks = new StackPanel { Orientation = Orientation.Horizontal };
            var check = MakeButton(T("重新检查", "Check again"), async delegate { await RefreshAsync(); RefreshSettingsWindow(); }); checks.Children.Add(check);
            if (host == null && !fixtureMode) { var reconnect = MakeButton(T("重新连接", "Reconnect"), delegate { StartHost(); SetNotice(T("正在连接本机后台。", "Connecting to the local service.")); }); reconnect.Margin = new Thickness(8, 0, 0, 0); checks.Children.Add(reconnect); } DockPanel.SetDock(checks, Dock.Right); statusLine.Children.Add(checks);
            var hostStatus = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center }; bool connected = fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError));
            var dot = new System.Windows.Shapes.Ellipse { Width = 8, Height = 8, Fill = connected ? accent : Brushes.DarkOrange, Margin = new Thickness(0, 0, 7, 0), VerticalAlignment = VerticalAlignment.Center }; hostStatus.Children.Add(dot);
            var statusText = Text(connected ? T("后台已连接", "Backend connected") : T("后台未连接", "Backend disconnected"), 12); statusText.Foreground = connected ? accent : Brushes.DarkOrange; statusText.Margin = new Thickness(0); hostStatus.Children.Add(statusText); statusLine.Children.Add(hostStatus); connection.Children.Add(statusLine);
            var hint = Text(T("关闭窗口后，任务管家继续在系统托盘运行。", "Closing the window keeps Mission Manager running in the system tray."), 10); hint.Foreground = secondary; hint.Margin = new Thickness(0, 12, 0, 0); connection.Children.Add(hint);
            if (!ControlAvailable) { var reason = Text(ControlConnectionNote(), 10); reason.Foreground = secondary; reason.Margin = new Thickness(0, 8, 0, 0); connection.Children.Add(reason); }
            body.Children.Add(SettingsGroup(connection));
            var permissions = new StackPanel();
            permissions.Children.Add(PermissionRow(T("登录时启动", "Start at sign-in"), "power", T("登录 Windows 后自动启动任务管家。", "Start Mission Manager automatically after signing in to Windows."), fixtureMode ? T("尚未登记", "Not registered") : IsStartupEnabled() ? T("系统已允许", "Enabled in Windows") : T("尚未登记", "Not registered"), !fixtureMode && IsStartupEnabled(), SetStartup, "ms-settings:startupapps"));
            permissions.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            permissions.Children.Add(PermissionRow(T("任务通知", "Task notifications"), "bell", T("通知暂停、续接、发送失败及需要处理的异常。", "Notify on pauses, resumptions, failed deliveries and actionable errors."), preferences.Notifications ? T("应用通知已启用；系统投递状态未核验", "App notifications enabled; system delivery permission is not verified") : T("通知已关闭", "Notifications off"), preferences.Notifications, delegate(bool value) { preferences.Notifications = value; SavePreferences(); }, "ms-settings:notifications"));
            permissions.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            permissions.Children.Add(PermissionRow(T("保持后台运行", "Keep running in the background"), "moon", T("防止空闲睡眠，允许屏幕关闭。此设置不保证合盖运行。", "Prevent idle sleep while allowing the display to turn off. This does not guarantee operation with the lid closed."), preferences.KeepAwake ? T("已保持系统清醒", "Keep-awake request active") : T("未启用防睡眠保护", "Keep-awake protection off"), preferences.KeepAwake, SetAwake, "ms-settings:powersleep")); body.Children.Add(SettingsGroup(permissions, new Thickness(8)));
            var lid = new StackPanel();
            lid.Children.Add(PermissionRow(T("合盖运行辅助服务", "Closed-lid helper service"), "laptop", T("为无外接显示器的合盖运行提供电源管理支持。", "Provide power-management support for closed-lid operation without an external display."), T("当前 Windows 版本暂未提供此功能。", "This feature is not available in the current Windows preview."), false, delegate(bool value) { }, "ms-settings:powersleep", false));
            lid.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            lid.Children.Add(PermissionRow(T("合盖运行", "Closed-lid operation"), "laptop", T("合盖和手动睡眠仍按 Windows 系统电源策略处理。", "Lid closure and manual sleep still follow Windows system power policy."), T("未启用", "Not enabled"), false, delegate(bool value) { }, "ms-settings:powersleep", false));
            var battery = new DockPanel { Margin = new Thickness(20, 0, 20, 14) }; var batteryToggle = new CheckBox { Content = "", Width = 50, IsChecked = false, IsEnabled = false }; StyleSwitch(batteryToggle, false); DockPanel.SetDock(batteryToggle, Dock.Right); battery.Children.Add(batteryToggle); var batteryText = Text(T("允许使用电池", "Allow battery operation"), 12); batteryText.Margin = new Thickness(0); batteryText.VerticalAlignment = VerticalAlignment.Center; battery.Children.Add(batteryText); lid.Children.Add(battery);
            var powerNote = Text(T("此预览不会修改系统电源计划，也不保证合盖或手动睡眠后执行。", "This preview does not change the system power plan or guarantee execution after lid closure or manual sleep."), 10); powerNote.Foreground = secondary; powerNote.TextAlignment = TextAlignment.Center; powerNote.Margin = new Thickness(20, 0, 20, 12); lid.Children.Add(powerNote); body.Children.Add(SettingsGroup(lid, new Thickness(8)));
            var footer = new DockPanel(); var time = Text(T("最近检查：", "Last checked: ") + (fixtureMode ? FormatTime(Json.Number(snapshot, "now")) : DateTime.Now.ToString("HH:mm:ss")), 10); time.Foreground = secondary; DockPanel.SetDock(time, Dock.Right); footer.Children.Add(time);
            var power = Text(PowerLabel(), 10); power.Foreground = secondary; footer.Children.Add(power); body.Children.Add(footer);
            return new Border { Background = background, Child = Scroller(body) };
        }
        string PowerLabel()
        {
            if (fixtureMode) return T("外接电源 · 电量 100% · 系统策略（示例）", "AC power · Battery 100% · System policy (sample)");
            try { var power = Forms.SystemInformation.PowerStatus; return (power.PowerLineStatus == Forms.PowerLineStatus.Online ? T("外接电源", "AC power") : T("电池", "Battery")) + " · " + Math.Round(power.BatteryLifePercent * 100) + "%"; } catch { return T("电源状态暂未提供", "Power status unavailable"); }
        }
        void SavePreferences() { if (!fixtureMode) preferences.Save(); }
        void RefreshSettingsWindow()
        {
            if (settingsWindow == null || AnyOpenChoice(settingsWindow)) return;
            settingsWindow.Title = T("设置", "Settings"); settingsWindow.Background = background; settingsWindow.Foreground = foreground; settingsWindow.Content = BuildSettingsSurface();
        }
        static bool AnyOpenChoice(DependencyObject parent)
        {
            var choice = parent as ComboBox; if (choice != null && choice.IsDropDownOpen) return true;
            int count; try { count = VisualTreeHelper.GetChildrenCount(parent); } catch { return false; }
            for (int index = 0; index < count; index++) if (AnyOpenChoice(VisualTreeHelper.GetChild(parent, index))) return true; return false;
        }
        bool IsStartupEnabled()
        {
            try { using (var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run")) return key != null && key.GetValue("CodexMissionManager") != null; }
            catch { return false; }
        }
        void SetStartup(bool value)
        {
            try
            {
                using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run"))
                { if (value) key.SetValue("CodexMissionManager", "\"" + Process.GetCurrentProcess().MainModule.FileName + "\" --background"); else key.DeleteValue("CodexMissionManager", false); }
                SetNotice(T("启动偏好已保存。", "Startup preference saved."));
            }
            catch (Exception ex) { SetNotice(ex.Message); }
            RefreshSettingsWindow();
        }
        public static void OpenUri(string uri)
        {
            try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); } catch { }
        }
        public void OpenChat(string id) { OpenUri("codex://threads/" + Uri.EscapeDataString(id)); }
        void SetAwake(bool enabled)
        {
            if (fixtureMode) return;
            uint result = SetThreadExecutionState(ExecutionContinuous | (enabled ? ExecutionSystemRequired : 0));
            if (result == 0) { preferences.KeepAwake = false; SetNotice(T("未能启用保持运行，请检查系统电源设置。", "Could not keep the system awake. Check Windows power settings.")); }
            else preferences.KeepAwake = enabled;
            preferences.Save();
        }
        void SetNotice(string value) { notice = value; if (noticeBlock != null) noticeBlock.Text = notice; UpdateNotices(); BuildTrayMenu(); }
        public void ToggleGlobal()
        {
            if (fixtureMode) return;
            if (baseUri == null || !Json.Bool(snapshot, "running")) { StartHost(); SetNotice(T("正在连接本机后台。", "Connecting to the local service.")); return; }
            if (Json.Bool(snapshot, "control_paused", true) && !ControlAvailable) { SetNotice(T("客户端控制尚未通过核验，暂不能启用自动控制。", "Client control has not passed verification. Automatic control cannot be enabled yet.")); return; }
            var action = Json.Bool(snapshot, "control_paused", true) ? "enable" : "pause";
            var ignored = PerformAsync(Json.Values("action", action, "revision", Json.Integer(snapshot, "control_revision")));
        }
        void StartHost()
        {
            if (fixtureMode || quitting) return;
            if (host != null)
            {
                try { if (!host.HasExited) return; } catch (InvalidOperationException) { }
                try { host.Dispose(); } catch { } host = null;
            }
            string directory = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(directory, "runtime", "python", "python.exe");
            string script = Path.Combine(directory, "backend", "app_host.py");
            if (!File.Exists(python) || !File.Exists(script)) { connectionError = T("应用文件不完整，请重新安装。", "Application files are incomplete. Reinstall the app."); RenderSnapshot(); return; }
            try
            {
                Directory.CreateDirectory(preferences.DirectoryPath);
                var start = new ProcessStartInfo(python, "-X utf8 -I \"" + script + "\" --directory \"" + preferences.DirectoryPath + "\"") {
                    WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
                var process = new Process { StartInfo = start, EnableRaisingEvents = true };
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                    if (String.IsNullOrWhiteSpace(e.Data)) return;
                    try
                    {
                        var data = Json.Parse(e.Data); Uri url;
                        if (Uri.TryCreate(Json.Text(data, "url"), UriKind.Absolute, out url) && url.Scheme == "http" && url.Host == "127.0.0.1" && url.Port > 0)
                            Dispatcher.BeginInvoke(new Action(async delegate { if (!Object.ReferenceEquals(host, process) || quitting) return; baseUri = url; connectionError = ""; await RefreshAsync(); }));
                    }
                    catch (Exception) { }
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                    if (String.IsNullOrEmpty(e.Data)) return;
                    try { File.AppendAllText(Path.Combine(preferences.DirectoryPath, "native-host.log"), DateTime.UtcNow.ToString("o") + " " + e.Data + Environment.NewLine, Encoding.UTF8); } catch { }
                };
                process.Exited += delegate { Dispatcher.BeginInvoke(new Action(delegate {
                    if (!Object.ReferenceEquals(host, process)) return;
                    host = null;
                    if (!quitting) {
                        string code; try { code = process.ExitCode.ToString(CultureInfo.InvariantCulture); } catch { code = "—"; }
                        baseUri = null; connectionError = T("后台已退出（退出码 ", "The backend exited (code ") + code
                            + T("）；本机记录保留。可启动后台服务或在设置中重新连接。", "). Local records are preserved. Start the service or reconnect in Settings."); RenderSnapshot();
                    }
                })); };
                process.Start(); host = process; process.BeginOutputReadLine(); process.BeginErrorReadLine();
            }
            catch (Exception ex) { connectionError = ex.Message; RenderSnapshot(); }
        }
        public void EnsureHostStarted() { StartHost(); }
        async Task RefreshAsync()
        {
            if (fixtureMode || quitting || refreshing || baseUri == null) return;
            refreshing = true;
            try
            {
                using (var handshake = await client.GetAsync(baseUri)) handshake.EnsureSuccessStatusCode();
                using (var response = await client.GetAsync(new Uri(baseUri, "/api/state")))
                {
                    response.EnsureSuccessStatusCode(); snapshot = Json.Parse(await response.Content.ReadAsStringAsync());
                }
                connectionError = ""; RenderSnapshot();
            }
            catch (Exception ex) { connectionError = T("后台连接待恢复：", "Backend connection unavailable: ") + ex.Message; RenderSnapshot(); }
            finally { refreshing = false; }
        }
        public async Task PerformAsync(Dictionary<string, object> payload)
        {
            if (fixtureMode || quitting || busy || baseUri == null) return;
            string action = Json.Text(payload, "action");
            bool createsWork = action == "enable" || action == "pause_all" || action == "execute_now"
                || ((action == "set_auto" || action == "set_plan") && Json.Bool(payload, "enabled"));
            if (createsWork && (!ControlAvailable || !Healthy))
            {
                SetNotice(T("当前连接尚未通过核验，仅可撤销已有许可或取消预约。", "The connection is not verified. Existing permissions and schedules can still be revoked."));
                RenderSnapshot(); return;
            }
            busy = true; SetNotice(T("正在提交操作…", "Submitting…")); RenderHeader(); RenderChats();
            try
            {
                using (var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseUri, "/api/action")))
                {
                    request.Headers.Add("X-Guardian-UI", "1"); request.Headers.Add("Origin", baseUri.GetLeftPart(UriPartial.Authority));
                    request.Content = new StringContent(Json.Stringify(payload), Encoding.UTF8, "application/json");
                    using (var response = await client.SendAsync(request))
                    {
                        var body = Json.Parse(await response.Content.ReadAsStringAsync());
                        if (!response.IsSuccessStatusCode) throw new InvalidOperationException(Json.Text(body, "error", T("操作结果待核对，请查看记录。", "Result unconfirmed. Check activity before retrying.")));
                        SetNotice(preferences.Language == "en" ? Json.Text(body, "message_en", Json.Text(body, "message", "Request submitted. Check the delivery record.")) : Json.Text(body, "message", "操作已提交，请核对回执。"));
                    }
                }
            }
            catch (Exception ex) { SetNotice(ex.Message); }
            finally { busy = false; }
            // C# 5 cannot await in finally. Refresh after both the success and
            // handled-failure paths, once the busy guard has been released.
            await RefreshAsync(); RenderSnapshot();
        }
        void BuildTray()
        {
            try { trayBrandIcon = System.Drawing.Icon.ExtractAssociatedIcon(Process.GetCurrentProcess().MainModule.FileName); } catch { }
            tray = new Forms.NotifyIcon { Icon = trayBrandIcon ?? System.Drawing.SystemIcons.Application, Text = "Mission Manager", Visible = true };
            tray.DoubleClick += delegate { Dispatcher.BeginInvoke(new Action(ShowMain)); };
            tray.MouseUp += delegate(object sender, Forms.MouseEventArgs e) {
                if (e.Button == Forms.MouseButtons.Left || e.Button == Forms.MouseButtons.Right) Dispatcher.BeginInvoke(new Action(ToggleTrayPanel));
            };
        }
        void ToggleTrayPanel()
        {
            if (quitting || fixtureMode) return;
            if (trayPanelWindow != null) { trayPanelWindow.Close(); return; }
            var panel = new Window { Width = 400, Height = 570, WindowStyle = WindowStyle.None, ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false, Topmost = true, AllowsTransparency = true, Background = Brushes.Transparent, Foreground = foreground,
                FontFamily = FontFamily, FontSize = 13, Content = BuildTraySurface() };
            trayPanelWindow = panel; var work = SystemParameters.WorkArea;
            panel.Left = Math.Max(work.Left, work.Right - panel.Width - 12); panel.Top = Math.Max(work.Top, work.Bottom - panel.Height - 12);
            panel.Deactivated += delegate { if (!AnyOpenChoice(panel)) panel.Close(); };
            panel.Closed += delegate { if (Object.ReferenceEquals(trayPanelWindow, panel)) trayPanelWindow = null; };
            panel.Show(); panel.Activate();
        }
        void CloseTrayPanel() { if (trayPanelWindow != null) trayPanelWindow.Close(); }
        void BuildTrayMenu()
        {
            if (trayPanelWindow == null || AnyOpenChoice(trayPanelWindow)) return;
            trayPanelWindow.Foreground = foreground; trayPanelWindow.Content = BuildTraySurface();
        }
        FrameworkElement TrayAction(string name, string iconName, Action action)
        {
            var line = new StackPanel { Orientation = Orientation.Horizontal }; var glyph = Glyph(iconName, foreground, 15); glyph.Margin = new Thickness(0, 0, 9, 0); line.Children.Add(glyph);
            var label = Text(name, 13); label.Margin = new Thickness(0); line.Children.Add(label);
            var button = MakePlainButton(line, action); button.HorizontalAlignment = HorizontalAlignment.Stretch; button.Margin = new Thickness(0, 0, 0, 16); return button;
        }
        FrameworkElement BuildTraySurface()
        {
            var body = new StackPanel { Margin = new Thickness(20) };
            var heading = new DockPanel(); var plan = Text(Subscription(Json.Child(Json.Child(snapshot, "usage"), "account")), 10); plan.Foreground = secondary; plan.Margin = new Thickness(0); plan.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(plan, Dock.Right); heading.Children.Add(plan);
            var brand = new StackPanel { Orientation = Orientation.Horizontal }; var shield = Glyph("shield", foreground, 18); shield.Margin = new Thickness(0, 0, 8, 0); brand.Children.Add(shield); var title = Text(T("任务管家", "Mission Manager"), 13, true); title.Margin = new Thickness(0); brand.Children.Add(title); heading.Children.Add(brand); body.Children.Add(heading);
            var usage = Json.Child(snapshot, "usage"); var windows = VisibleWindows(usage);
            foreach (var window in windows)
            {
                var meter = new StackPanel { Margin = new Thickness(0, 16, 0, 0) }; var top = new DockPanel(); double remaining = Json.Number(window, "remaining", Double.NaN);
                var value = Text(Double.IsNaN(remaining) ? T("未提供", "Not provided") : remaining.ToString("0.0", CultureInfo.InvariantCulture) + "%", 12, true); value.Margin = new Thickness(0); DockPanel.SetDock(value, Dock.Right); top.Children.Add(value);
                var label = Text(WindowTitle(Json.Number(window, "minutes")), 12); label.Margin = new Thickness(0); top.Children.Add(label); meter.Children.Add(top);
                if (!Double.IsNaN(remaining))
                {
                    var track = new Grid { Height = 5, Margin = new Thickness(0, 6, 0, 6) }; track.Children.Add(new Border { Background = Tint(secondary, 0.2), CornerRadius = new CornerRadius(3) });
                    var fill = new Border { Background = remaining <= 10 ? Brushes.DarkOrange : accent, CornerRadius = new CornerRadius(3), HorizontalAlignment = HorizontalAlignment.Left };
                    track.Children.Add(fill); track.SizeChanged += delegate { fill.Width = track.ActualWidth * Math.Max(0, Math.Min(100, remaining)) / 100; }; meter.Children.Add(track);
                }
                var reset = Text(Json.Number(window, "reset") > 0 ? T("下次刷新 ", "Next reset ") + FormatTime(Json.Number(window, "reset")) : T("刷新时间未提供", "Reset time not provided"), 10); reset.Foreground = secondary; reset.Margin = new Thickness(0); meter.Children.Add(reset); body.Children.Add(meter);
            }
            string availability = "";
            if (Json.Bool(usage, "blocked")) availability = T("服务暂不允许使用，等待重新核验", "The service currently blocks usage. Waiting for verification.");
            else if (Json.Text(usage, "quota_state") == "service_only" && Json.Bool(usage, "service_allowed")) availability = T("服务已允许使用，未提供固定额度窗口", "Usage is permitted; no fixed quota window was provided.");
            else if (windows.Count == 0) availability = T("额度信息尚未核实", "Allowance has not been verified");
            if (availability.Length > 0) { var note = Text(availability, 10); note.Foreground = secondary; note.Margin = new Thickness(0, 14, 0, 0); body.Children.Add(note); }
            if (UsageStale(usage)) { var stale = Text(T("◷  额度待同步", "◷  Quota awaiting update"), 10); stale.Foreground = Brushes.DarkOrange; stale.Margin = new Thickness(0, 14, 0, 0); body.Children.Add(stale); }
            var controls = new Grid { Margin = new Thickness(0, 16, 0, 0) }; controls.ColumnDefinitions.Add(new ColumnDefinition()); controls.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) }); controls.ColumnDefinitions.Add(new ColumnDefinition());
            string bulkState = Json.Text(Json.Child(snapshot, "bulk_pause"), "state"); bool bulkBusy = bulkState == "pending" || bulkState == "processing";
            var automatic = MakeButton(Json.Bool(snapshot, "control_paused", true) ? T("恢复自动控制", "Resume automation") : T("暂停自动控制", "Pause automation"), ToggleGlobal); automatic.FontSize = 11;
            automatic.IsEnabled = !busy && !bulkBusy && (fixtureMode || baseUri != null) && Json.Bool(snapshot, "running") && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy)); controls.Children.Add(automatic);
            var pause = MakeButton(T("暂停所有任务", "Pause all tasks"), async delegate { await PerformAsync(Json.Values("action", "pause_all", "revision", Json.Integer(snapshot, "control_revision"))); }); pause.FontSize = 11; pause.ToolTip = T("暂停允许接管的执行中任务，并关闭全局自动控制。手动暂停的任务需手动恢复。", "Pause managed running tasks and disable global automation. Manually paused tasks require manual resumption."); pause.IsEnabled = !busy && !bulkBusy && Healthy && ControlAvailable && (fixtureMode || baseUri != null); Grid.SetColumn(pause, 2); controls.Children.Add(pause); body.Children.Add(controls);
            var bulk = Json.Child(snapshot, "bulk_pause"); if (bulk.Count > 0)
            {
                var result = new DockPanel { Margin = new Thickness(0, 12, 0, 0) }; var details = MakePlainButton(T("查看结果", "View results"), ShowBulkResults); details.FontSize = 10; DockPanel.SetDock(details, Dock.Right); result.Children.Add(details);
                var count = Text(T("暂停 ", "Paused ") + Json.Integer(bulk, "paused") + T(" · 跳过 ", " · Skipped ") + Json.Integer(bulk, "skipped") + T(" · 待处理 ", " · Needs attention ") + Json.Integer(bulk, "failed"), 10); count.Foreground = Json.Integer(bulk, "failed") > 0 ? Brushes.DarkOrange : secondary; count.Margin = new Thickness(0); result.Children.Add(count); body.Children.Add(result);
            }
            if (notice.Length > 0) { var message = Text(notice, 10); message.Foreground = secondary; message.Margin = new Thickness(0, 12, 0, 0); body.Children.Add(message); }
            if (connectionError.Length > 0) { var error = Text(connectionError, 10); error.Foreground = Brushes.DarkOrange; error.Margin = new Thickness(0, 12, 0, 0); body.Children.Add(error); }
            body.Children.Add(DividerLine(border, new Thickness(0, 16, 0, 16)));
            body.Children.Add(TrayAction(T("打开任务管家", "Open Mission Manager"), "window", ShowMain));
            body.Children.Add(TrayAction(T("设置", "Settings"), "settings", delegate { CloseTrayPanel(); ShowSettingsWindow(); }));
            var language = Choice(new[] { "简体中文", "English" }); language.SelectedIndex = preferences.Language == "en" ? 1 : 0;
            language.SelectionChanged += delegate { preferences.Language = language.SelectedIndex == 1 ? "en" : "zh"; SavePreferences(); RebuildPresentation(); }; body.Children.Add(SettingsChoiceRow(T("语言", "Language"), language, 180));
            var theme = Choice(new[] { T("跟随系统", "System"), T("浅色", "Light"), T("深色", "Dark") }); theme.SelectedIndex = preferences.Theme == "light" ? 1 : preferences.Theme == "dark" ? 2 : 0;
            theme.SelectionChanged += delegate { preferences.Theme = theme.SelectedIndex == 1 ? "light" : theme.SelectedIndex == 2 ? "dark" : "system"; SavePreferences(); RebuildPresentation(); }; body.Children.Add(SettingsChoiceRow(T("外观", "Appearance"), theme, 180));
            body.Children.Add(DividerLine(border, new Thickness(0, 4, 0, 16)));
            var footer = new DockPanel(); var exit = MakePlainButton(T("退出", "Quit"), Quit); exit.FontSize = 10; DockPanel.SetDock(exit, Dock.Right); footer.Children.Add(exit);
            var connected = Text(fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError)) ? T("●  后台已连接", "●  Backend connected") : T("●  后台未连接", "●  Backend disconnected"), 10); connected.Foreground = secondary; connected.Margin = new Thickness(0); footer.Children.Add(connected); body.Children.Add(footer);
            return new Border { Background = background, BorderBrush = border, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Child = Scroller(body), ClipToBounds = true };
        }
        void ShowBulkResults()
        {
            if (fixtureMode) return; CloseTrayPanel(); var body = new StackPanel { Margin = new Thickness(24) }; var heading = Text(T("暂停所有任务", "Pause all tasks"), 17, true); body.Children.Add(heading);
            var description = Text(T("暂停允许接管的执行中任务，并关闭全局自动控制。手动暂停的任务需手动恢复。", "Pause managed running tasks and disable global automation. Manually paused tasks require manual resumption."), 12); description.Foreground = secondary; description.Margin = new Thickness(0, 8, 0, 18); body.Children.Add(description);
            foreach (var item in Json.Rows(Json.Child(snapshot, "bulk_pause"), "items"))
            {
                string id = Json.Text(item, "thread_id"); var task = Json.Rows(snapshot, "tasks").FirstOrDefault(x => Json.Text(x, "id") == id);
                var title = Text(task == null ? id : Json.Text(task, "name"), 13, true); title.Margin = new Thickness(0, 0, 0, 6); body.Children.Add(title);
                string state = Json.Text(item, "state"); var status = Text(state == "paused" ? T("已暂停", "Paused") : state == "skipped" ? T("已跳过", "Skipped") : T("暂停失败", "Pause failed"), 12); status.Foreground = state == "failed" ? Brushes.DarkOrange : secondary; body.Children.Add(status);
                string reason = Json.Text(item, "reason"); if (reason.Length > 0) { var detail = Text(reason, 10); detail.Foreground = secondary; body.Children.Add(detail); } body.Children.Add(DividerLine(border, new Thickness(0, 8, 0, 14)));
            }
            var window = new Window { Title = T("暂停结果", "Pause results"), Width = 540, Height = 480, WindowStartupLocation = WindowStartupLocation.CenterOwner, Background = background, Foreground = foreground, FontFamily = FontFamily, FontSize = 13, Content = Scroller(body) }; ConfigureAuxiliaryOwner(window); window.Show();
        }
        public FrameworkElement PreparePreviewSurface(string view)
        {
            if (!fixtureMode) throw new InvalidOperationException("Preview surfaces require fixture mode.");
            if (view == "settings") return BuildSettingsSurface();
            if (view == "tray") return BuildTraySurface();
            currentView = view == "activity" ? "events" : view == "rules" ? "rules" : "tasks"; BuildContent(); RenderSnapshot();
            var surface = Content as FrameworkElement; Content = null; return surface;
        }
        void ReadNotifications()
        {
            try
            {
                string path = Path.Combine(preferences.DirectoryPath, "state", "native-notices.json");
                var rootNotices = Json.Serializer().DeserializeObject(File.ReadAllText(path)) as IEnumerable;
                if (rootNotices == null) return;
                foreach (object raw in rootNotices)
                {
                    var noticeValue = Json.Object(raw); string key = Json.Text(noticeValue, "key");
                    if (!notificationKeys.Add(key) || firstNotices || !preferences.Notifications || tray == null) continue;
                    tray.ShowBalloonTip(5000, Json.Text(noticeValue, "title", "Mission Manager"), Json.Text(noticeValue, "body"), Forms.ToolTipIcon.Info);
                }
                firstNotices = false;
            }
            catch (Exception) { }
        }
        void ShowMain() { CloseTrayPanel(); Show(); if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal; Activate(); }
        void OnClosing(object sender, CancelEventArgs e)
        {
            if (fixtureMode || quitting) return; e.Cancel = true; Hide();
        }
        async void Quit()
        {
            if (quitting) return; quitting = true; CloseTrayPanel(); if (settingsWindow != null) settingsWindow.Close(); if (timer != null) timer.Stop();
            SetThreadExecutionState(ExecutionContinuous);
            if (tray != null) { tray.Visible = false; tray.Dispose(); tray = null; }
            if (trayBrandIcon != null) { trayBrandIcon.Dispose(); trayBrandIcon = null; }
            IsEnabled = false;
            var owned = host;
            if (owned != null)
            {
                try { if (!owned.HasExited) { owned.StandardInput.WriteLine("stop"); owned.StandardInput.Flush(); owned.StandardInput.Close(); } } catch { }
                await Task.Run(delegate { try { if (!owned.WaitForExit(45000) && !owned.HasExited) owned.Kill(); } catch { } });
            }
            client.Dispose(); Application.Current.Shutdown();
        }
    }

    static class ChatControlPolicy
    {
        public static bool IsLocal(Dictionary<string, object> chat)
        {
            // The backend still verifies the current cached account scope and
            // revision. This only identifies a local chat for a revocation UI.
            return Json.Text(chat, "key").StartsWith("codex:local:", StringComparison.Ordinal)
                && Json.Text(chat, "kind", "codex") == "codex"
                && Json.Text(chat, "host_id", "local") == "local";
        }
        public static bool AutomaticOn(Dictionary<string, object> chat)
        {
            return Json.Bool(chat, "auto_resume") && !Json.Bool(chat, "manual_hold") && Json.Text(chat, "state") != "disabled";
        }
        public static bool CanToggleAutomatic(Dictionary<string, object> chat, bool healthy, bool controlAvailable, bool busy, bool localApiAvailable)
        {
            if (busy || !localApiAvailable) return false;
            if (AutomaticOn(chat) && IsLocal(chat)) return true; // only the off transition
            return healthy && controlAvailable && Json.Bool(chat, "can_control");
        }
        public static bool CanToggleSchedule(Dictionary<string, object> chat, bool healthy, bool controlAvailable, bool busy, bool localApiAvailable, bool canSchedule)
        {
            if (busy || !localApiAvailable) return false;
            string state = Json.Text(Json.Child(chat, "plan"), "state");
            if (state == "sending") return false; // already submitted; cannot cancel
            if (state == "armed" && IsLocal(chat)) return true; // only cancellation
            return healthy && controlAvailable && Json.Bool(chat, "can_control") && canSchedule;
        }
        public static bool SelfTest()
        {
            var local = Json.Values("key", "codex:local:offline-fixture", "kind", "codex", "host_id", "local", "auto_resume", true,
                "manual_hold", false, "state", "watching", "can_control", false, "plan", Json.Values("state", "armed"));
            if (!CanToggleAutomatic(local, false, false, false, true) || !CanToggleSchedule(local, false, false, false, true, false)) return false;
            if (CanToggleAutomatic(local, false, false, true, true) || CanToggleSchedule(local, false, false, true, true, false)) return false;
            if (CanToggleAutomatic(local, false, false, false, false) || CanToggleSchedule(local, false, false, false, false, false)) return false;
            local["auto_resume"] = false; local["plan"] = Json.Values("state", "cancelled");
            if (CanToggleAutomatic(local, false, false, false, true) || CanToggleSchedule(local, false, false, false, true, false)) return false;
            local["auto_resume"] = true; local["plan"] = Json.Values("state", "sending");
            if (CanToggleSchedule(local, true, true, false, true, true)) return false;
            local["key"] = "chatgpt:cloud:offline-fixture"; local["kind"] = "chatgpt"; local["host_id"] = "cloud"; local["plan"] = Json.Values("state", "armed");
            if (CanToggleAutomatic(local, false, false, false, true) || CanToggleSchedule(local, false, false, false, true, false)) return false;
            local["key"] = "codex:local:offline-fixture"; local["kind"] = "codex"; local["host_id"] = "local";
            local["auto_resume"] = false; local["can_control"] = true; local["plan"] = Json.Values("state", "off");
            return CanToggleAutomatic(local, true, true, false, true) && CanToggleSchedule(local, true, true, false, true, true);
        }
    }

    sealed class ChatRow : Border
    {
        readonly MissionWindow owner;
        readonly TextBlock title, detail, stage, stageStamp, status, planLabel, receiptLabel, autoHeading, directoryText, autoError;
        readonly Border statusBadge;
        readonly ContentControl typeIconHost;
        readonly System.Windows.Shapes.Ellipse statusDot;
        readonly StackPanel editorPanel, directoryPanel;
        readonly CheckBox auto, schedule;
        readonly TextBox prompt;
        readonly Button save, now, open, retry, cancel;
        Dictionary<string, object> chat = new Dictionary<string, object>();
        bool updating, dirty;
        int draftRevision;
        public ChatRow(MissionWindow window)
        {
            owner = window; Background = owner.SurfaceBrush; BorderThickness = new Thickness(0); CornerRadius = new CornerRadius(10);
            Padding = new Thickness(16); Margin = new Thickness(0, 0, 0, 12);
            var columns = new Grid(); columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) });
            columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(138) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(310) }); Child = columns;
            var info = new StackPanel(); columns.Children.Add(info);
            var rowHeading = new DockPanel(); typeIconHost = new ContentControl { Width = 18, Height = 15, Margin = new Thickness(0, 2, 8, 0), VerticalAlignment = VerticalAlignment.Top }; DockPanel.SetDock(typeIconHost, Dock.Left); rowHeading.Children.Add(typeIconHost);
            var identity = new StackPanel(); title = Label("", 13, true); title.Margin = new Thickness(0); open = owner.MakePlainButton(title, delegate { owner.ShowChatDetails(chat); }); open.HorizontalContentAlignment = HorizontalAlignment.Left; identity.Children.Add(open);
            detail = Label("", 10); detail.FontFamily = new FontFamily("Consolas"); detail.Foreground = owner.SecondaryBrush; detail.Margin = new Thickness(0, 5, 0, 0); identity.Children.Add(detail); rowHeading.Children.Add(identity); info.Children.Add(rowHeading);
            var stageBody = new StackPanel(); var stageHeading = Label(owner.T("当前执行阶段", "Execution stage"), 10, true); stageHeading.Foreground = owner.AccentBrush; stageHeading.Margin = new Thickness(0, 0, 0, 7); stageBody.Children.Add(stageHeading);
            stageStamp = Label("", 10); stageStamp.Foreground = owner.SecondaryBrush; stageStamp.Margin = new Thickness(0, 0, 0, 7); stageBody.Children.Add(stageStamp);
            stage = Label("", 12); stage.Foreground = owner.SecondaryBrush; stage.LineHeight = 16; stage.MaxHeight = 80; stage.TextTrimming = TextTrimming.CharacterEllipsis; stage.Margin = new Thickness(0); stageBody.Children.Add(stage);
            info.Children.Add(new Border { Background = owner.StageBrush, CornerRadius = new CornerRadius(8), Padding = new Thickness(12), Margin = new Thickness(0, 10, 0, 0), Child = stageBody });
            var middle = new StackPanel(); Grid.SetColumn(middle, 2); columns.Children.Add(middle);
            var badgeLine = new StackPanel { Orientation = Orientation.Horizontal }; statusDot = new System.Windows.Shapes.Ellipse { Width = 6, Height = 6, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 7, 0) }; badgeLine.Children.Add(statusDot);
            status = Label("", 10, true); status.Margin = new Thickness(0); badgeLine.Children.Add(status);
            statusBadge = new Border { CornerRadius = new CornerRadius(7), Padding = new Thickness(8), HorizontalAlignment = HorizontalAlignment.Left, Child = badgeLine }; middle.Children.Add(statusBadge);
            autoHeading = Label(owner.T("自动控制", "Automatic control"), 10); autoHeading.Foreground = owner.SecondaryBrush; autoHeading.Margin = new Thickness(0, 20, 0, 7); middle.Children.Add(autoHeading);
            auto = new CheckBox { Foreground = owner.ForegroundBrush, HorizontalAlignment = HorizontalAlignment.Stretch };
            owner.StyleSwitch(auto); auto.Click += async delegate { if (!updating) await owner.PerformAsync(Json.Values("action", "set_auto", "key", Json.Text(chat, "key"), "enabled", auto.IsChecked == true, "revision", Json.Integer(chat, "revision"))); }; middle.Children.Add(auto);
            retry = owner.MakeButton(owner.T("重试连接", "Retry connection"), async delegate { await owner.PerformAsync(Json.Values("action", "set_auto", "key", Json.Text(chat, "key"), "enabled", true, "revision", Json.Integer(chat, "revision"))); }); retry.FontSize = 10; retry.Margin = new Thickness(0, 7, 0, 0); retry.HorizontalAlignment = HorizontalAlignment.Left; middle.Children.Add(retry);
            autoError = Label("", 10); autoError.Foreground = Brushes.DarkOrange; autoError.MaxHeight = 46; autoError.Margin = new Thickness(0, 7, 0, 0); middle.Children.Add(autoError);
            var right = new StackPanel(); Grid.SetColumn(right, 4); columns.Children.Add(right);
            directoryPanel = new StackPanel(); var directoryHeading = new StackPanel { Orientation = Orientation.Horizontal };
            var eye = owner.Glyph("eye", owner.SecondaryBrush, 16); eye.Margin = new Thickness(0, 0, 8, 0); directoryHeading.Children.Add(eye); var label = Label(owner.T("仅显示目录", "Directory only"), 12); label.Foreground = owner.SecondaryBrush; label.Margin = new Thickness(0); directoryHeading.Children.Add(label); directoryPanel.Children.Add(directoryHeading);
            directoryText = Label("", 10); directoryText.Foreground = owner.SecondaryBrush; directoryText.Margin = new Thickness(0, 10, 0, 0); directoryPanel.Children.Add(directoryText); right.Children.Add(directoryPanel);
            editorPanel = new StackPanel(); right.Children.Add(editorPanel);
            schedule = new CheckBox { Foreground = owner.ForegroundBrush, Margin = new Thickness(0, 0, 0, 10) }; owner.StyleSwitch(schedule);
            schedule.Click += async delegate { if (!updating) await SavePlan(schedule.IsChecked == true); }; editorPanel.Children.Add(schedule);
            planLabel = Label("", 10); planLabel.Foreground = owner.SecondaryBrush; planLabel.Margin = new Thickness(0, 0, 0, 10); editorPanel.Children.Add(planLabel);
            prompt = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 78, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Padding = new Thickness(6), FontSize = 13, MaxLength = 8000, Margin = new Thickness(0, 0, 0, 10) }; owner.StyleTextBox(prompt);
            prompt.TextChanged += delegate { if (!updating) { if (!dirty) draftRevision = Json.Integer(Json.Child(chat, "plan"), "revision"); dirty = true; owner.RememberDraft(Json.Text(chat, "key"), prompt.Text, draftRevision); } }; editorPanel.Children.Add(prompt);
            var buttons = new WrapPanel(); save = owner.MakeButton(owner.T("保存并预约", "Save & schedule"), async delegate { await SavePlan(true); }); save.Margin = new Thickness(0, 0, 8, 0); buttons.Children.Add(save);
            now = owner.MakeButton(owner.T("立刻执行", "Run now"), async delegate { await owner.PerformAsync(Json.Values("action", "execute_now", "key", Json.Text(chat, "key"), "prompt", prompt.Text, "revision", Json.Integer(chat, "revision"), "request_id", Guid.NewGuid().ToString("D"))); }, true); buttons.Children.Add(now); editorPanel.Children.Add(buttons);
            receiptLabel = Label("", 10); receiptLabel.Foreground = owner.SecondaryBrush; receiptLabel.Margin = new Thickness(0, 10, 0, 0); editorPanel.Children.Add(receiptLabel);
            cancel = owner.MakePlainButton(owner.T("取消此预约", "Cancel this schedule"), async delegate { await SavePlan(false); }); cancel.FontSize = 10; cancel.Foreground = owner.SecondaryBrush; cancel.Margin = new Thickness(0, 8, 0, 0); cancel.HorizontalAlignment = HorizontalAlignment.Left; editorPanel.Children.Add(cancel);
            bool layoutInitialized = false, narrowLayout = false;
            SizeChanged += delegate {
                bool narrow = ActualWidth - Padding.Left - Padding.Right < 850; if (layoutInitialized && narrow == narrowLayout) return; layoutInitialized = true; narrowLayout = narrow;
                columns.ColumnDefinitions.Clear(); columns.RowDefinitions.Clear(); Grid.SetRow(info, 0); Grid.SetColumn(info, 0);
                if (narrow)
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(156) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) }); columns.ColumnDefinitions.Add(new ColumnDefinition());
                    columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    Grid.SetColumnSpan(info, 3); info.Margin = new Thickness(0, 0, 0, 18); Grid.SetRow(middle, 1); Grid.SetColumn(middle, 0); Grid.SetRow(right, 1); Grid.SetColumn(right, 2);
                }
                else
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(138) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(18) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(310) });
                    Grid.SetColumnSpan(info, 1); info.Margin = new Thickness(0); Grid.SetRow(middle, 0); Grid.SetColumn(middle, 2); Grid.SetRow(right, 0); Grid.SetColumn(right, 4);
                }
            };
        }
        TextBlock Label(string value, int size, bool bold = false)
        { return new TextBlock { Text = value, FontSize = size, Foreground = owner.ForegroundBrush, FontWeight = bold ? FontWeights.Bold : FontWeights.Normal, TextWrapping = TextWrapping.Wrap, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, LineHeight = MissionWindow.TextLineHeight(size), Margin = new Thickness(0) }; }
        async Task SavePlan(bool enabled)
        {
            var plan = Json.Child(chat, "plan"); int revision = enabled && dirty ? draftRevision : Json.Integer(plan, "revision");
            string text = enabled ? prompt.Text : Json.Text(plan, "prompt", "继续任务");
            await owner.PerformAsync(Json.Values("action", "set_plan", "key", Json.Text(chat, "key"), "enabled", enabled, "prompt", text, "revision", revision));
            // A saved prompt is considered clean only after the refreshed plan
            // matches it, never merely because the HTTP request was attempted.
            var refreshed = Json.Rows(owner.Snapshot, "tasks").FirstOrDefault(x => Json.Text(x, "key") == Json.Text(chat, "key"));
            if (enabled && refreshed != null && prompt.Text == text && Json.Text(Json.Child(refreshed, "plan"), "prompt") == text.Trim()
                    && Json.Integer(Json.Child(refreshed, "plan"), "revision") != revision) { dirty = false; owner.ClearDraft(Json.Text(chat, "key"), text); }
        }
        public void Update(Dictionary<string, object> value)
        {
            chat = value; updating = true; title.Text = Json.Text(chat, "name");
            string iconName = Json.Text(chat, "category") == "chatgpt" ? "chat" : "terminal"; if (!Object.Equals(typeIconHost.Tag, iconName)) { typeIconHost.Tag = iconName; typeIconHost.Content = owner.Glyph(iconName, owner.AccentBrush, 15); }
            string source = Json.Text(chat, "category") == "codex" ? owner.T("Codex · 本机", "Codex · Local")
                : Json.Text(chat, "source_label").IndexOf("Work", StringComparison.OrdinalIgnoreCase) >= 0 ? owner.T("ChatGPT Work · 云端", "ChatGPT Work · Cloud") : owner.T("ChatGPT · 目录快照", "ChatGPT · Directory snapshot");
            string id = Json.Text(chat, "id"); detail.Text = source + " / " + id.Substring(0, Math.Min(id.Length, 8));
            var execution = Json.Child(chat, "execution_stage"); stage.Text = Json.Text(execution, "text", Json.Bool(chat, "can_control") ? owner.T("暂未读取到执行进展", "Execution progress is not available yet") : owner.T("当前仅显示目录，执行阶段暂不可读", "Directory only; execution progress is not available")); stage.ToolTip = stage.Text;
            double stamp = Json.Number(execution, "updated_at"); stageStamp.Text = MissionWindow.FormatTime(stamp); stageStamp.Visibility = stamp > 0 ? Visibility.Visible : Visibility.Collapsed;
            status.Text = Status(); var runtime = Json.Child(chat, "runtime"); IEnumerable flags = Json.Get(runtime, "activeFlags") as IEnumerable; bool waitingInput = flags != null && flags.Cast<object>().Any();
            string state = Json.Text(chat, "state"); bool attention = state == "needs_review" || Json.Text(Json.Child(chat, "plan"), "state") == "needs_review" || Json.Text(chat, "auto_connection") == "failed" || waitingInput || Json.Text(runtime, "type") == "systemError";
            bool waiting = state == "paused" || state == "pause_intent" || state == "resume_intent";
            Brush color = !owner.BackendConnected ? owner.SecondaryBrush : attention || waiting ? Brushes.DarkOrange : Json.Text(runtime, "type") == "active" ? owner.AccentBrush : owner.SecondaryBrush;
            status.Foreground = color; statusDot.Fill = color; statusBadge.Background = MissionWindow.Tint(color, 0.09);
            bool automatic = ChatControlPolicy.AutomaticOn(chat); auto.IsChecked = automatic;
            string connection = Json.Text(chat, "auto_connection");
            auto.Content = !Json.Bool(chat, "can_control") ? owner.T("不可用", "Unavailable") : connection == "waiting_global" ? owner.T("等待启用", "Waiting") : connection == "failed" ? owner.T("未连接", "Not connected") : Json.Bool(chat, "auto_pending") ? owner.T("连接中", "Connecting") : automatic ? owner.T("已开启", "On") : owner.T("已关闭", "Off");
            bool controllable = Json.Bool(chat, "can_control") && owner.ControlAvailable, available = owner.Healthy && !owner.IsBusy;
            auto.IsEnabled = ChatControlPolicy.CanToggleAutomatic(chat, owner.Healthy, owner.ControlAvailable, owner.IsBusy, owner.CanSubmitLocalChange);
            retry.Visibility = connection == "failed" ? Visibility.Visible : Visibility.Collapsed; retry.IsEnabled = controllable && available;
            autoError.Text = Json.Text(chat, "auto_error"); autoError.Visibility = connection == "failed" && autoError.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            var plan = Json.Child(chat, "plan"); string planState = Json.Text(plan, "state", "off"); bool scheduled = MissionWindow.Scheduled(plan); schedule.IsChecked = scheduled; schedule.Content = PlanLabel(planState);
            var usage = Json.Child(owner.Snapshot, "usage"); bool canSchedule = Json.Bool(usage, "scheduling_available", MissionWindow.VisibleWindows(usage).Count > 0);
            schedule.IsEnabled = ChatControlPolicy.CanToggleSchedule(chat, owner.Healthy, owner.ControlAvailable, owner.IsBusy, owner.CanSubmitLocalChange, canSchedule);
            double minutes = Json.Number(plan, "armed_window_minutes"), reset = Json.Number(plan, "armed_window_reset");
            if (!(minutes > 0 && reset > 0 && (scheduled || planState == "needs_review")))
            {
                var target = Json.Child(usage, "scheduling_window"); if (target.Count == 0) target = MissionWindow.VisibleWindows(usage).OrderBy(x => Json.Number(x, "minutes") == 300 ? 0 : Json.Number(x, "minutes") == 10080 ? 2 : 1).ThenBy(x => Json.Number(x, "minutes")).FirstOrDefault() ?? new Dictionary<string, object>();
                minutes = Json.Number(target, "minutes"); reset = Json.Number(target, "reset");
            }
            planLabel.Text = minutes > 0 && reset > 0 && canSchedule ? owner.T("预约窗口：", "Schedule window: ") + owner.WindowTitle(minutes) + "\n" + owner.T("刷新时间 ", "Reset ") + MissionWindow.FormatTime(reset) : "";
            planLabel.Visibility = planLabel.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
            string draftText; int revision; if (owner.ReadDraft(Json.Text(chat, "key"), out draftText, out revision)) { dirty = true; draftRevision = revision; prompt.Text = draftText; }
            else if (!dirty) { prompt.Text = Json.Text(plan, "prompt", "继续任务"); draftRevision = Json.Integer(plan, "revision"); }
            prompt.IsReadOnly = !controllable || planState == "sending";
            save.Content = scheduled ? owner.T("保存指令", "Save instruction") : owner.T("保存并预约", "Save & schedule"); save.IsEnabled = controllable && available && canSchedule && planState != "sending";
            var immediate = Json.Child(chat, "immediate"); string receipt = Json.Text(immediate, "state");
            now.IsEnabled = controllable && available && Json.Text(runtime, "type") != "active" && !waitingInput && receipt != "pending" && receipt != "checking" && receipt != "sending" && planState != "sending" && PermitsImmediate(usage);
            receiptLabel.Text = receipt.Length > 0 ? ReceiptLabel(receipt) + " " + Json.Text(immediate, "message") : !canSchedule ? owner.T("当前未提供可预约的刷新窗口。", "No schedulable reset window is available.") : "";
            string reason = Json.Text(plan, "reason"); if (reason.Length > 0) receiptLabel.Text += (receiptLabel.Text.Length == 0 ? "" : "\n") + reason;
            receiptLabel.Visibility = receiptLabel.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            cancel.Visibility = planState == "needs_review" ? Visibility.Visible : Visibility.Collapsed; cancel.IsEnabled = !owner.IsBusy && owner.CanSubmitLocalChange && ChatControlPolicy.IsLocal(chat);
            bool editorVisible = Json.Bool(chat, "can_control") || (ChatControlPolicy.IsLocal(chat) && (planState == "armed" || planState == "needs_review"));
            editorPanel.Visibility = editorVisible ? Visibility.Visible : Visibility.Collapsed; directoryPanel.Visibility = editorVisible ? Visibility.Collapsed : Visibility.Visible;
            directoryText.Text = Json.Text(chat, "category") == "chatgpt" ? owner.T("此聊天没有后台自动执行通道", "Automatic execution is unavailable for this chat") : owner.T("客户端控制尚待核验，当前只读显示。", "Client control awaits verification. This chat is read-only.");
            updating = false;
        }
        bool PermitsImmediate(Dictionary<string, object> usage)
        {
            if (Json.Bool(usage, "blocked") || Json.Get(usage, "service_allowed") is bool && !Json.Bool(usage, "service_allowed")) return false;
            string quotaState = Json.Text(usage, "quota_state"); if (quotaState.Length == 0) return true;
            if (!Json.Bool(usage, "service_allowed")) return false;
            if (quotaState == "service_only") return true;
            var windows = MissionWindow.VisibleWindows(usage); if (quotaState != "metered" || windows.Count == 0) return false;
            double minimum = Json.Number(Json.Child(owner.Snapshot, "policy"), "resume", 20);
            return windows.All(x => { double remaining = Json.Number(x, "remaining", Double.NaN); return !Double.IsNaN(remaining) && remaining <= 100 && (Json.Number(x, "minutes") == 10080 ? remaining > 0 : remaining >= minimum); });
        }
        string Status()
        {
            if (!owner.BackendConnected) return owner.T("状态待同步", "Awaiting status");
            string connection = Json.Text(chat, "auto_connection"), state = Json.Text(chat, "state");
            if (connection == "waiting_global") return owner.T("等待全局启用", "Waiting for global control");
            if (connection == "queued") return owner.T("等待连接", "Queued for connection");
            if (connection == "failed") return owner.T("连接失败，可重试", "Connection failed; retry available");
            if (Json.Text(chat, "connection_error").Length > 0) return owner.T("连接待恢复", "Connection unavailable");
            if (state == "needs_review" || Json.Text(Json.Child(chat, "plan"), "state") == "needs_review") return owner.T("需要检查", "Review required");
            if (state == "paused") return Json.Bool(chat, "manual_hold") ? owner.T("手动暂停", "Manually paused") : owner.T("等待恢复", "Waiting for recovery");
            if (state == "pause_intent") return owner.T("确认暂停中", "Confirming pause");
            if (state == "resume_intent") return owner.T("确认续做中", "Confirming resume");
            var runtime = Json.Child(chat, "runtime"); IEnumerable flags = Json.Get(runtime, "activeFlags") as IEnumerable;
            if (flags != null && flags.Cast<object>().Any()) return owner.T("等待你处理", "Needs your attention");
            string type = Json.Text(runtime, "type");
            if (type == "active") return owner.T("执行中", "Running");
            if (Json.Bool(chat, "auto_pending")) return owner.T("正在连接", "Connecting");
            if (type == "idle") return owner.T("等待指令", "Awaiting instructions");
            if (type == "notLoaded") return owner.T("未打开", "Not open");
            if (type == "systemError") return owner.T("回合出错", "Turn error");
            return owner.T("状态待同步", "Awaiting status");
        }
        string PlanLabel(string state)
        {
            if (state == "armed") return owner.T("等待下一窗口恢复", "Waiting for next window");
            if (state == "sending") return owner.T("正在确认发送", "Confirming delivery");
            if (state == "sent") return owner.T("已发送一次，预约已关闭", "Sent once; schedule is off");
            if (state == "cancelled") return owner.T("已取消预约", "Schedule cancelled");
            if (state == "needs_review") return owner.T("预约需要重新确认", "Schedule needs review");
            return owner.T("未预约", "Not scheduled");
        }
        string ReceiptLabel(string state)
        {
            if (state == "sent") return owner.T("已确认发送", "Delivery confirmed");
            if (state == "failed") return owner.T("未发送", "Not sent");
            if (state == "unknown") return owner.T("结果待核对，请先查看记录", "Result unconfirmed; check activity before retrying");
            return owner.T("正在检查并确认发送", "Checking and confirming delivery");
        }
    }

    static class Program
    {
        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--self-test")
            {
                bool revocationChecks = ChatControlPolicy.SelfTest();
                string result = Json.Stringify(Json.Values("version", "0.2.1", "platform", "windows", "native", true, "ui", "WPF", "webView", false,
                    "hostStarted", false, "messagesSent", 0, "cacheRefreshSeconds", 5, "localRevocationChecks", revocationChecks));
                if (args.Length > 1) File.WriteAllText(args[1], result, new UTF8Encoding(false));
                Console.WriteLine(result); return revocationChecks ? 0 : 1;
            }
            if (args.Length > 0 && args[0] == "--ui-self-test")
            {
                try
                {
                    if (args.Length < 3) throw new ArgumentException("Usage: --ui-self-test fixture.json preview.png [--language zh|en] [--theme system|light|dark] [--view home|settings|activity|rules|tray] [--scale 1|2]");
                    string language = "zh", theme = "system", previewView = "home"; double scale = 2; int positional = 0;
                    for (int index = 3; index < args.Length; index++)
                    {
                        if (args[index] == "--language" && index + 1 < args.Length) language = args[++index];
                        else if (args[index] == "--theme" && index + 1 < args.Length) theme = args[++index];
                        else if (args[index] == "--view" && index + 1 < args.Length) previewView = args[++index];
                        else if (args[index] == "--scale" && index + 1 < args.Length) scale = Double.Parse(args[++index], CultureInfo.InvariantCulture);
                        else if (args[index].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Unknown or incomplete fixture option.");
                        else if (positional++ == 0) language = args[index];
                        else if (positional == 2) theme = args[index];
                        else throw new ArgumentException("Unknown fixture argument.");
                    }
                    if (!new[] { "home", "settings", "activity", "rules", "tray" }.Contains(previewView)) throw new ArgumentException("Unknown fixture view.");
                    if (scale != 1 && scale != 2) throw new ArgumentException("Fixture scale must be 1 or 2.");
                    var fixture = Json.Parse(File.ReadAllText(args[1])); var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                    var window = new MissionWindow(true, fixture, language, theme);
                    int renderExit = 0;
                    app.Startup += delegate { window.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(delegate {
                        try
                        {
                        // Render a detached native content tree at a fixed size.
                        // No HWND/non-client area or remote desktop dimensions
                        // participate in this offline fixture capture.
                        var view = window.PreparePreviewSurface(previewView);
                        if (view == null) throw new InvalidOperationException("Native content is unavailable.");
                        System.Windows.Documents.TextElement.SetFontFamily(view, window.FontFamily);
                        System.Windows.Documents.TextElement.SetFontSize(view, window.FontSize);
                        System.Windows.Documents.TextElement.SetForeground(view, window.Foreground);
                        int width = previewView == "settings" ? 800 : previewView == "tray" ? 400 : 1380;
                        int height = previewView == "settings" ? 1100 : previewView == "tray" ? 570 : 900;
                        view.Width = width; view.Height = height;
                        view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout();
                        int pixelWidth = (int)(width * scale), pixelHeight = (int)(height * scale);
                        var image = new RenderTargetBitmap(pixelWidth, pixelHeight, 96 * scale, 96 * scale, PixelFormats.Pbgra32); image.Render(view);
                        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image)); using (var file = File.Create(args[2])) encoder.Save(file);
                        File.WriteAllText(args[2] + ".json", Json.Stringify(Json.Values("native", true, "ui", "WPF", "webView", false, "hostStarted", false, "messagesSent", 0,
                            "fixtureChats", Json.Rows(fixture, "tasks").Count, "renderedRoot", "content", "view", previewView, "width", pixelWidth, "height", pixelHeight, "logicalWidth", width, "logicalHeight", height, "scale", scale,
                            "desktopResolutionIndependent", true, "privatePreferencesLoaded", false, "language", language, "theme", theme)), new UTF8Encoding(false));
                        }
                        catch (Exception ex) { renderExit = 1; Console.Error.WriteLine(ex.ToString()); }
                        finally { app.Shutdown(renderExit); }
                    })); }; app.Run(); return renderExit;
                }
                catch (Exception ex) { Console.Error.WriteLine(ex.ToString()); return 1; }
            }
            bool created; using (var mutex = new Mutex(true, @"Local\CodexMissionManager-Windows", out created))
            {
                if (!created) { MessageBox.Show("任务管家已在运行，请从系统托盘打开。\nMission Manager is already running. Open it from the system tray.", "Mission Manager"); return 0; }
                var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                var window = new MissionWindow(false, null); app.MainWindow = window;
                app.Startup += delegate { if (args.Contains("--background")) window.EnsureHostStarted(); else window.Show(); };
                app.Run(); return 0;
            }
        }
    }
}
