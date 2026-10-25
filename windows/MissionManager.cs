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
        DispatcherTimer timer;
        bool refreshing, busy, quitting, firstNotices = true;
        string notice = "", connectionError = "", currentView = "tasks", source = "all", search = "";
        int page;
        Brush background, surface, foreground, secondary, border, accent, accentText;
        Grid root;
        StackPanel sidebar, quotaPanel, content;
        TextBlock noticeBlock, stateBlock, countBlock, syncBlock;
        Button globalButton, pauseAllButton;
        WrapPanel taskControls;
        StackPanel rowsPanel;
        TextBox searchBox;
        ComboBox sourceBox;

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
            Width = 1420; Height = 960; MinWidth = 900; MinHeight = 660;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI"); FontSize = 14;
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
        public bool IsBusy { get { return busy; } }
        public bool CanSubmitLocalChange { get { return !fixtureMode && !quitting && baseUri != null; } }
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
            background = ColorBrush(dark ? "#121A18" : "#F4F7F3"); surface = ColorBrush(dark ? "#1C2723" : "#FFFFFF");
            foreground = ColorBrush(dark ? "#E7EFE8" : "#24352C"); secondary = ColorBrush(dark ? "#A7B9AC" : "#6D7F70");
            border = ColorBrush(dark ? "#35443A" : "#DCE5DA"); accent = ColorBrush(dark ? "#8AC5A3" : "#315D46");
            accentText = ColorBrush(dark ? "#13261B" : "#FFFFFF"); Background = background; Foreground = foreground;
        }
        static Brush ColorBrush(string value) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(value)); }
        void CheckSystemTheme()
        {
            if (preferences.Theme == "system" && dark != SystemDark()) RebuildPresentation();
        }
        void RebuildPresentation()
        {
            ApplyTheme(); rowCache.Clear(); BuildShell(); BuildTrayMenu(); RenderSnapshot();
        }
        TextBlock Text(string value, double size, bool bold = false)
        {
            return new TextBlock { Text = value, FontSize = size, FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal,
                Foreground = foreground, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 8) };
        }
        public Button MakeButton(string label, Action action, bool prominent = false)
        {
            var result = new Button { Content = label, Padding = new Thickness(12, 7, 12, 7), Margin = new Thickness(0, 0, 8, 7),
                Background = prominent ? accent : surface, Foreground = prominent ? accentText : foreground, BorderBrush = border,
                BorderThickness = new Thickness(1), Cursor = System.Windows.Input.Cursors.Hand };
            result.Click += delegate { action(); }; return result;
        }
        public void StyleSwitch(CheckBox check)
        {
            // A real native CheckBox with a switch-shaped template retains
            // keyboard, focus and accessibility semantics.
            var template = new ControlTemplate(typeof(CheckBox));
            var line = new FrameworkElementFactory(typeof(StackPanel));
            line.SetValue(StackPanel.OrientationProperty, Orientation.Horizontal);
            var track = new FrameworkElementFactory(typeof(Border), "SwitchTrack");
            track.SetValue(FrameworkElement.WidthProperty, 39.0); track.SetValue(FrameworkElement.HeightProperty, 23.0);
            track.SetValue(Border.CornerRadiusProperty, new CornerRadius(12)); track.SetValue(Border.BackgroundProperty, border);
            track.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            var thumb = new FrameworkElementFactory(typeof(System.Windows.Shapes.Ellipse), "SwitchThumb");
            thumb.SetValue(FrameworkElement.WidthProperty, 17.0); thumb.SetValue(FrameworkElement.HeightProperty, 17.0);
            thumb.SetValue(FrameworkElement.MarginProperty, new Thickness(3)); thumb.SetValue(System.Windows.Shapes.Shape.FillProperty, Brushes.White);
            thumb.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Left); track.AppendChild(thumb); line.AppendChild(track);
            var label = new FrameworkElementFactory(typeof(ContentPresenter));
            label.SetValue(FrameworkElement.MarginProperty, new Thickness(9, 0, 0, 0)); label.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            label.SetBinding(ContentPresenter.ContentProperty, new System.Windows.Data.Binding("Content") { RelativeSource = System.Windows.Data.RelativeSource.TemplatedParent });
            line.AppendChild(label); template.VisualTree = line;
            var on = new Trigger { Property = CheckBox.IsCheckedProperty, Value = true };
            on.Setters.Add(new Setter(Border.BackgroundProperty, accent, "SwitchTrack"));
            on.Setters.Add(new Setter(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Right, "SwitchThumb")); template.Triggers.Add(on);
            var disabled = new Trigger { Property = UIElement.IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(UIElement.OpacityProperty, 0.5)); template.Triggers.Add(disabled);
            check.Template = template;
        }
        Border Card(UIElement child, Thickness margin)
        {
            return new Border { Background = surface, BorderBrush = border, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10),
                Padding = new Thickness(18), Margin = margin, Child = child };
        }
        void BuildShell()
        {
            Title = T("任务管家", "Mission Manager");
            root = new Grid { Background = background }; root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(265) });
            root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }); Content = root;
            sidebar = new StackPanel { Margin = new Thickness(22, 24, 20, 20) };
            sidebar.Children.Add(Text(T("任务管家", "Mission Manager"), 27, true));
            var brand = Text("GUARDIAN / WINDOWS", 11); brand.Foreground = secondary; sidebar.Children.Add(brand);
            sidebar.Children.Add(new Border { Height = 24 });
            sidebar.Children.Add(MakeButton(T("任务控制", "Chats"), delegate { currentView = "tasks"; BuildContent(); }));
            sidebar.Children.Add(MakeButton(T("操作记录", "Activity"), delegate { currentView = "events"; BuildContent(); }));
            sidebar.Children.Add(MakeButton(T("运行规则", "Rules"), delegate { currentView = "rules"; BuildContent(); }));
            sidebar.Children.Add(MakeButton(T("设置", "Settings"), delegate { currentView = "settings"; BuildContent(); }));
            sidebar.Children.Add(new Border { Height = 18 }); quotaPanel = new StackPanel(); sidebar.Children.Add(quotaPanel);
            sidebar.Children.Add(new Border { Height = 18 });
            var note = Text(T("关闭窗口后继续在系统托盘运行。", "Closing this window keeps the app running in the system tray."), 12); note.Foreground = secondary; sidebar.Children.Add(note);
            var left = new Border { BorderBrush = border, BorderThickness = new Thickness(0, 0, 1, 0), Child = new ScrollViewer { Content = sidebar, VerticalScrollBarVisibility = ScrollBarVisibility.Auto } };
            root.Children.Add(left);
            var scroll = new ScrollViewer { VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
            content = new StackPanel { Margin = new Thickness(28, 24, 28, 28) }; scroll.Content = content; Grid.SetColumn(scroll, 1); root.Children.Add(scroll);
            BuildContent();
        }
        void BuildContent()
        {
            content.Children.Clear();
            var top = new DockPanel { LastChildFill = true };
            var topButtons = new StackPanel { Orientation = Orientation.Horizontal };
            topButtons.Children.Add(MakeButton("中文 / EN", delegate { preferences.Language = preferences.Language == "en" ? "zh" : "en"; preferences.Save(); RebuildPresentation(); }));
            topButtons.Children.Add(MakeButton(T("刷新", "Refresh"), async delegate { await RefreshAsync(); }));
            DockPanel.SetDock(topButtons, Dock.Right); top.Children.Add(topButtons);
            top.Children.Add(Text(T("本机工作空间", "Local workspace"), 13)); content.Children.Add(top);
            noticeBlock = Text(notice, 13); noticeBlock.Foreground = secondary; content.Children.Add(noticeBlock);
            if (currentView == "events") { BuildEvents(); return; }
            if (currentView == "rules") { BuildRules(); return; }
            if (currentView == "settings") { BuildSettings(); return; }
            content.Children.Add(Text(T("让任务接着完成。", "Keep your work moving."), 28, true));
            stateBlock = Text("", 13); content.Children.Add(stateBlock);
            var global = new WrapPanel();
            globalButton = MakeButton(T("启用自动控制", "Enable automatic control"), delegate { ToggleGlobal(); }, true); global.Children.Add(globalButton);
            pauseAllButton = MakeButton(T("暂停所有受管任务", "Pause managed tasks"), async delegate {
                await PerformAsync(Json.Values("action", "pause_all", "revision", Json.Integer(snapshot, "control_revision")));
            }); pauseAllButton.IsEnabled = !fixtureMode; global.Children.Add(pauseAllButton); content.Children.Add(global);
            countBlock = Text("", 13); countBlock.Foreground = secondary; content.Children.Add(countBlock);
            taskControls = new WrapPanel { Margin = new Thickness(0, 8, 0, 10) };
            sourceBox = new ComboBox { Width = 155, Margin = new Thickness(0, 0, 10, 6), Padding = new Thickness(8, 5, 8, 5), Foreground = Brushes.Black };
            sourceBox.Items.Add(T("全部来源", "All sources")); sourceBox.Items.Add("Codex"); sourceBox.Items.Add("ChatGPT");
            sourceBox.SelectedIndex = source == "codex" ? 1 : source == "chatgpt" ? 2 : 0;
            sourceBox.SelectionChanged += delegate { source = sourceBox.SelectedIndex == 1 ? "codex" : sourceBox.SelectedIndex == 2 ? "chatgpt" : "all"; page = 0; RenderChats(); };
            taskControls.Children.Add(sourceBox);
            var searchLabel = Text(T("搜索聊天", "Search chats"), 12); searchLabel.VerticalAlignment = VerticalAlignment.Center; searchLabel.Margin = new Thickness(0, 0, 9, 6); taskControls.Children.Add(searchLabel);
            searchBox = new TextBox { Width = 320, Text = search, Padding = new Thickness(9, 6, 9, 6), Margin = new Thickness(0, 0, 10, 6),
                Background = surface, Foreground = foreground, BorderBrush = border, ToolTip = T("搜索聊天名称或 ID", "Search chat name or ID") };
            searchBox.TextChanged += delegate { search = searchBox.Text; page = 0; RenderChats(); }; taskControls.Children.Add(searchBox); content.Children.Add(taskControls);
            rowsPanel = new StackPanel(); content.Children.Add(rowsPanel);
            syncBlock = Text(T("每 5 秒读取后台缓存；ChatGPT 云端仅显示已知目录。", "Reads cached status every 5 seconds. Cloud ChatGPT entries are directory-only."), 12);
            syncBlock.Foreground = secondary; content.Children.Add(syncBlock);
            RenderHeader(); RenderChats();
        }
        void RenderSnapshot()
        {
            RenderQuota();
            if (noticeBlock != null) noticeBlock.Text = notice;
            if (currentView == "tasks") { RenderHeader(); RenderChats(); }
            else if (currentView == "events" && !busy) BuildContent();
            else if (currentView == "rules") BuildContent();
            BuildTrayMenu();
        }
        void RenderHeader()
        {
            if (stateBlock == null) return;
            bool enabled = Json.Bool(snapshot, "control_enabled");
            string state = enabled ? T("自动控制已启用", "Automatic control enabled") : Json.Bool(snapshot, "control_paused", true) ? T("自动控制已暂停", "Automatic control paused") : T("等待可靠连接，自动发送暂不可用", "Waiting for a reliable connection. Automatic sending is unavailable.");
            if (Healthy && !ControlAvailable) state += " · " + ControlConnectionNote();
            if (!String.IsNullOrEmpty(connectionError)) state += " · " + connectionError;
            else if (!Healthy && Json.Text(snapshot, "service_error") == "account_identity") state += " · " + T("请打开 ChatGPT 并登录账号", "Open ChatGPT and sign in");
            stateBlock.Text = state;
            globalButton.Content = Json.Bool(snapshot, "control_paused", true) ? T("启用自动控制", "Enable automatic control") : T("暂停自动控制", "Pause automatic control");
            globalButton.IsEnabled = !fixtureMode && !busy && baseUri != null && Json.Bool(snapshot, "running")
                && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy));
            pauseAllButton.IsEnabled = !fixtureMode && !busy && Healthy && ControlAvailable;
            var chats = Json.Rows(snapshot, "tasks");
            int active = chats.Count(x => Json.Text(Json.Child(x, "runtime"), "type") == "active");
            int waiting = chats.Count(x => Json.Text(x, "state") == "paused" || Scheduled(Json.Child(x, "plan")));
            countBlock.Text = T("聊天目录 ", "Chats ") + chats.Count + "     " + T("正在执行 ", "Running ") + active + "     " + T("等待恢复 / 预约 ", "Waiting / scheduled ") + waiting;
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
            var filtered = all.Where(x => (source == "all" || Json.Text(x, "category") == source)
                && (String.IsNullOrWhiteSpace(search) || (Json.Text(x, "name") + " " + Json.Text(x, "id")).IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0)).ToList();
            int pages = Math.Max(1, (filtered.Count + 19) / 20); page = Math.Min(page, pages - 1);
            var selected = filtered.Skip(page * 20).Take(20).ToList();
            var wanted = new List<UIElement>();
            foreach (var chat in selected)
            {
                string key = Json.Text(chat, "key"); ChatRow row;
                if (!rowCache.TryGetValue(key, out row)) { row = new ChatRow(this); rowCache[key] = row; }
                row.Update(chat); wanted.Add(row);
            }
            if (wanted.Count == 0)
            {
                string value = Healthy ? T("没有匹配的聊天。", "No matching chats.") : T("正在等待客户端账号与聊天目录。请打开 ChatGPT 并完成登录。", "Waiting for the client account and chat directory. Open ChatGPT and complete sign-in.");
                wanted.Add(Card(Text(value, 15), new Thickness(0, 8, 0, 16)));
            }
            bool same = rowsPanel.Children.Count == wanted.Count;
            if (same) for (int i = 0; i < wanted.Count; i++) if (rowsPanel.Children[i] != wanted[i]) same = false;
            if (!same && !rowsPanel.IsKeyboardFocusWithin) { rowsPanel.Children.Clear(); foreach (var element in wanted) rowsPanel.Children.Add(element); }
            if (pages > 1)
            {
                var paging = new WrapPanel();
                var prev = MakeButton(T("上一页", "Previous"), delegate { page = Math.Max(0, page - 1); RenderChats(); }); prev.IsEnabled = page > 0; paging.Children.Add(prev);
                paging.Children.Add(Text((page + 1) + " / " + pages, 14));
                var next = MakeButton(T("下一页", "Next"), delegate { page++; RenderChats(); }); next.IsEnabled = page + 1 < pages; paging.Children.Add(next);
                if (!rowsPanel.IsKeyboardFocusWithin) rowsPanel.Children.Add(paging);
            }
        }
        void RenderQuota()
        {
            if (quotaPanel == null) return; quotaPanel.Children.Clear();
            var usage = Json.Child(snapshot, "usage"); var account = Json.Child(usage, "account");
            string plan = Json.Text(account, "plan_type", T("待识别", "Not identified"));
            var knownPlans = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) { {"free","Free"}, {"go","Go"}, {"plus","Plus"}, {"pro","Pro"}, {"team","Team"}, {"business","Business"}, {"enterprise","Enterprise"}, {"edu","Edu"} };
            string knownPlan; if (knownPlans.TryGetValue(plan, out knownPlan)) plan = knownPlan;
            quotaPanel.Children.Add(Text(T("当前额度", "Current allowance") + " · " + plan, 16, true));
            foreach (var window in VisibleWindows(usage))
            {
                double remaining = Json.Number(window, "remaining", Double.NaN);
                var heading = Text(WindowTitle(Json.Number(window, "minutes")) + (Double.IsNaN(remaining) ? "" : "  " + remaining.ToString("0.#", CultureInfo.InvariantCulture) + "%"), 13); quotaPanel.Children.Add(heading);
                if (!Double.IsNaN(remaining) && remaining >= 0 && remaining <= 100)
                    quotaPanel.Children.Add(new ProgressBar { Minimum = 0, Maximum = 100, Value = remaining, Height = 7, Foreground = accent, Background = border, Margin = new Thickness(0, 0, 0, 8) });
                var reset = Text(T("下次刷新 ", "Resets ") + FormatTime(Json.Number(window, "reset")), 11); reset.Foreground = secondary; quotaPanel.Children.Add(reset);
            }
            string quotaState = Json.Text(usage, "quota_state");
            if (Json.Bool(usage, "blocked")) quotaPanel.Children.Add(Text(T("服务暂不允许使用", "Usage is blocked by the service"), 12));
            else if (quotaState == "service_only" && Json.Bool(usage, "service_allowed")) quotaPanel.Children.Add(Text(T("服务已允许使用，未提供固定窗口", "The service allows usage; no fixed window was provided."), 12));
            else if (VisibleWindows(usage).Count == 0) quotaPanel.Children.Add(Text(T("额度信息尚未核实", "Allowance has not been verified"), 12));
            if (Json.Bool(usage, "stale", true) || !String.IsNullOrEmpty(connectionError)) { var stale = Text(T("额度待同步 · 上次记录", "Awaiting sync · previous record"), 11); stale.Foreground = secondary; quotaPanel.Children.Add(stale); }
            quotaPanel.Children.Add(new Border { Height = 15 });
            string name = Json.Text(account, "name", Json.Text(account, "email", T("未登录账号", "Not signed in")));
            quotaPanel.Children.Add(Text(name, 16, true));
            string email = Json.Text(account, "email"); if (email != name) quotaPanel.Children.Add(Text(email, 12));
            string id = Json.Text(account, "id");
            if (id.Length > 0)
            {
                var idText = Text(T("账号 ID\n", "Account ID\n") + id, 11); idText.Foreground = secondary; quotaPanel.Children.Add(idText);
                quotaPanel.Children.Add(MakeButton(T("复制账号 ID", "Copy account ID"), delegate { try { Clipboard.SetText(id); } catch { } }));
            }
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
            content.Children.Add(Text(T("操作记录", "Activity"), 28, true));
            foreach (var item in Json.Rows(snapshot, "events").Take(100))
            {
                var block = new StackPanel(); block.Children.Add(Text(EventLabel(Json.Text(item, "state")), 15, true));
                block.Children.Add(Text(Json.Text(item, "name") + " · " + FormatTime(Json.Number(item, "created")), 12));
                string reason = Json.Text(Json.Child(item, "detail"), "reason"); if (reason.Length > 0) block.Children.Add(Text(reason, 12));
                content.Children.Add(Card(block, new Thickness(0, 0, 0, 10)));
            }
            if (Json.Rows(snapshot, "events").Count == 0) content.Children.Add(Text(T("暂无操作记录。", "No activity has been recorded."), 15));
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
            content.Children.Add(Text(T("运行规则", "Control rules"), 28, true));
            var policy = Json.Child(snapshot, "policy");
            content.Children.Add(Text(T("额度不足时暂停，可靠恢复后核对原会话并续做。", "Pause when allowance is low, then verify the original chat before resuming."), 16));
            content.Children.Add(Text(T("暂停阈值：", "Pause threshold: ") + "≤ " + Json.Number(policy, "pause", 10) + "%", 16));
            content.Children.Add(Text(T("恢复阈值：", "Resume threshold: ") + "≥ " + Json.Number(policy, "resume", 20) + "%", 16));
            content.Children.Add(Text(T("恢复连续确认：", "Recovery confirmation: ") + Json.Number(policy, "confirm_seconds", 5) + T(" 秒", " seconds"), 16));
            content.Children.Add(Text(T("界面每 5 秒读取缓存；正常采集间隔 ", "The interface reads the cache every 5 seconds. Collection waits ")
                + Json.Number(snapshot, "poll_seconds", 30).ToString("0.#", CultureInfo.InvariantCulture)
                + T(" 秒，临近额度阈值或有待执行预约时 ", " seconds normally, or ")
                + Json.Number(snapshot, "near_limit_poll_seconds", 10).ToString("0.#", CultureInfo.InvariantCulture)
                + T(" 秒，另加每轮处理耗时。", " seconds near limits or with pending scheduled work, plus each round's processing time."), 15));
            content.Children.Add(Text(T("服务许可、实际额度窗口、账号身份及原回合均须通过核验。人工保持、审批请求和新用户指令优先；不自动购买额度。", "Service permission, actual quota windows, account identity and the original turn must pass verification. Manual holds, approvals and new user input take priority. The app does not purchase allowance."), 15));
            content.Children.Add(Text(T("一次性预约确认送达后自动关闭。普通 ChatGPT 云端聊天目前仅显示已知目录。", "One-time schedules turn off after confirmed delivery. Ordinary cloud ChatGPT chats are directory-only."), 15));
        }
        void BuildSettings()
        {
            content.Children.Add(Text(T("设置", "Settings"), 28, true));
            var appearance = new StackPanel(); appearance.Children.Add(Text(T("外观与语言", "Appearance and language"), 18, true));
            var choices = new WrapPanel();
            foreach (string choice in new[] { "system", "light", "dark" })
            {
                string local = choice;
                choices.Children.Add(MakeButton(choice == "system" ? T("跟随系统", "System") : choice == "dark" ? T("深色", "Dark") : T("浅色", "Light"), delegate { preferences.Theme = local; preferences.Save(); RebuildPresentation(); }));
            }
            appearance.Children.Add(choices); appearance.Children.Add(MakeButton(T("切换为 English", "Switch to 简体中文"), delegate { preferences.Language = preferences.Language == "en" ? "zh" : "en"; preferences.Save(); RebuildPresentation(); }));
            content.Children.Add(Card(appearance, new Thickness(0, 0, 0, 16)));
            var startup = new StackPanel(); startup.Children.Add(Text(T("登录时启动", "Start at sign-in"), 18, true));
            var startupToggle = new CheckBox { Content = T("登录 Windows 后启动任务管家", "Start Mission Manager when signing in to Windows"), Foreground = foreground, Margin = new Thickness(0, 4, 0, 12), IsChecked = IsStartupEnabled() };
            StyleSwitch(startupToggle);
            startupToggle.Click += delegate { SetStartup(startupToggle.IsChecked == true); };
            startup.Children.Add(startupToggle); startup.Children.Add(MakeButton(T("打开启动应用设置", "Open startup settings"), delegate { OpenUri("ms-settings:startupapps"); }));
            content.Children.Add(Card(startup, new Thickness(0, 0, 0, 16)));
            var notifications = new StackPanel(); notifications.Children.Add(Text(T("通知", "Notifications"), 18, true));
            var notificationToggle = new CheckBox { Content = T("通知暂停、续接、发送失败及需处理的异常", "Notify on pauses, resumptions, delivery failures and actionable errors"), Foreground = foreground, Margin = new Thickness(0, 4, 0, 12), IsChecked = preferences.Notifications };
            StyleSwitch(notificationToggle);
            notificationToggle.Click += delegate { preferences.Notifications = notificationToggle.IsChecked == true; preferences.Save(); };
            notifications.Children.Add(notificationToggle); notifications.Children.Add(MakeButton(T("打开系统通知设置", "Open notification settings"), delegate { OpenUri("ms-settings:notifications"); }));
            notifications.Children.Add(Text(T("此开关保存应用通知偏好；实际显示仍受 Windows 通知设置限制。", "This switch saves the app's notification preference. Actual delivery remains subject to Windows notification settings."), 12));
            content.Children.Add(Card(notifications, new Thickness(0, 0, 0, 16)));
            var runtime = new StackPanel(); runtime.Children.Add(Text(T("后台与客户端", "Background service and client"), 18, true));
            runtime.Children.Add(Text(T("关闭主窗口后仍运行；从托盘退出后停止管家后台。Windows 进入睡眠时无法继续采集。", "Closing the window keeps the app running. Exiting from the tray stops its backend. Collection cannot continue while Windows is asleep."), 14));
            var awakeToggle = new CheckBox { Content = T("保持后台运行：防止空闲睡眠，允许熄屏", "Keep running: prevent idle sleep while allowing the display to turn off"), Foreground = foreground, Margin = new Thickness(0, 5, 0, 10), IsChecked = preferences.KeepAwake };
            StyleSwitch(awakeToggle);
            awakeToggle.Click += delegate { SetAwake(awakeToggle.IsChecked == true); awakeToggle.IsChecked = preferences.KeepAwake; };
            runtime.Children.Add(awakeToggle);
            runtime.Children.Add(Text(T("该选项不修改系统电源计划。合盖或手动睡眠仍按 Windows 系统策略处理。", "This option does not change the power plan. Lid closure and manual sleep still follow Windows system policy."), 12));
            var compatibility = Json.Child(snapshot, "compatibility");
            runtime.Children.Add(Text(T("客户端：", "Client: ") + Json.Text(compatibility, "version", T("尚未检测", "Not detected")) + " · " + Json.Text(compatibility, "status"), 13));
            if (!ControlAvailable) runtime.Children.Add(Text(ControlConnectionNote(), 13));
            runtime.Children.Add(Text(T("原生 Windows 预览版 · V0.2.1", "Native Windows preview · V0.2.1"), 12));
            var actions = new WrapPanel(); actions.Children.Add(MakeButton(T("打开电源设置", "Open power settings"), delegate { OpenUri("ms-settings:powersleep"); }));
            actions.Children.Add(MakeButton(T("打开本机数据目录", "Open local data folder"), delegate { Directory.CreateDirectory(preferences.DirectoryPath); OpenUri(preferences.DirectoryPath); })); runtime.Children.Add(actions);
            content.Children.Add(Card(runtime, new Thickness(0, 0, 0, 16)));
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
        void SetNotice(string value) { notice = value; if (noticeBlock != null) noticeBlock.Text = notice; }
        public void ToggleGlobal()
        {
            if (fixtureMode) return;
            if (Json.Bool(snapshot, "control_paused", true) && !ControlAvailable) { SetNotice(T("客户端控制尚未通过核验，暂不能启用自动控制。", "Client control has not passed verification. Automatic control cannot be enabled yet.")); return; }
            var action = Json.Bool(snapshot, "control_paused", true) ? "enable" : "pause";
            var ignored = PerformAsync(Json.Values("action", action, "revision", Json.Integer(snapshot, "control_revision")));
        }
        void StartHost()
        {
            if (host != null || fixtureMode || quitting) return;
            string directory = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(directory, "runtime", "python", "python.exe");
            string script = Path.Combine(directory, "backend", "app_host.py");
            if (!File.Exists(python) || !File.Exists(script)) { connectionError = T("应用文件不完整，请重新安装。", "Application files are incomplete. Reinstall the app."); RenderHeader(); return; }
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
                            Dispatcher.BeginInvoke(new Action(async delegate { baseUri = url; connectionError = ""; await RefreshAsync(); }));
                    }
                    catch (Exception) { }
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e) {
                    if (String.IsNullOrEmpty(e.Data)) return;
                    try { File.AppendAllText(Path.Combine(preferences.DirectoryPath, "native-host.log"), DateTime.UtcNow.ToString("o") + " " + e.Data + Environment.NewLine, Encoding.UTF8); } catch { }
                };
                process.Exited += delegate { Dispatcher.BeginInvoke(new Action(delegate {
                    if (!quitting) { baseUri = null; connectionError = T("后台已退出；本机记录保留。请重新打开应用。", "The backend exited. Local records are preserved. Reopen the app."); RenderHeader(); }
                })); };
                process.Start(); host = process; process.BeginOutputReadLine(); process.BeginErrorReadLine();
            }
            catch (Exception ex) { connectionError = ex.Message; RenderHeader(); }
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
            tray = new Forms.NotifyIcon { Icon = System.Drawing.SystemIcons.Shield, Text = "Mission Manager", Visible = true };
            tray.DoubleClick += delegate { Dispatcher.BeginInvoke(new Action(ShowMain)); };
            BuildTrayMenu();
        }
        void BuildTrayMenu()
        {
            if (tray == null) return;
            if (tray.ContextMenuStrip != null && tray.ContextMenuStrip.Visible) return;
            var menu = new Forms.ContextMenuStrip();
            var usage = Json.Child(snapshot, "usage");
            foreach (var window in VisibleWindows(usage))
            {
                double remaining = Json.Number(window, "remaining", Double.NaN);
                var label = new Forms.ToolStripMenuItem(WindowTitle(Json.Number(window, "minutes")) + " · " + (Double.IsNaN(remaining) ? "—" : remaining.ToString("0.#") + "%") + " · " + FormatTime(Json.Number(window, "reset"))) { Enabled = false };
                menu.Items.Add(label);
            }
            if (VisibleWindows(usage).Count == 0) menu.Items.Add(new Forms.ToolStripMenuItem(T("额度待同步", "Allowance awaiting sync")) { Enabled = false });
            menu.Items.Add(new Forms.ToolStripSeparator());
            AddTrayItem(menu, T("打开任务管家", "Open Mission Manager"), ShowMain);
            AddTrayItem(menu, Json.Bool(snapshot, "control_paused", true) ? T("恢复自动控制", "Resume automatic control") : T("暂停自动控制", "Pause automatic control"), ToggleGlobal,
                !busy && baseUri != null && Json.Bool(snapshot, "running") && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy)));
            AddTrayItem(menu, T("暂停所有受管任务", "Pause managed tasks"), async delegate { await PerformAsync(Json.Values("action", "pause_all", "revision", Json.Integer(snapshot, "control_revision"))); }, Healthy && ControlAvailable && !busy);
            AddTrayItem(menu, T("设置", "Settings"), delegate { currentView = "settings"; BuildContent(); ShowMain(); });
            var languages = new Forms.ToolStripMenuItem(T("语言", "Language"));
            AddTrayItem(languages, "简体中文", delegate { preferences.Language = "zh"; preferences.Save(); RebuildPresentation(); });
            AddTrayItem(languages, "English", delegate { preferences.Language = "en"; preferences.Save(); RebuildPresentation(); }); menu.Items.Add(languages);
            var themes = new Forms.ToolStripMenuItem(T("外观", "Appearance"));
            foreach (string choice in new[] { "system", "light", "dark" })
            {
                string value = choice;
                AddTrayItem(themes, choice == "system" ? T("跟随系统", "System") : choice == "dark" ? T("深色", "Dark") : T("浅色", "Light"), delegate { preferences.Theme = value; preferences.Save(); RebuildPresentation(); });
            }
            menu.Items.Add(themes); menu.Items.Add(new Forms.ToolStripSeparator()); AddTrayItem(menu, T("退出", "Exit"), Quit);
            var old = tray.ContextMenuStrip; tray.ContextMenuStrip = menu; if (old != null) old.Dispose();
        }
        void AddTrayItem(Forms.ContextMenuStrip menu, string label, Action action, bool enabled = true)
        { var item = new Forms.ToolStripMenuItem(label) { Enabled = enabled }; item.Click += delegate { Dispatcher.BeginInvoke(action); }; menu.Items.Add(item); }
        void AddTrayItem(Forms.ToolStripMenuItem menu, string label, Action action)
        { var item = new Forms.ToolStripMenuItem(label); item.Click += delegate { Dispatcher.BeginInvoke(action); }; menu.DropDownItems.Add(item); }
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
        void ShowMain() { Show(); if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal; Activate(); }
        void OnClosing(object sender, CancelEventArgs e)
        {
            if (fixtureMode || quitting) return; e.Cancel = true; Hide();
        }
        async void Quit()
        {
            if (quitting) return; quitting = true; if (timer != null) timer.Stop();
            SetThreadExecutionState(ExecutionContinuous);
            if (tray != null) { tray.Visible = false; tray.Dispose(); tray = null; }
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
        readonly TextBlock title, detail, stage, status, planLabel, receiptLabel;
        readonly CheckBox auto, schedule;
        readonly TextBox prompt;
        readonly Button save, now, open;
        Dictionary<string, object> chat = new Dictionary<string, object>();
        bool updating, dirty;
        int draftRevision;
        public ChatRow(MissionWindow window)
        {
            owner = window; Background = owner.SurfaceBrush; BorderBrush = owner.CardBorderBrush; BorderThickness = new Thickness(1); CornerRadius = new CornerRadius(9);
            Padding = new Thickness(17); Margin = new Thickness(0, 0, 0, 13);
            var columns = new Grid(); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(175) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(330) }); Child = columns;
            var info = new StackPanel { Margin = new Thickness(0, 0, 18, 0) }; columns.Children.Add(info);
            title = Label("", 16, true); info.Children.Add(title); detail = Label("", 11); detail.Foreground = owner.SecondaryBrush; info.Children.Add(detail);
            info.Children.Add(Label(owner.T("当前执行阶段", "Current execution stage"), 12, true));
            stage = Label("", 13); stage.MaxHeight = 130; stage.TextTrimming = TextTrimming.CharacterEllipsis; info.Children.Add(stage);
            var middle = new StackPanel { Margin = new Thickness(0, 0, 12, 0) }; Grid.SetColumn(middle, 1); columns.Children.Add(middle);
            status = Label("", 14, true); middle.Children.Add(status);
            auto = new CheckBox { Content = owner.T("自动控制", "Automatic control"), Foreground = owner.ForegroundBrush, Margin = new Thickness(0, 12, 0, 7) };
            owner.StyleSwitch(auto);
            auto.Click += async delegate { if (!updating) await owner.PerformAsync(Json.Values("action", "set_auto", "key", Json.Text(chat, "key"), "enabled", auto.IsChecked == true, "revision", Json.Integer(chat, "revision"))); };
            middle.Children.Add(auto);
            open = owner.MakeButton(owner.T("打开聊天", "Open chat"), delegate { owner.OpenChat(Json.Text(chat, "id")); }); middle.Children.Add(open);
            var right = new StackPanel(); Grid.SetColumn(right, 2); columns.Children.Add(right);
            schedule = new CheckBox { Content = owner.T("额度恢复后执行一次", "Run once after quota recovery"), Foreground = owner.ForegroundBrush, Margin = new Thickness(0, 0, 0, 6) };
            owner.StyleSwitch(schedule);
            schedule.Click += async delegate { if (!updating) await SavePlan(schedule.IsChecked == true); }; right.Children.Add(schedule);
            planLabel = Label("", 11); planLabel.Foreground = owner.SecondaryBrush; right.Children.Add(planLabel);
            prompt = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 60, MaxHeight = 120, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Background = owner.SurfaceBrush, Foreground = owner.ForegroundBrush, BorderBrush = owner.CardBorderBrush, Padding = new Thickness(8), MaxLength = 8000, Margin = new Thickness(0, 3, 0, 9) };
            prompt.TextChanged += delegate { if (!updating && !dirty) { dirty = true; draftRevision = Json.Integer(Json.Child(chat, "plan"), "revision"); } }; right.Children.Add(prompt);
            var buttons = new WrapPanel();
            save = owner.MakeButton(owner.T("保存并预约", "Save and schedule"), async delegate { await SavePlan(true); }); buttons.Children.Add(save);
            now = owner.MakeButton(owner.T("立刻执行", "Run now"), async delegate {
                await owner.PerformAsync(Json.Values("action", "execute_now", "key", Json.Text(chat, "key"), "prompt", prompt.Text, "revision", Json.Integer(chat, "revision"), "request_id", Guid.NewGuid().ToString("D")));
            }, true); buttons.Children.Add(now); right.Children.Add(buttons);
            receiptLabel = Label("", 11); receiptLabel.Foreground = owner.SecondaryBrush; right.Children.Add(receiptLabel);
            bool layoutInitialized = false, narrowLayout = false;
            SizeChanged += delegate {
                bool narrow = ActualWidth - Padding.Left - Padding.Right < 850;
                if (layoutInitialized && narrow == narrowLayout) return;
                layoutInitialized = true; narrowLayout = narrow;
                columns.ColumnDefinitions.Clear(); columns.RowDefinitions.Clear();
                Grid.SetRow(info, 0); Grid.SetColumn(info, 0);
                if (narrow)
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(175) });
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    Grid.SetColumnSpan(info, 2); info.Margin = new Thickness(0, 0, 0, 12);
                    Grid.SetRow(middle, 1); Grid.SetColumn(middle, 0);
                    Grid.SetRow(right, 1); Grid.SetColumn(right, 1);
                }
                else
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(175) });
                    columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(330) });
                    Grid.SetColumnSpan(info, 1); info.Margin = new Thickness(0, 0, 18, 0);
                    Grid.SetRow(middle, 0); Grid.SetColumn(middle, 1);
                    Grid.SetRow(right, 0); Grid.SetColumn(right, 2);
                }
            };
        }
        TextBlock Label(string value, int size, bool bold = false)
        { return new TextBlock { Text = value, FontSize = size, Foreground = owner.ForegroundBrush, FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 7) }; }
        async Task SavePlan(bool enabled)
        {
            var plan = Json.Child(chat, "plan"); int revision = enabled && dirty ? draftRevision : Json.Integer(plan, "revision");
            string text = enabled ? prompt.Text : Json.Text(plan, "prompt", "继续任务");
            await owner.PerformAsync(Json.Values("action", "set_plan", "key", Json.Text(chat, "key"), "enabled", enabled, "prompt", text, "revision", revision));
            // A saved prompt is considered clean only after the refreshed plan
            // matches it, never merely because the HTTP request was attempted.
            var refreshed = Json.Rows(owner.Snapshot, "tasks").FirstOrDefault(x => Json.Text(x, "key") == Json.Text(chat, "key"));
            if (refreshed != null && Json.Text(Json.Child(refreshed, "plan"), "prompt") == prompt.Text
                    && Json.Integer(Json.Child(refreshed, "plan"), "revision") != revision) dirty = false;
        }
        public void Update(Dictionary<string, object> value)
        {
            chat = value; updating = true;
            title.Text = Json.Text(chat, "name");
            string source = Json.Text(chat, "category") == "codex" ? owner.T("Codex · 本机", "Codex · Local")
                : Json.Text(chat, "source_label").IndexOf("Work", StringComparison.OrdinalIgnoreCase) >= 0 ? owner.T("ChatGPT Work · 云端", "ChatGPT Work · Cloud") : owner.T("ChatGPT · 目录", "ChatGPT · Directory");
            detail.Text = source + " / " + Json.Text(chat, "id");
            var execution = Json.Child(chat, "execution_stage");
            stage.Text = Json.Text(execution, "text", owner.T("当前尚无可读取的公开执行进展。", "No public execution progress is available yet."));
            stage.ToolTip = stage.Text;
            status.Text = Status(); auto.IsChecked = ChatControlPolicy.AutomaticOn(chat);
            bool controllable = Json.Bool(chat, "can_control") && owner.ControlAvailable, available = owner.Healthy && !owner.IsBusy;
            auto.IsEnabled = ChatControlPolicy.CanToggleAutomatic(chat, owner.Healthy, owner.ControlAvailable, owner.IsBusy, owner.CanSubmitLocalChange);
            var plan = Json.Child(chat, "plan"); bool scheduled = MissionWindow.Scheduled(plan);
            schedule.IsChecked = scheduled;
            var usage = Json.Child(owner.Snapshot, "usage"); bool canSchedule = Json.Bool(usage, "scheduling_available", MissionWindow.VisibleWindows(usage).Count > 0);
            schedule.IsEnabled = ChatControlPolicy.CanToggleSchedule(chat, owner.Healthy, owner.ControlAvailable, owner.IsBusy, owner.CanSubmitLocalChange, canSchedule);
            string planState = Json.Text(plan, "state", "off");
            planLabel.Text = PlanLabel(planState);
            double minutes = Json.Number(plan, "armed_window_minutes");
            if (minutes > 0) planLabel.Text += " · " + owner.WindowTitle(minutes) + " · " + MissionWindow.FormatTime(Json.Number(plan, "armed_window_reset"));
            if (!canSchedule && !scheduled) planLabel.Text += owner.T(" · 未提供固定刷新窗口", " · No fixed reset window");
            if (!dirty) { prompt.Text = Json.Text(plan, "prompt", "继续任务"); draftRevision = Json.Integer(plan, "revision"); }
            prompt.IsReadOnly = !controllable; save.IsEnabled = controllable && available && canSchedule && planState != "sending";
            var runtime = Json.Child(chat, "runtime"); var immediate = Json.Child(chat, "immediate"); string receipt = Json.Text(immediate, "state");
            IEnumerable flags = Json.Get(runtime, "activeFlags") as IEnumerable; bool waitingInput = flags != null && flags.Cast<object>().Any();
            now.IsEnabled = controllable && available && Json.Text(runtime, "type") != "active" && !waitingInput
                && receipt != "pending" && receipt != "checking" && receipt != "sending" && planState != "sending" && PermitsImmediate(usage);
            receiptLabel.Text = receipt.Length > 0 ? ReceiptLabel(receipt) + " " + Json.Text(immediate, "message") : Json.Text(chat, "capability_note");
            if (Json.Text(chat, "auto_error").Length > 0) receiptLabel.Text += " " + Json.Text(chat, "auto_error");
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
                    if (args.Length < 3) throw new ArgumentException("Usage: --ui-self-test fixture.json preview.png [zh|en] [system|light|dark]");
                    string language = "zh", theme = "system"; int positional = 0;
                    for (int index = 3; index < args.Length; index++)
                    {
                        if (args[index] == "--language" && index + 1 < args.Length) language = args[++index];
                        else if (args[index] == "--theme" && index + 1 < args.Length) theme = args[++index];
                        else if (positional++ == 0) language = args[index];
                        else if (positional == 2) theme = args[index];
                        else throw new ArgumentException("Unknown fixture argument.");
                    }
                    var fixture = Json.Parse(File.ReadAllText(args[1])); var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                    var window = new MissionWindow(true, fixture, language, theme);
                    int renderExit = 0;
                    app.Startup += delegate { window.Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, new Action(delegate {
                        try
                        {
                        // Render a detached native content tree at a fixed size.
                        // No HWND/non-client area or remote desktop dimensions
                        // participate in this offline fixture capture.
                        var view = window.Content as FrameworkElement;
                        if (view == null) throw new InvalidOperationException("Native content is unavailable.");
                        window.Content = null;
                        System.Windows.Documents.TextElement.SetFontFamily(view, window.FontFamily);
                        System.Windows.Documents.TextElement.SetFontSize(view, window.FontSize);
                        System.Windows.Documents.TextElement.SetForeground(view, window.Foreground);
                        const int width = 1420, height = 960;
                        view.Width = width; view.Height = height;
                        view.Measure(new Size(width, height)); view.Arrange(new Rect(0, 0, width, height)); view.UpdateLayout();
                        var image = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32); image.Render(view);
                        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image)); using (var file = File.Create(args[2])) encoder.Save(file);
                        File.WriteAllText(args[2] + ".json", Json.Stringify(Json.Values("native", true, "ui", "WPF", "webView", false, "hostStarted", false, "messagesSent", 0,
                            "fixtureChats", Json.Rows(fixture, "tasks").Count, "renderedRoot", "content", "width", width, "height", height,
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
