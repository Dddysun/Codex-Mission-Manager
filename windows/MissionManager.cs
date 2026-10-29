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

    // Pure presentation policy: no client access, task routing or permission
    // changes. Unknown evidence remains unknown on both desktop platforms.
    static class QuotaRestorationEvents
    {
        static string T(bool english, string zh, string en) { return english ? en : zh; }
        public static bool IsRestored(Dictionary<string, object> item) { return Json.Text(item, "state") == "quota_restored"; }
        public static bool IsGlobal(Dictionary<string, object> item)
        { return IsRestored(item) || (item.ContainsKey("thread_id") && String.IsNullOrWhiteSpace(Json.Text(item, "thread_id"))); }
        public static string ScopeTitle(Dictionary<string, object> item, bool english)
        {
            if (IsRestored(item)) return T(english, "全局额度事件", "Global quota event");
            if (IsGlobal(item)) return T(english, "全局控制", "Global control");
            return Json.Text(item, "name", T(english, "全局控制", "Global control"));
        }
        public static string Category(string value, bool english)
        {
            switch (value)
            {
                case "user_reset": return T(english, "用户恢复（推断）", "User reset (inferred)");
                case "official_scheduled_reset": return T(english, "周期重置（推断）", "Scheduled reset (inferred)");
                case "official_independent_reset": return T(english, "额外重置（推断）", "Extra reset (inferred)");
                default: return T(english, "额度恢复", "Quota restored");
            }
        }
        static double Number(Dictionary<string, object> item, string key)
        { return Json.Number(item, key, Double.NaN); }
        static bool Finite(double value) { return !Double.IsNaN(value) && !Double.IsInfinity(value); }
        static bool KnownCount(double value) { return Finite(value) && value >= 0 && Math.Round(value) == value; }
        public static string Percent(Dictionary<string, object> item, string key, bool english)
        {
            double value = Number(item, key);
            return Finite(value) && value >= 0 && value <= 100 ? value.ToString("0.0", CultureInfo.InvariantCulture) + "%" : T(english, "未提供", "Unavailable");
        }
        public static string Count(Dictionary<string, object> item, string key, bool english)
        {
            double value = Number(item, key);
            return KnownCount(value) ? value.ToString("G", CultureInfo.InvariantCulture) : T(english, "未提供", "Unavailable");
        }
        static string Time(Dictionary<string, object> item, string key, bool english)
        {
            double value = Number(item, key);
            return Finite(value) && value > 0 ? MissionWindow.FormatTime(value) : T(english, "未提供", "Unavailable");
        }
        static string WindowTitle(Dictionary<string, object> item, bool english)
        {
            double minutes = Number(item, "minutes");
            if (!Finite(minutes) || minutes <= 0) return T(english, "额度窗口未提供", "Quota window not provided");
            if (minutes == 300) return T(english, "五小时额度", "5-hour quota");
            if (minutes == 10080) return T(english, "周额度", "Weekly quota");
            if (minutes % 1440 == 0) return (minutes / 1440).ToString("0", CultureInfo.InvariantCulture) + T(english, "天额度", "-day quota");
            if (minutes % 60 == 0) return (minutes / 60).ToString("0", CultureInfo.InvariantCulture) + T(english, "小时额度", "-hour quota");
            return minutes.ToString("0", CultureInfo.InvariantCulture) + T(english, "分钟额度", "-minute quota");
        }
        public static string Summary(Dictionary<string, object> item, bool english)
        {
            var windows = Json.Rows(Json.Child(item, "detail"), "windows");
            if (windows.Count == 0) return T(english, "余额变化待核实", "Balance change unverified");
            return String.Join(" · ", windows.Select(window => WindowTitle(window, english) + " " +
                Percent(window, "previous_remaining", english).Replace(".0%", "%") + " → " +
                Percent(window, "remaining", english).Replace(".0%", "%")));
        }
        public static List<string> Lines(Dictionary<string, object> item, bool english)
        {
            var lines = new List<string>(); if (!IsRestored(item)) return lines;
            var detail = Json.Child(item, "detail");
            lines.Add(T(english, "分类基于余额、时间及权益变化推断。", "Classification inferred from balance, time and credit changes."));
            if (Json.Text(detail, "category") == "user_reset") lines.Add(T(english, "依据权益变化判定", "Inferred from credit changes"));
            lines.Add(T(english, "观测时间：", "Observed: ") + Time(detail, "previous_observed_at", english) + " → " + Time(detail, "observed_at", english));
            var windows = Json.Rows(detail, "windows");
            if (windows.Count == 0) lines.Add(T(english, "未提供可核实的额度窗口变化。", "Verified quota-window changes were not provided."));
            foreach (var window in windows)
            {
                lines.Add(WindowTitle(window, english) + T(english, " · 余额 ", " · Balance ") + Percent(window, "previous_remaining", english) + " → " + Percent(window, "remaining", english));
                lines.Add(T(english, "刷新时间：", "Reset time: ") + Time(window, "previous_reset", english) + " → " + Time(window, "reset", english));
                string classification = Json.Text(window, "classification");
                if (classification.Length > 0) lines.Add(T(english, "窗口判定：", "Window classification: ") + Category(classification, english));
            }
            var credits = Json.Child(detail, "reset_credits");
            if (KnownCount(Number(credits, "previous_available_count")) || KnownCount(Number(credits, "available_count")))
                lines.Add(T(english, "重置权益次数：", "Reset credits: ") + Count(credits, "previous_available_count", english) + " → " + Count(credits, "available_count", english));
            else lines.Add(T(english, "重置权益次数未提供。", "Reset-credit counts were not provided."));
            return lines;
        }
        public static bool SelfTest()
        {
            var window = Json.Values("minutes", 300, "previous_remaining", 2, "remaining", 100,
                "previous_reset", 1793152800, "reset", 1793170800, "classification", "user_reset");
            var detail = Json.Values("category", "user_reset", "previous_observed_at", 1793152700, "observed_at", 1793152800,
                "classification_basis", "fixture_evidence", "official_reason", null, "windows", new object[] { window },
                "reset_credits", Json.Values("previous_available_count", 2, "available_count", 1, "delta", -1));
            var item = Json.Values("state", "quota_restored", "thread_id", null, "name", "ghost task must stay hidden", "detail", detail);
            var lines = Lines(item, true);
            if (Summary(item, true) != "5-hour quota 2% → 100%" || Summary(Json.Values("detail", Json.Values()), true) != "Balance change unverified") return false;
            if (!IsGlobal(item) || ScopeTitle(item, true) != "Global quota event" || lines.Any(line => line.Contains("ghost task"))) return false;
            if (!lines.Any(line => line.Contains("2.0% → 100.0%")) || !lines.Any(line => line == "Reset credits: 2 → 1") || !lines.Any(line => line == "Inferred from credit changes")) return false;
            foreach (string category in new[] { "user_reset", "official_scheduled_reset", "official_independent_reset", "unattributed", "future_category" })
                if (Category(category, false).Length == 0 || Category(category, true).Length == 0) return false;
            if (Category("future_category", true) != "Quota restored") return false;
            detail["reset_credits"] = Json.Values("previous_available_count", null, "available_count", 0);
            if (!Lines(item, true).Contains("Reset credits: Unavailable → 0")) return false;
            detail["reset_credits"] = Json.Values("previous_available_count", null, "available_count", null);
            if (!Lines(item, true).Contains("Reset-credit counts were not provided.")) return false;
            var missing = Json.Values(); if (Percent(missing, "remaining", true) != "Unavailable" || Count(missing, "available_count", true) != "Unavailable") return false;
            var task = Json.Values("state", "running", "thread_id", "fixture-chat", "name", "Existing task");
            if (IsGlobal(task) || ScopeTitle(task, true) != "Existing task" || Lines(task, true).Count != 0) return false;
            task["thread_id"] = null; if (ScopeTitle(task, true) != "Global control") return false;
            task.Remove("thread_id"); return ScopeTitle(task, true) == "Existing task";
        }
    }

    static class NotificationCopy
    {
        public static string Title(string value, bool english)
        {
            string title = value ?? "";
            foreach (string prefix in new[] { "TOKEN榨汁机：", "榨汁机：", "任务管家：", "额度管家：" })
                if (title.StartsWith(prefix, StringComparison.Ordinal)) { title = title.Substring(prefix.Length); break; }
            if (!english) return "TOKEN榨汁机：" + (title.Length == 0 ? "状态更新" : title);
            var names = new Dictionary<string, string> {
                {"任务需要检查", "Review needed"}, {"已暂停任务", "Tasks paused"}, {"已登记额度中断", "Quota interruption recorded"},
                {"已恢复任务", "Tasks resumed"}, {"防睡眠保护未启动", "Keep-awake unavailable"}, {"额度不足", "Low quota"},
                {"额度预警", "Quota warning"}, {"额度已恢复", "Quota restored"}, {"监测不可用", "Monitoring unavailable"},
                {"已发送预约指令", "Scheduled instruction sent"}, {"即时发送需要处理", "Delivery needs attention"} };
            string label; return names.TryGetValue(title, out label) ? "TokenMax: " + label : "TokenMax";
        }
        public static bool SelfTest()
        { return Title("额度管家：额度已恢复", true) == "TokenMax: Quota restored"
            && Title("任务管家：已暂停任务", false) == "TOKEN榨汁机：已暂停任务"
            && Title("TOKEN榨汁机：即时发送需要处理", true) == "TokenMax: Delivery needs attention"
            && Title("unknown", true) == "TokenMax"; }
    }

    // The API owns origin classification. Older or unknown values stay in the
    // automatic bucket; filtering never rewrites the cached event dictionaries.
    static class ActivityEventFilter
    {
        public static string Normalize(string value) { return value == "user" || value == "automatic" ? value : "all"; }
        public static string Origin(Dictionary<string, object> item) { return Json.Text(item, "origin") == "user" ? "user" : "automatic"; }
        public static List<Dictionary<string, object>> Apply(IEnumerable<Dictionary<string, object>> events, string selection)
        {
            string filter = Normalize(selection);
            return events.Take(200).Where(item => filter == "all" || Origin(item) == filter).ToList();
        }
        public static bool SelfTest()
        {
            var events = new List<Dictionary<string, object>> {
                Json.Values("id", 1, "origin", "user", "state", "quota_restored"),
                Json.Values("id", 2, "origin", "automatic"), Json.Values("id", 3),
                Json.Values("id", 4, "origin", "future_origin"), Json.Values("id", 5, "origin", null),
                Json.Values("id", 6, "origin", "automatic", "detail", Json.Values("origin", "user", "category", "user_reset"))
            };
            string before = Json.Stringify(events);
            if (Apply(events, "all").Count != 6 || Apply(events, "user").Count != 1 || Apply(events, "automatic").Count != 5) return false;
            if (Apply(events, "future_filter").Count != 6 || Apply(events, "user")[0] != events[0]) return false;
            if (Origin(events[2]) != "automatic" || Origin(events[3]) != "automatic" || Origin(events[5]) != "automatic") return false;
            if (Json.Stringify(events) != before || events.Count != 6) return false;
            var longHistory = Enumerable.Range(0, 201).Select(index => Json.Values("id", index, "origin", index == 200 ? "user" : "automatic")).ToList();
            return Apply(longHistory, "all").Count == 200 && Apply(longHistory, "user").Count == 0
                && Apply(longHistory, "automatic").Count == 200 && longHistory.Count == 201
                && Apply(new List<Dictionary<string, object>>(), "user").Count == 0;
        }
    }

    sealed class Preferences
    {
        public string Language = CultureInfo.CurrentUICulture.Name.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh" : "en";
        public string Theme = "system";
        public string Accent = "green";
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
                Language = Json.Text(data, "language", Language); Theme = Json.Text(data, "theme", "system"); Accent = ThemePalette.Normalize(Json.Text(data, "accent", "green"));
                Notifications = Json.Bool(data, "notifications");
                KeepAwake = Json.Bool(data, "keep_awake");
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            catch (ArgumentException) { }
        }
        public bool TrySave(out Exception failure)
        {
            failure = null;
            try
            {
                Directory.CreateDirectory(DirectoryPath);
                string file = Path.Combine(DirectoryPath, "native-preferences.json");
                File.WriteAllText(file + ".tmp", Json.Stringify(Json.Values("language", Language, "theme", Theme, "accent", Accent, "notifications", Notifications, "keep_awake", KeepAwake)), new UTF8Encoding(false));
                if (File.Exists(file)) File.Replace(file + ".tmp", file, null);
                else File.Move(file + ".tmp", file);
                return true;
            }
            catch (Exception ex) { failure = ex; return false; }
        }

    }

    static class ThemePalette
    {
        public static readonly string[] Keys = { "green", "blue", "purple", "yellow" };
        public static string Normalize(string value) { return Keys.Contains(value) ? value : "green"; }
        public static string[] Colors(string value, bool dark)
        {
            switch (Normalize(value))
            {
                case "blue": return dark ? new[] { "#85B4F0", "#10223B", "#0E1724", "#223149" } : new[] { "#326CB5", "#FFFFFF", "#162638", "#2D435F" };
                case "purple": return dark ? new[] { "#B39ADE", "#21182F", "#171222", "#30243F" } : new[] { "#7856B1", "#FFFFFF", "#241E34", "#423553" };
                case "yellow": return dark ? new[] { "#E5CA80", "#2D2411", "#1E1A11", "#3C331E" } : new[] { "#D9B95F", "#302717", "#302A1B", "#514832" };
                default: return dark ? new[] { "#7FB795", "#102117", "#0D1712", "#2A332F" } : new[] { "#3F765F", "#FFFFFF", "#192822", "#35423D" };
            }
        }
        public static bool SelfTest()
        {
            if (Normalize("unknown") != "green") return false;
            foreach (string key in Keys) foreach (bool dark in new[] { false, true })
            {
                var c = Colors(key, dark); if (c.Length != 4 || c.Any(x => x.Length != 7 || !x.StartsWith("#", StringComparison.Ordinal))) return false;
                if (c[0] == c[1] || c[2] == c[3]) return false;
            }
            return Colors("yellow", false)[1] == "#302717";
        }
    }

    static class RulesPolicy
    {
        public static readonly string[] Fields = { "pause_remaining", "resume_remaining", "poll_seconds", "near_limit_poll_seconds", "recovery_confirm_seconds", "ui_poll_seconds" };
        public static readonly int[] Defaults = { 10, 20, 30, 10, 5, 5 };
        public static readonly int[] Minimums = { 1, 5, 10, 5, 3, 2 };
        public static readonly int[] Maximums = { 50, 95, 300, 60, 60, 30 };
        public static Dictionary<string, object> DefaultsObject()
        { var value = new Dictionary<string, object>(); for (int index = 0; index < Fields.Length; index++) value[Fields[index]] = Defaults[index]; return value; }
        public static bool Parse(IDictionary<string, string> draft, out Dictionary<string, object> value, out string error)
        {
            value = new Dictionary<string, object>(); error = "";
            for (int index = 0; index < Fields.Length; index++)
            {
                string text; int number; if (!draft.TryGetValue(Fields[index], out text) || !Int32.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out number)
                    || number < Minimums[index] || number > Maximums[index]) { error = Fields[index]; return false; }
                value[Fields[index]] = number;
            }
            if (Json.Integer(value, "resume_remaining") < Json.Integer(value, "pause_remaining") + 5) { error = "resume_margin"; return false; }
            if (Json.Integer(value, "near_limit_poll_seconds") > Json.Integer(value, "poll_seconds")) { error = "near_interval"; return false; }
            return true;
        }
        public static bool SelfTest()
        {
            var draft = new Dictionary<string, string>(); for (int i = 0; i < Fields.Length; i++) draft[Fields[i]] = Defaults[i].ToString(CultureInfo.InvariantCulture);
            Dictionary<string, object> parsed; string error; if (!Parse(draft, out parsed, out error)) return false;
            draft["resume_remaining"] = "14"; if (Parse(draft, out parsed, out error) || error != "resume_margin") return false;
            draft["resume_remaining"] = "20"; draft["near_limit_poll_seconds"] = "31"; if (Parse(draft, out parsed, out error) || error != "near_interval") return false;
            draft["near_limit_poll_seconds"] = "10"; draft["pause_remaining"] = "1.5"; if (Parse(draft, out parsed, out error)) return false;
            draft["pause_remaining"] = "10"; draft["ui_poll_seconds"] = "1"; return !Parse(draft, out parsed, out error);
        }
    }

    // Startup diagnostics must survive a non-writable application data folder.
    // Each owned process gets a separate, bounded in-memory buffer. No stderr
    // from an older process can replace a newer process's connection state.
    sealed class StartupDiagnostic
    {
        const int MaximumLines = 12, MaximumCharacters = 4096;
        readonly object gate = new object();
        readonly List<string> lines = new List<string>();
        int characters;
        bool appDataFailure, genericAccessFailure, logWriteFailure;
        public static string Shorten(string value, int length)
        {
            value = (value ?? "").Replace('\0', ' ').Replace('\r', ' ').Replace('\n', ' ').Trim();
            return value.Length <= length ? value : value.Substring(0, length - 1) + "…";
        }
        public static bool IsAccessFailure(string message)
        {
            string value = (message ?? "").ToLowerInvariant();
            return value.Contains("app_data_not_writable") || value.Contains("permissionerror") || value.Contains("permission denied") || value.Contains("unauthorizedaccess")
                || value.Contains("access denied") || value.Contains("access is denied") || value.Contains("accessdenied")
                || value.Contains("winerror 5") || value.Contains("拒绝访问") || value.Contains("访问被拒绝");
        }
        public static bool IsAccessFailure(Exception error)
        { return error is UnauthorizedAccessException || error is System.Security.SecurityException || (error != null && IsAccessFailure(error.GetType().Name + ": " + error.Message)); }
        public void Append(string line)
        {
            if (String.IsNullOrWhiteSpace(line)) return;
            string value = Shorten(line, 768);
            lock (gate)
            {
                appDataFailure = appDataFailure || line.IndexOf("app_data_not_writable", StringComparison.OrdinalIgnoreCase) >= 0;
                genericAccessFailure = genericAccessFailure || IsAccessFailure(line); lines.Add(value); characters += value.Length;
                while (lines.Count > MaximumLines || characters > MaximumCharacters) { characters -= lines[0].Length; lines.RemoveAt(0); }
            }
        }
        public void RecordDataDirectoryFailure(Exception error)
        { lock (gate) { appDataFailure = appDataFailure || IsAccessFailure(error); } }
        public void RecordLogFailure(Exception error)
        { lock (gate) { logWriteFailure = true; appDataFailure = appDataFailure || IsAccessFailure(error); } }
        public static string AccessHint(bool chinese, string directory)
        {
            return chinese ? "当前用户无法写入应用数据目录。请在文件夹属性的“安全”中核对读写权限后重试。目录：" + directory
                : "The current user cannot write to the app data folder. Check read/write access in the folder's Security properties, then retry. Folder: " + directory;
        }
        public string Describe(bool chinese, string directory)
        {
            lock (gate)
            {
                if (appDataFailure) return AccessHint(chinese, directory);
                string last = "";
                for (int index = lines.Count - 1; index >= 0; index--)
                {
                    string line = lines[index]; if (line.StartsWith("File ", StringComparison.Ordinal) || line.StartsWith("Traceback", StringComparison.Ordinal)) continue;
                    if (line.IndexOf("Error", StringComparison.OrdinalIgnoreCase) >= 0 || line.IndexOf("Exception", StringComparison.OrdinalIgnoreCase) >= 0) { last = Shorten(line, 220); break; }
                }
                if (last.Length == 0 && lines.Count > 0) last = Shorten(lines[lines.Count - 1], 220);
                if (genericAccessFailure) last += (last.Length > 0 ? " " : "") + (chinese ? "启动所需文件或程序的访问被拒绝，请核对当前用户的访问权限。" : "Access to a required startup file or program was denied. Check access for the current user.");
                if (logWriteFailure) last += (last.Length > 0 ? " " : "") + (chinese ? "诊断日志未能保存，请检查应用数据目录是否可写。目录：" : "The diagnostic log could not be saved. Check that the app data folder is writable. Folder: ") + directory;
                return last;
            }
        }
        public static bool SelfTest()
        {
            var denied = new StartupDiagnostic(); denied.Append("PermissionError: [WinError 5] Access is denied");
            denied.RecordLogFailure(new UnauthorizedAccessException("fixture log is not writable"));
            if (!denied.Describe(true, "fixture-app-data").Contains("读写权限") || !denied.Describe(false, "fixture-app-data").Contains("Security properties")) return false;
            for (int index = 0; index < 100; index++) denied.Append(new String('x', 10000));
            if (denied.lines.Count > MaximumLines || denied.characters > MaximumCharacters || !denied.Describe(false, "fixture-app-data").Contains("cannot write")) return false;
            var early = new StartupDiagnostic(); early.Append("app_data_not_writable: Current account lacks application data access");
            if (!early.Describe(false, "fixture-app-data").Contains("Security properties")) return false;
            var runtimeAccess = new StartupDiagnostic(); runtimeAccess.Append("PermissionError: [WinError 5] Cannot execute fixture-runtime.exe");
            string runtimeMessage = runtimeAccess.Describe(false, "fixture-app-data");
            if (!runtimeMessage.Contains("fixture-runtime.exe") || !runtimeMessage.Contains("required startup") || runtimeMessage.Contains("app data") || runtimeMessage.Contains("Security properties")) return false;
            var imports = new StartupDiagnostic(); imports.Append("Traceback (most recent call last):"); imports.Append("ModuleNotFoundError: No module named fixture_missing");
            return imports.Describe(false, "fixture-app-data").Contains("fixture_missing");
        }
    }

    sealed class TrayPopupWindow : Window
    {
        // Deterministically exercises the real Deactivated callback in the
        // offline lifecycle test, even on a non-interactive CI desktop.
        public void RaiseDeactivatedForFixture() { OnDeactivated(EventArgs.Empty); }
    }

    sealed class ExitWork
    {
        public Action RequestStop, ForceStop, Dispose;
        public Func<int, bool> WaitForExit;
    }

    sealed class ExitResult
    {
        public bool GracefulExit, ForceAttempted, ExitConfirmed, DisposeCompleted;
        public int Errors;
    }

    static class ExitCleanup
    {
        // Match the backend's bounded cleanup budget. Every blocking process
        // operation, including pipe writes and Dispose, stays off the UI thread.
        public const int GraceMilliseconds = 6000;
        public const int ForceMilliseconds = 1750;
        public const int DisposeMilliseconds = 250;
        public static async Task<bool> BoundedAsync(Action action, int milliseconds)
        {
            var work = Task.Run(delegate { try { action(); } catch (Exception) { } });
            return await Task.WhenAny(work, Task.Delay(milliseconds)) == work;
        }
        static void Attempt(Action action, ExitResult result)
        {
            try { if (action != null) action(); }
            catch (Exception) { Interlocked.Increment(ref result.Errors); }
        }
        static bool Wait(ExitWork work, int milliseconds, ExitResult result)
        {
            try { return work.WaitForExit != null && work.WaitForExit(milliseconds); }
            catch (Exception) { Interlocked.Increment(ref result.Errors); return false; }
        }
        public static async Task<ExitResult> StopAsync(ExitWork work, int graceMilliseconds = GraceMilliseconds,
                int forceMilliseconds = ForceMilliseconds, int disposeMilliseconds = DisposeMilliseconds)
        {
            var result = new ExitResult(); if (work == null) return result;
            bool exited = false;
            bool completed = await BoundedAsync(delegate {
                Attempt(work.RequestStop, result); exited = Wait(work, graceMilliseconds, result);
            }, graceMilliseconds);
            result.GracefulExit = completed && exited; result.ExitConfirmed = result.GracefulExit;
            if (!result.GracefulExit)
            {
                result.ForceAttempted = true; bool forcedExit = false;
                bool forcedCompleted = await BoundedAsync(delegate {
                    Attempt(work.ForceStop, result); forcedExit = Wait(work, forceMilliseconds, result);
                }, forceMilliseconds);
                result.ExitConfirmed = forcedCompleted && forcedExit;
            }
            result.DisposeCompleted = await BoundedAsync(delegate { Attempt(work.Dispose, result); }, disposeMilliseconds);
            return result;
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
        JuicerLogo sidebarLogo;
        readonly HashSet<string> expandedEvents = new HashSet<string>();
        System.Drawing.Icon trayBrandIcon;
        DispatcherTimer timer;
        bool refreshing, busy, quitting, firstNotices = true, lifecycleFixture;
        Task quitTask;
        int shutdownRequests;
        ExitWork fixtureExitWork;
        ExitResult lastExitResult;
        string notice = "", connectionError = "", currentView = "tasks", search = "";
        string connectionErrorDetail = "", connectionExitCode = "";
        StartupDiagnostic startupDiagnostic;
        bool preferenceSaveFailed, preferenceSaveAccessFailure;
        string statusFilter = "all";
        string activityFilter = "all";
        Brush background, surface, foreground, secondary, border, accent, accentText, accentInk, sideBackground, sideSelected, groupSurface;
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
        StackPanel eventRowsPanel;
        TextBox searchBox;
        ComboBox filterBox;
        ComboBox activityFilterBox;
        Window settingsWindow, trayPanelWindow;
        readonly Dictionary<string, string> rulesDraft = new Dictionary<string, string>();
        readonly Dictionary<string, TextBox> ruleInputs = new Dictionary<string, TextBox>();
        int rulesDraftRevision;
        bool rulesDraftInitialized, rulesDirty, rulesSaving, rulesUpdating;
        string rulesError = "";
        TextBlock rulesStatus, ruleQuotaSummary;
        Button rulesSave, rulesReload;

        sealed class Draft { public string Text; public int Revision; }

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint SetThreadExecutionState(uint flags);
        const uint ExecutionContinuous = 0x80000000;
        const uint ExecutionSystemRequired = 0x00000001;

        public MissionWindow(bool fixture, Dictionary<string, object> initial, string fixtureLanguage = "zh", string fixtureTheme = "system", string fixtureAccent = "green")
        {
            fixtureMode = fixture;
            preferences = new Preferences(!fixture);
            if (fixture)
            {
                if (fixtureLanguage != "zh" && fixtureLanguage != "en") throw new ArgumentException("Fixture language must be zh or en.");
                if (fixtureTheme != "system" && fixtureTheme != "light" && fixtureTheme != "dark") throw new ArgumentException("Fixture theme must be system, light or dark.");
                // Preview choices never load or save the real user's settings.
                preferences.Language = fixtureLanguage; preferences.Theme = fixtureTheme; preferences.Accent = ThemePalette.Normalize(fixtureAccent);
            }
            if (initial != null) snapshot = initial;
            var handler = new HttpClientHandler { CookieContainer = cookies, UseCookies = true, UseProxy = false };
            client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(20) };
            Width = 1380; Height = 900; MinWidth = 1080; MinHeight = 660;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            FontFamily = new FontFamily("Segoe UI, Microsoft YaHei UI"); FontSize = 13;
            Title = T("TOKEN榨汁机", "TokenMax");
            Closing += OnClosing;
            ApplyTheme(); BuildShell(); RenderSnapshot();
            if (!fixtureMode)
            {
                if (preferences.KeepAwake) SetAwake(true);
                BuildTray();
                timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(UiPollSeconds()) };
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
        public Brush AccentBrush { get { return accentInk; } }
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
            border = ColorBrush(dark ? "#3D3D3D" : "#DFDFDF"); var palette = ThemePalette.Colors(preferences.Accent, dark);
            accent = ColorBrush(palette[0]); accentText = ColorBrush(palette[1]); sideBackground = ColorBrush(palette[2]); sideSelected = ColorBrush(palette[3]);
            accentInk = ColorBrush(preferences.Accent == "yellow" && !dark ? "#82631A" : palette[0]); Background = background; Foreground = foreground;
        }
        static Brush ColorBrush(string value) { return new SolidColorBrush((Color)ColorConverter.ConvertFromString(value)); }
        public static Brush Tint(Brush source, double opacity)
        {
            var solid = source as SolidColorBrush; Color color = solid == null ? Colors.Gray : solid.Color;
            return new SolidColorBrush(Color.FromArgb((byte)Math.Round(255 * opacity), color.R, color.G, color.B));
        }
        void CheckSystemTheme()
        {
            if (quitting) return;
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
        public void StyleTextBox(TextBox box, bool legacyPaddingForFixture = false)
        {
            if (legacyPaddingForFixture && !fixtureMode) throw new InvalidOperationException("Legacy templates are available only to offline layout checks.");
            box.Background = ColorBrush(dark ? "#1E1E1E" : "#FFFFFF"); box.Foreground = foreground; box.BorderBrush = border;
            var template = new ControlTemplate(typeof(TextBox));
            var frame = new FrameworkElementFactory(typeof(Border), "InputFrame");
            frame.SetValue(Border.CornerRadiusProperty, new CornerRadius(6)); frame.SetValue(Border.BorderThicknessProperty, new Thickness(1));
            frame.SetBinding(Border.BackgroundProperty, ParentBinding("Background")); frame.SetBinding(Border.BorderBrushProperty, ParentBinding("BorderBrush"));
            var scroll = new FrameworkElementFactory(typeof(ScrollViewer), "PART_ContentHost");
            // TextBoxBase already forwards Padding to PART_ContentHost.Padding.
            // Binding the same value to Margin subtracts it a second time and
            // clips a 13-DIP line inside a 30-DIP single-line input.
            if (legacyPaddingForFixture) scroll.SetBinding(FrameworkElement.MarginProperty, ParentBinding("Padding"));
            frame.AppendChild(scroll); template.VisualTree = frame;
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
            foreach (var pair in navButtons) pair.Value.Background = pair.Key == currentView ? sideSelected : Brushes.Transparent;
            if (navCount != null) navCount.Text = CodexChats().Count.ToString(CultureInfo.InvariantCulture);
            if (breadcrumb != null) breadcrumb.Text = currentView == "events" ? T("操作记录", "Activity") : currentView == "rules" ? T("运行规则", "Rules") : T("来一杯", "Juice Bar");
        }
        void BuildShell()
        {
            Title = T("TOKEN榨汁机", "TokenMax"); navButtons.Clear();
            root = new Grid { Background = background }; root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(290) });
            root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) }); Content = root;
            var side = new Grid { Background = sideBackground }; side.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); side.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); root.Children.Add(side);
            sidebar = new StackPanel { Margin = new Thickness(22, 22, 22, 0) };
            var brand = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 38) };
            sidebarLogo = new JuicerLogo { Width = 52, Height = 52 }; sidebarLogo.SetPresentation(LogoState, true); brand.Children.Add(sidebarLogo);
            var brandText = new StackPanel { Margin = new Thickness(12, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
            brandText.Children.Add(SideText(T("TOKEN榨汁机", "TokenMax"), 17, true));
            var signature = SideText("T O K E N M A X", 9); signature.FontFamily = new FontFamily("Consolas"); signature.Margin = new Thickness(0, 5, 0, 0); brandText.Children.Add(signature); brand.Children.Add(brandText); sidebar.Children.Add(brand);
            var workspace = SideText(T("工作空间", "Workspace"), 10); workspace.Margin = new Thickness(0, 0, 0, 22); sidebar.Children.Add(workspace);
            sidebar.Children.Add(Navigation(T("来一杯", "Juice Bar"), "grid", "tasks"));
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
            var copy = new StackPanel(); var title = Text(connected ? T("检查状态待恢复", "Status check pending") : String.IsNullOrEmpty(connectionError) ? T("正在连接本机后台", "Connecting to the local service") : T("后台连接待恢复", "Backend connection unavailable"), 12, true); title.Margin = new Thickness(0, 0, 0, 4); copy.Children.Add(title);
            var description = Text(String.IsNullOrEmpty(connectionError) ? T("正在核对账号与额度…", "Checking account and quota…") : ConnectionErrorText(), 12); description.Margin = new Thickness(0); copy.Children.Add(description); row.Children.Add(copy); connectionBanner.Child = row;
        }
        void BuildContent()
        {
            if (pageHost == null) return; UpdateNavigation();
            // Cached rows may survive navigation. Detach them before replacing
            // the page so WPF never assigns a second logical parent. Drafts
            // remain in their row instances and in the owner draft cache.
            if (rowsPanel != null) rowsPanel.Children.Clear();
            rowsPanel = null; eventRowsPanel = null; activityFilterBox = null; globalButton = null; stateBlock = null;
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
            globalButton = MakeButton(T("开始榨汁", "Start Juicing"), delegate { ToggleGlobal(); }); globalButton.HorizontalAlignment = HorizontalAlignment.Right; controls.Children.Add(globalButton); DockPanel.SetDock(controls, Dock.Right); hero.Children.Add(controls);
            var heading = new StackPanel(); var title = Text(T("来一杯", "Juice Bar"), 28, true); title.Margin = new Thickness(0, 0, 0, 8); heading.Children.Add(title);
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
            var filters = new Grid { Margin = new Thickness(0, 18, 0, 0) }; filters.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(245) }); filters.ColumnDefinitions.Add(new ColumnDefinition());
            var filterLine = new DockPanel(); var filterLabel = Text(T("筛选", "Filter"), 13); filterLabel.Margin = new Thickness(0, 0, 8, 0); filterLabel.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(filterLabel, Dock.Left); filterLine.Children.Add(filterLabel);
            filterBox = Choice(new[] { T("全部状态", "All statuses"), T("等待恢复", "Waiting for recovery"), T("已预约", "Scheduled"), T("需留意", "Needs attention") });
            filterBox.SelectedIndex = statusFilter == "waiting" ? 1 : statusFilter == "scheduled" ? 2 : statusFilter == "attention" ? 3 : 0;
            filterBox.SelectionChanged += delegate { statusFilter = filterBox.SelectedIndex == 1 ? "waiting" : filterBox.SelectedIndex == 2 ? "scheduled" : filterBox.SelectedIndex == 3 ? "attention" : "all"; RenderChats(); }; filterLine.Children.Add(filterBox); filters.Children.Add(filterLine);
            var searchFrame = new Grid { Width = 280, HorizontalAlignment = HorizontalAlignment.Right }; Grid.SetColumn(searchFrame, 1);
            searchBox = MakeSearchInput(search); searchFrame.Children.Add(searchBox);
            var placeholder = Text(T("搜索聊天名称或 ID", "Search chats or IDs"), 12); placeholder.Foreground = secondary; placeholder.Margin = new Thickness(7, 0, 0, 0); placeholder.VerticalAlignment = VerticalAlignment.Center; placeholder.IsHitTestVisible = false; placeholder.Visibility = String.IsNullOrEmpty(search) ? Visibility.Visible : Visibility.Collapsed; searchFrame.Children.Add(placeholder);
            searchBox.TextChanged += delegate { search = searchBox.Text; placeholder.Visibility = String.IsNullOrEmpty(search) ? Visibility.Visible : Visibility.Collapsed; RenderChats(); }; filters.Children.Add(searchFrame); Grid.SetRow(filters, 2); pageRoot.Children.Add(filters);
            var columns = new Grid { Margin = new Thickness(18, 18, 18, 0) }; columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(24) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(360) });
            var first = Text(T("任务 / 当前执行阶段", "Task / Execution stage"), 10); first.Foreground = secondary; first.Margin = new Thickness(0); columns.Children.Add(first);
            var third = Text(T("额度恢复后执行 · 一次性", "Run once after quota recovery"), 10); third.Foreground = secondary; third.Margin = new Thickness(0); Grid.SetColumn(third, 2); columns.Children.Add(third); Grid.SetRow(columns, 3); pageRoot.Children.Add(columns);
            rowsPanel = new StackPanel { Margin = new Thickness(0, 0, 4, 0) }; var list = Scroller(rowsPanel, new Thickness(0, 18, 0, 0)); Grid.SetRow(list, 4); pageRoot.Children.Add(list);
            var footer = new DockPanel { Margin = new Thickness(0, 18, 0, 0) }; syncBlock = Text("", 10); syncBlock.Foreground = secondary; syncBlock.Margin = new Thickness(0); footer.Children.Add(syncBlock);
            Grid.SetRow(footer, 5); pageRoot.Children.Add(footer);
            RenderHeader(); RenderChats(); return pageRoot;
        }
        FrameworkElement Segments(string[] labels, string[] values, string selected, Action<string> changed)
        {
            var grid = new Grid(); for (int index = 0; index < labels.Length; index++)
            {
                grid.ColumnDefinitions.Add(new ColumnDefinition()); string value = values[index];
                var button = MakeButton(labels[index], delegate { changed(value); }); button.Padding = new Thickness(6, 3, 6, 3); button.FontSize = 12; button.Height = 22; button.MinHeight = 22;
                button.Background = value == selected ? ColorBrush(dark ? "#555555" : "#CCCCCC") : Brushes.Transparent;
                Grid.SetColumn(button, index); grid.Children.Add(button);
            }
            return new Border { Background = ColorBrush(dark ? "#333333" : "#EBEBEB"), CornerRadius = new CornerRadius(6), Padding = new Thickness(1), Child = grid };
        }
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
        List<Dictionary<string, object>> CodexChats()
        { return Json.Rows(snapshot, "tasks").Where(x => Json.Text(x, "category", "codex") == "codex" && Json.Text(x, "kind", "codex") == "codex" && Json.Text(x, "host_id", "local") == "local").ToList(); }
        int UiPollSeconds()
        { return Math.Max(2, Math.Min(30, Json.Integer(Json.Child(Json.Child(snapshot, "rules"), "values"), "ui_poll_seconds", 5))); }
        void ApplyUiPollInterval() { if (timer != null) timer.Interval = TimeSpan.FromSeconds(UiPollSeconds()); }
        string ResetCreditSummary(Dictionary<string, object> usage)
        {
            var credits = Json.Child(usage, "reset_credits"); if (!Json.Bool(credits, "supported")) return "";
            object raw = Json.Get(credits, "available_count");
            return raw == null ? T("额度重置权益：数量未提供", "Rate-limit resets: count not provided")
                : T("可用额度重置权益：", "Available rate-limit resets: ") + Json.Integer(credits, "available_count").ToString(CultureInfo.InvariantCulture);
        }
        string ResetCreditDetails(Dictionary<string, object> usage)
        {
            var lines = new List<string>(); foreach (var item in Json.Rows(Json.Child(usage, "reset_credits"), "credits").Take(20))
            {
                string name = Json.Text(item, "title", T("额度重置权益", "Rate-limit reset")); string status = Json.Text(item, "status");
                double expiry = Json.Number(item, "expires_at", Json.Number(item, "expiresAt"));
                lines.Add(name + (status.Length > 0 ? " · " + status : "") + (expiry > 0 ? " · " + T("有效期至 ", "Expires ") + FormatTime(expiry) : ""));
            }
            return String.Join("\n", lines);
        }
        string LogoState
        {
            get
            {
                var usage = Json.Child(snapshot, "usage");
                bool connected = fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError));
                return JuicerLogo.ResolveState(Json.Bool(snapshot, "control_paused", true), Json.Bool(snapshot, "running"),
                    connected, Healthy && String.IsNullOrEmpty(Json.Text(snapshot, "desktop_connection_error")), ControlAvailable, Json.Text(snapshot, "service_error", Json.Text(Json.Child(snapshot, "compatibility"), "status") == "update_required" ? "update_required" : ""),
                    Json.Bool(usage, "stale", true), Json.Text(usage, "quota_state", "unknown"),
                    Json.Bool(usage, "blocked"), Json.Text(snapshot, "quota_phase", VisibleWindows(usage).Any(window => Json.Number(window, "remaining", Double.PositiveInfinity) <= (Json.Number(window, "minutes") == 10080 ? 0 : Json.Number(Json.Child(snapshot, "policy"), "pause", 10))) ? "low" : "normal"), Json.Bool(snapshot, "control_enabled"));
            }
        }
        void RenderSnapshot()
        {
            if (quitting) return;
            ApplyUiPollInterval(); RenderQuota(); UpdateNavigation(); UpdateNotices();
            if (sidebarLogo != null) sidebarLogo.SetPresentation(LogoState, true);
            if (tray != null) tray.Text = T("TOKEN榨汁机", "TokenMax");
            if (lastSync != null) lastSync.Text = T("最近同步 ", "Last updated ") + FormatTime(Json.Number(snapshot, "observed_at"));
            if (currentView == "tasks") { RenderHeader(); RenderChats(); }
            else if (currentView == "events" && !busy) RenderEvents();
            else if (currentView == "rules") RefreshRulesPresentation();
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
            stateBlock.Text = enabled ? T("榨汁已开启", "Juicing on") : T("榨汁已停止", "Juicing stopped");
            globalButton.Content = !Json.Bool(snapshot, "running") ? T("启动后台服务", "Start background service") : Json.Bool(snapshot, "control_paused", true) ? T("开始榨汁", "Start Juicing") : T("暂停榨汁", "Pause Juicing");
            globalButton.IsEnabled = !busy && (fixtureMode || host == null || (baseUri != null && Json.Bool(snapshot, "running")
                && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy))));
            var chats = CodexChats();
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
            var all = CodexChats();
            var filtered = all.Where(x => (String.IsNullOrWhiteSpace(search) || (Json.Text(x, "name") + " " + Json.Text(x, "id")).IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0)
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
                var note = Text(T("Codex 任务目录随后台更新。", "The Codex task directory follows background updates."), 12); note.Foreground = secondary; note.TextAlignment = TextAlignment.Center; empty.Children.Add(note);
                wanted.Add(new Border { MinHeight = 220, Child = empty });
            }
            bool same = rowsPanel.Children.Count == wanted.Count;
            if (same) for (int index = 0; index < wanted.Count; index++) if (rowsPanel.Children[index] != wanted[index]) same = false;
            if (!same && !rowsPanel.IsKeyboardFocusWithin) { rowsPanel.Children.Clear(); foreach (var element in wanted) rowsPanel.Children.Add(element); }
            if (syncBlock != null) syncBlock.Text = preferences.Language == "en" ? filtered.Count + " of " + all.Count + " tasks · Updates every " + UiPollSeconds() + " seconds"
                : "显示 " + filtered.Count + " / " + all.Count + " 个任务 · 每 " + UiPollSeconds() + " 秒同步";
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
                    fill.Children.Add(new Border { Background = remaining <= Json.Number(Json.Child(snapshot, "policy"), "pause", 10) ? Brushes.Orange : ColorBrush("#B0B0B0"), CornerRadius = new CornerRadius(4) }); track.Children.Add(fill); group.Children.Add(track);
                }
                var reset = SideText(T("下次刷新 ", "Next reset ") + FormatTime(Json.Number(window, "reset")), 10); reset.Foreground = Tint(Brushes.White, 0.58); group.Children.Add(reset); quotaPanel.Children.Add(group);
            }
            string quotaState = Json.Text(usage, "quota_state"), note = "";
            if (Json.Bool(usage, "blocked")) note = T("服务暂不允许使用，等待重新核验", "The service currently blocks usage. Waiting for verification.");
            else if (quotaState == "service_only" && Json.Bool(usage, "service_allowed")) note = T("服务已允许使用，未提供固定额度窗口", "Usage is permitted; no fixed quota window was provided.");
            else if (VisibleWindows(usage).Count == 0) note = T("额度信息尚未核实", "Allowance has not been verified");
            if (note.Length > 0) { var message = SideText(note, 10); message.Margin = new Thickness(0, 16, 0, 0); quotaPanel.Children.Add(message); }
            string resetCredits = ResetCreditSummary(usage); if (resetCredits.Length > 0) { var earned = SideText(resetCredits, 10); earned.Margin = new Thickness(0, 14, 0, 0); earned.ToolTip = ResetCreditDetails(usage); quotaPanel.Children.Add(earned); }
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
            if (quitting) return;
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
            body.Children.Add(Text(T("来源：", "Source: ") + T("Codex · 本机", "Codex · Local"), 13));
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
                string message = Localized(immediate, "message"); if (message.Length > 0) receipt += "\n" + message;
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
            var filterLine = new DockPanel { Margin = new Thickness(0, 0, 0, 20), LastChildFill = true };
            var choice = Choice(new[] { T("全部记录", "All records"), T("用户操作", "User actions"), T("自动进程", "Automated processes") });
            choice.Width = 200; choice.Margin = new Thickness(18, 0, 0, 0); choice.VerticalAlignment = VerticalAlignment.Top;
            System.Windows.Automation.AutomationProperties.SetName(choice, T("记录来源", "Record source"));
            choice.SelectedIndex = activityFilter == "user" ? 1 : activityFilter == "automatic" ? 2 : 0;
            activityFilterBox = choice;
            choice.SelectionChanged += delegate {
                if (currentView != "events" || activityFilterBox != choice || choice.SelectedIndex < 0) return;
                string selected = choice.SelectedIndex == 1 ? "user" : choice.SelectedIndex == 2 ? "automatic" : "all";
                if (selected == activityFilter) return;
                activityFilter = selected; RenderEvents();
            };
            DockPanel.SetDock(choice, Dock.Right); filterLine.Children.Add(choice);
            var description = Text(T("最近 200 条记录", "Latest 200 records"), 13); description.Foreground = secondary; description.Margin = new Thickness(0); filterLine.Children.Add(description); content.Children.Add(filterLine);
            eventRowsPanel = new StackPanel(); content.Children.Add(eventRowsPanel); RenderEvents();
        }
        void RenderEvents()
        {
            if (eventRowsPanel == null || currentView != "events") return;
            // Keep the native selector and its keyboard/dropdown focus alive
            // while the five-second cache refresh updates only the record rows.
            eventRowsPanel.Children.Clear();
            var events = ActivityEventFilter.Apply(Json.Rows(snapshot, "events"), activityFilter);
            foreach (var item in events)
            {
                var row = new DockPanel { Margin = new Thickness(12, 10, 12, 10) };
                var icon = Glyph("clock", accent, 16); icon.Margin = new Thickness(0, 2, 18, 0); icon.VerticalAlignment = VerticalAlignment.Top; DockPanel.SetDock(icon, Dock.Left); row.Children.Add(icon);
                var stamp = Text(FormatTime(Json.Number(item, "created")), 10); stamp.Foreground = secondary; stamp.Margin = new Thickness(18, 1, 0, 0); DockPanel.SetDock(stamp, Dock.Right); row.Children.Add(stamp);
                bool restored = QuotaRestorationEvents.IsRestored(item); bool english = preferences.Language == "en";
                var labels = new StackPanel(); var heading = Text(restored ? QuotaRestorationEvents.Category(Json.Text(Json.Child(item, "detail"), "category"), english) : EventLabel(Json.Text(item, "state")), 13, true); heading.Margin = new Thickness(0, 0, 0, 5); labels.Children.Add(heading);
                if (restored)
                {
                    var summary = Text(QuotaRestorationEvents.Summary(item, english), 13); summary.Margin = new Thickness(0); labels.Children.Add(summary);
                    var details = new StackPanel();
                    foreach (string line in QuotaRestorationEvents.Lines(item, english)) { var evidence = Text(line, 12); evidence.Foreground = secondary; evidence.Margin = new Thickness(0, 5, 0, 0); details.Children.Add(evidence); }
                    string eventKey = Convert.ToString(Json.Get(item, "id"), CultureInfo.InvariantCulture);
                    if (String.IsNullOrEmpty(eventKey)) eventKey = Json.Stringify(item);
                    var disclosure = new Expander { Header = T("详情", "Details"), Content = details, IsExpanded = expandedEvents.Contains(eventKey), Foreground = secondary, Margin = new Thickness(0, 7, 0, 0), FontSize = 11 };
                    disclosure.Expanded += delegate { expandedEvents.Add(eventKey); };
                    disclosure.Collapsed += delegate { expandedEvents.Remove(eventKey); };
                    labels.Children.Add(disclosure);
                }
                else
                {
                var name = Text(QuotaRestorationEvents.ScopeTitle(item, english), 13); name.Margin = new Thickness(0); labels.Children.Add(name);
                var eventDetail = Json.Child(item, "detail"); string reason = Json.Text(eventDetail, "reason"); string recovery = RecoveryLabel(Json.Text(eventDetail, "recovery_reason"));
                if (recovery.Length > 0) { var evidence = Text(recovery, 12); evidence.Foreground = secondary; evidence.Margin = new Thickness(0, 5, 0, 0); labels.Children.Add(evidence); }
                if (reason.Length > 0 && reason != recovery) { var detail = Text(reason, 12); detail.Foreground = secondary; detail.Margin = new Thickness(0, 5, 0, 0); labels.Children.Add(detail); }
                }
                row.Children.Add(labels); eventRowsPanel.Children.Add(row); eventRowsPanel.Children.Add(DividerLine(Tint(secondary, 0.15), new Thickness(46, 0, 12, 0)));
            }
            if (events.Count == 0) { var empty = Text(T("此筛选条件下暂无记录", "No records match this filter"), 13); empty.Foreground = secondary; eventRowsPanel.Children.Add(empty); }
        }
        string RecoveryLabel(string value)
        {
            switch (value)
            {
                case "window_advanced": return T("已观察到新额度窗口", "New quota window observed");
                case "balance_restored": return T("可用余额恢复，重置原因未知", "Usable balance restored; reset cause unknown");
                case "quota_available": return T("额度已重新核验可用", "Quota availability verified");
                case "service_permission_restored": return T("服务许可恢复", "Service permission restored");
                default: return "";
            }
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
                {"immediate_failed",new[]{"立刻执行未发送","Immediate delivery failed"}}, {"rules_updated",new[]{"运行规则已更新","Operating rules updated"}} };
            string[] label; return labels.TryGetValue(value, out label) ? T(label[0],label[1]) : value;
        }
        TextBox MakeRuleInput(string value, double fontSize = 13, bool legacyPaddingForFixture = false)
        {
            var input = new TextBox { Text = value, FontFamily = FontFamily, FontSize = fontSize,
                Padding = new Thickness(8, 4, 8, 4), MaxLength = 4, VerticalContentAlignment = VerticalAlignment.Center };
            // Auto height lets WPF's actual font line metrics raise the natural
            // desired height. Leave two DIPs for glyph overhang/rounding in
            // addition to the template's one-DIP border on each side.
            if (legacyPaddingForFixture) input.Height = 30;
            else input.MinHeight = SingleLineMinimumHeight(input, 30);
            StyleTextBox(input, legacyPaddingForFixture); return input;
        }
        static double SingleLineMinimumHeight(TextBox input, double floor)
        { return Math.Max(floor, Math.Ceiling(input.FontSize * input.FontFamily.LineSpacing) + input.Padding.Top + input.Padding.Bottom + 2 + 2); }
        TextBox MakeSearchInput(string value, double fontSize = 12, bool legacyPaddingForFixture = false)
        {
            var input = new TextBox { Text = value, FontFamily = FontFamily, FontSize = fontSize,
                Padding = new Thickness(7, 2, 7, 2), VerticalContentAlignment = VerticalAlignment.Center };
            if (legacyPaddingForFixture) input.Height = 22;
            else input.MinHeight = SingleLineMinimumHeight(input, 22);
            StyleTextBox(input, legacyPaddingForFixture); return input;
        }
        string[] RuleLabels()
        { return new[] { T("暂停阈值", "Pause threshold"), T("恢复阈值", "Resume threshold"), T("正常采集间隔", "Normal collection interval"), T("临近阈值采集间隔", "Near-limit collection interval"), T("恢复复核时长", "Recovery confirmation"), T("界面刷新间隔", "Interface refresh interval") }; }
        void LoadRulesDraft()
        {
            var rules = Json.Child(snapshot, "rules"); var values = Json.Child(rules, "values"); rulesDraft.Clear();
            for (int i = 0; i < RulesPolicy.Fields.Length; i++) rulesDraft[RulesPolicy.Fields[i]] = Json.Integer(values, RulesPolicy.Fields[i], RulesPolicy.Defaults[i]).ToString(CultureInfo.InvariantCulture);
            rulesDraftRevision = Json.Integer(rules, "revision"); rulesDraftInitialized = true; rulesDirty = false; rulesError = "";
        }
        void BuildRules()
        {
            content.Margin = new Thickness(30); content.MaxWidth = 880; content.HorizontalAlignment = HorizontalAlignment.Left;
            var title = Text(T("运行规则", "Rules"), 26, true); title.Margin = new Thickness(0, 0, 0, 10); content.Children.Add(title);
            var introduction = Text(T("设置暂停、恢复条件和刷新频率。", "Set pause, recovery and refresh intervals."), 13); introduction.Foreground = secondary; introduction.Margin = new Thickness(0, 0, 0, 24); content.Children.Add(introduction);
            if (!rulesDraftInitialized || (!rulesDirty && !rulesSaving)) LoadRulesDraft(); ruleInputs.Clear();
            var editor = new StackPanel(); var heading = Text(T("控制参数", "Control parameters"), 15, true); heading.Margin = new Thickness(0, 0, 0, 18); editor.Children.Add(heading);
            string[] labels = RuleLabels(); var bounds = Json.Child(Json.Child(snapshot, "rules"), "bounds");
            for (int i = 0; i < RulesPolicy.Fields.Length; i++)
            {
                string field = RulesPolicy.Fields[i]; var fieldBounds = Json.Child(bounds, field); int lower = Json.Integer(fieldBounds, "min", RulesPolicy.Minimums[i]), upper = Json.Integer(fieldBounds, "max", RulesPolicy.Maximums[i]);
                var row = new Grid { Margin = new Thickness(0, 0, 0, 14) }; row.ColumnDefinitions.Add(new ColumnDefinition()); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(100) }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(148) });
                var label = Text(labels[i], 13); label.Margin = new Thickness(0, 0, 12, 0); label.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(label);
                var input = MakeRuleInput(rulesDraft[field]); Grid.SetColumn(input, 1); row.Children.Add(input); ruleInputs[field] = input;
                input.TextChanged += delegate { if (!rulesUpdating) { rulesDraft[field] = input.Text; rulesDirty = true; rulesError = ""; RefreshRulesPresentation(); } };
                var range = Text((i < 2 ? "%  ·  " : T("秒  ·  ", "sec  ·  ")) + lower + "–" + upper, 11); range.Foreground = secondary; range.Margin = new Thickness(12, 0, 0, 0); range.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(range, 2); row.Children.Add(range); editor.Children.Add(row);
            }
            var constraints = Text(T("恢复阈值至少高出 5 个百分点；临近阈值采集须更快或相同。", "Resume must be at least 5 points above pause; near-limit checks must be at least as frequent."), 11); constraints.Foreground = secondary; constraints.Margin = new Thickness(0, 0, 0, 16); editor.Children.Add(constraints);
            var actions = new WrapPanel(); rulesSave = MakeButton(T("保存规则", "Save rules"), async delegate { await SaveRulesAsync(); }, true); rulesSave.Margin = new Thickness(0, 0, 10, 0); actions.Children.Add(rulesSave);
            rulesReload = MakeButton(T("重新载入已保存值", "Reload saved values"), delegate { LoadRulesDraft(); RefreshRulesPresentation(); }); rulesReload.ToolTip = T("放弃当前未保存的修改，读取后台最新规则。", "Discard unsaved changes and load the latest saved rules."); actions.Children.Add(rulesReload); editor.Children.Add(actions);
            rulesStatus = Text("", 11); rulesStatus.Margin = new Thickness(0, 12, 0, 0); editor.Children.Add(rulesStatus); content.Children.Add(Card(editor, new Thickness(0, 0, 0, 22)));
            var liveQuota = new StackPanel(); var liveHeading = Text(T("服务额度 · 只读", "Service quota · Read-only"), 13, true); liveQuota.Children.Add(liveHeading); ruleQuotaSummary = Text("", 12); ruleQuotaSummary.Foreground = secondary; ruleQuotaSummary.Margin = new Thickness(0); liveQuota.Children.Add(ruleQuotaSummary); content.Children.Add(Card(liveQuota, new Thickness(0, 0, 0, 22)));
            Rule(T("自动暂停与续接", "Automatic pause and recovery"), T("额度不足时暂停；恢复并复核后续接。恢复原因以操作记录中的证据为准。", "Pause on low quota; resume after verified recovery. Recovery evidence appears in Activity."));
            Rule(T("额度恢复后执行一次", "Run once after quota recovery"), T("额度恢复后发送一次。预约独立于聊天开关；暂停榨汁也会暂停预约。", "Send once after quota recovers. Scheduling is separate from chat switches; Pause Juicing also pauses schedules."));
            Rule(T("订阅与额度", "Subscription and quota"), T("额度未知时等待核验；无固定窗口时须获得服务许可。重置权益仅供查看。", "Unknown quota awaits verification. No fixed window requires service permission. Reset credits are read-only."));
            Rule(T("立刻执行", "Run now"), T("立即发送当前指令，须通过状态与额度核验。结果不明确时不重复发送。", "Send now after status and quota checks. Unconfirmed deliveries are not retried."));
            Rule(T("手动操作优先", "Manual actions take priority"), T("用户指令和审批优先。任务完成后等待新指令。", "User instructions and approvals take priority. Completed chats await new instructions."));
            Rule(T("后台运行", "Background operation"), T("关窗后继续运行；退出仅停止TOKEN榨汁机，不中断客户端聊天。", "Closing the window keeps running. Quitting stops TokenMax, not client chats."));
            var settings = MakeButton(T("后台运行与系统权限…", "Background operation and permissions…"), ShowSettingsWindow); settings.HorizontalAlignment = HorizontalAlignment.Left; content.Children.Add(settings); RefreshRulesPresentation();
        }
        void RefreshRulesPresentation()
        {
            if (quitting || rulesStatus == null || currentView != "rules") return;
            var rules = Json.Child(snapshot, "rules"); bool available = rules.Count > 0 && !quitting && (fixtureMode || baseUri != null);
            // Polling never assigns to a focused or dirty editor. Rebuilds use the
            // separate draft dictionary, so theme/language changes retain edits.
            if (!rulesDirty && !rulesSaving && !ruleInputs.Values.Any(x => x.IsKeyboardFocusWithin))
            {
                LoadRulesDraft(); rulesUpdating = true;
                try { foreach (var pair in ruleInputs) if (pair.Value.Text != rulesDraft[pair.Key]) pair.Value.Text = rulesDraft[pair.Key]; }
                finally { rulesUpdating = false; }
            }
            bool conflict = rulesDirty && Json.Integer(rules, "revision") != rulesDraftRevision;
            rulesStatus.Text = rulesError.Length > 0 ? rulesError : rulesSaving ? T("正在保存规则…", "Saving rules…")
                : !available ? T("连接后可保存；草稿已保留。", "Connect to save. Draft retained.")
                : conflict ? T("规则已更新；请重新载入。草稿已保留。", "Rules changed; reload to continue. Draft retained.")
                : rulesDirty ? T("有未保存的修改。", "There are unsaved changes.") : T("规则已保存；不会自动开始榨汁。", "Rules saved. Juicing does not start automatically.");
            rulesStatus.Foreground = rulesError.Length > 0 || conflict ? Brushes.DarkOrange : secondary;
            rulesSave.IsEnabled = available && !fixtureMode && !rulesSaving && rulesDirty && !conflict; rulesReload.IsEnabled = !rulesSaving; foreach (var input in ruleInputs.Values) input.IsEnabled = !rulesSaving;
            var usage = Json.Child(snapshot, "usage"); var lines = new List<string>();
            foreach (var window in VisibleWindows(usage))
            {
                double remaining = Json.Number(window, "remaining", Double.NaN); string balance = Double.IsNaN(remaining) ? T("未提供", "Not provided") : Math.Round(remaining).ToString(CultureInfo.InvariantCulture) + "%";
                lines.Add(WindowTitle(Json.Number(window, "minutes")) + T("：剩余 ", ": Remaining ") + balance + T(" · 刷新 ", " · Resets ") + FormatTime(Json.Number(window, "reset")));
            }
            if (lines.Count == 0) lines.Add(T("服务尚未提供可显示的额度窗口。", "The service has not provided a visible quota window."));
            string credits = ResetCreditSummary(usage); if (credits.Length > 0) lines.Add(credits); ruleQuotaSummary.Text = String.Join("\n", lines); ruleQuotaSummary.ToolTip = ResetCreditDetails(usage);
        }
        async Task SaveRulesAsync()
        {
            if (fixtureMode || quitting || rulesSaving || baseUri == null || !rulesDirty) return;
            Dictionary<string, object> values; string error; string[] labels = RuleLabels();
            if (!RulesPolicy.Parse(rulesDraft, out values, out error))
            {
                int fieldIndex = Array.IndexOf(RulesPolicy.Fields, error);
                rulesError = error == "resume_margin" ? T("恢复阈值至少高于暂停阈值 5 个百分点。", "The resume threshold must be at least 5 percentage points above the pause threshold.")
                    : error == "near_interval" ? T("临近阈值采集间隔不得长于正常采集间隔。", "Near-limit collection cannot be slower than normal collection.")
                    : fieldIndex >= 0 ? labels[fieldIndex] + T("必须是范围内的整数。", " must be a whole number within the allowed range.") : T("请检查规则参数。", "Check the rule values."); RefreshRulesPresentation(); return;
            }
            int submittedRevision = rulesDraftRevision; Uri requestedBase = baseUri; rulesSaving = true; rulesError = ""; RefreshRulesPresentation();
            try
            {
                using (var request = new HttpRequestMessage(HttpMethod.Post, new Uri(requestedBase, "/api/action")))
                {
                    request.Headers.Add("X-Guardian-UI", "1"); request.Headers.Add("Origin", requestedBase.GetLeftPart(UriPartial.Authority));
                    request.Content = new StringContent(Json.Stringify(Json.Values("action", "set_rules", "rules_revision", submittedRevision, "rules", values)), Encoding.UTF8, "application/json");
                    using (var response = await client.SendAsync(request))
                    {
                        var body = Json.Parse(await response.Content.ReadAsStringAsync());
                        if (!response.IsSuccessStatusCode)
                        {
                            rulesError = (int)response.StatusCode == 409 ? T("规则已更新；请重新载入。草稿已保留。", "Rules changed; reload to continue. Draft retained.")
                                : preferences.Language == "en" ? Json.Text(body, "message_en", T("规则未保存，草稿已保留。", "Rules could not be saved. Your draft is retained.")) : Json.Text(body, "message", T("规则未保存，草稿已保留。", "Rules could not be saved. Your draft is retained."));
                        }
                        else
                        {
                            var returnedRules = Json.Child(body, "rules"); var returnedValues = Json.Child(returnedRules, "values");
                            bool confirmed = returnedRules.Count > 0 && Json.Integer(returnedRules, "revision") > submittedRevision && RulesPolicy.Fields.All(field => Json.Integer(returnedValues, field, -1) == Json.Integer(values, field));
                            if (confirmed && Object.Equals(baseUri, requestedBase)) { snapshot["rules"] = returnedRules; LoadRulesDraft(); }
                            else rulesError = T("保存待确认；请重新载入。草稿已保留。", "Save unconfirmed; reload to verify. Draft retained.");
                        }
                    }
                }
            }
            catch (Exception) { rulesError = T("未能连接后台，规则草稿已保留。", "Could not reach the background service. Your rule draft is retained."); }
            rulesSaving = false; await RefreshAsync(); RefreshRulesPresentation();
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
            string label = state == "supported" ? T("已适配", "Compatible") : state == "update_required" ? T("需要更新TOKEN榨汁机", "TokenMax update required") : T("正在检查客户端兼容性", "Checking client compatibility");
            return version.Length > 0 ? version + " · " + label : label;
        }
        string[] AccentLabels() { return new[] { T("森林绿", "Forest"), T("蓝色", "Blue"), T("紫色", "Purple"), T("鹅蛋黄", "Egg yellow") }; }
        FrameworkElement AccentChoice()
        { return Segments(AccentLabels(), ThemePalette.Keys, preferences.Accent, delegate(string value) { preferences.Accent = value; SavePreferences(); RebuildPresentation(); }); }
        FrameworkElement BuildSettingsSurface()
        {
            var body = new StackPanel { Margin = new Thickness(28) };
            var title = Text(T("设置", "Settings"), 26, true); title.Margin = new Thickness(0, 0, 0, 8); body.Children.Add(title);
            var description = Text(preferenceSaveFailed ? PreferenceFailureText() : T("外观、后台运行与权限", "Appearance, background operation and permissions"), 13); description.Foreground = preferenceSaveFailed ? Brushes.DarkOrange : secondary; description.Margin = new Thickness(0, 0, 0, 24); body.Children.Add(description);
            var appearance = new StackPanel(); appearance.Children.Add(GroupHeading("palette", T("外观与语言", "Appearance and language")));
            appearance.Children.Add(SettingsChoiceRow(T("语言", "Language"), Segments(new[] { "简体中文", "English" }, new[] { "zh", "en" }, preferences.Language,
                delegate(string value) { preferences.Language = value; SavePreferences(); RebuildPresentation(); }), 180));
            appearance.Children.Add(SettingsChoiceRow(T("外观", "Appearance"), Segments(new[] { T("跟随系统", "System"), T("浅色", "Light"), T("深色", "Dark") }, new[] { "system", "light", "dark" }, preferences.Theme,
                delegate(string value) { preferences.Theme = value; SavePreferences(); RebuildPresentation(); }), 270));
            appearance.Children.Add(SettingsChoiceRow(T("主题色", "Accent color"), AccentChoice(), 315)); body.Children.Add(SettingsGroup(appearance));
            var connection = new StackPanel(); connection.Children.Add(GroupHeading("network", T("客户端连接", "Client connection")));
            var version = Text(CompatibilityLabel(), 13); version.Foreground = secondary; version.Margin = new Thickness(0, 0, 0, 12); connection.Children.Add(version);
            var statusLine = new DockPanel(); var checks = new StackPanel { Orientation = Orientation.Horizontal };
            var check = MakeButton(T("重新检查", "Check again"), async delegate { await RefreshAsync(); RefreshSettingsWindow(); }); checks.Children.Add(check);
            if (host == null && !fixtureMode) { var reconnect = MakeButton(T("重新连接", "Reconnect"), delegate { StartHost(); SetNotice(T("正在连接本机后台。", "Connecting to the local service.")); }); reconnect.Margin = new Thickness(8, 0, 0, 0); checks.Children.Add(reconnect); } DockPanel.SetDock(checks, Dock.Right); statusLine.Children.Add(checks);
            var hostStatus = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center }; bool connected = fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError));
            var dot = new System.Windows.Shapes.Ellipse { Width = 8, Height = 8, Fill = connected ? accent : Brushes.DarkOrange, Margin = new Thickness(0, 0, 7, 0), VerticalAlignment = VerticalAlignment.Center }; hostStatus.Children.Add(dot);
            var statusText = Text(connected ? T("后台已连接", "Backend connected") : T("后台未连接", "Backend disconnected"), 12); statusText.Foreground = connected ? accent : Brushes.DarkOrange; statusText.Margin = new Thickness(0); hostStatus.Children.Add(statusText); statusLine.Children.Add(hostStatus); connection.Children.Add(statusLine);
            var hint = Text(T("关窗后继续在托盘运行。", "Closing the window keeps running in the tray."), 10); hint.Foreground = secondary; hint.Margin = new Thickness(0, 12, 0, 0); connection.Children.Add(hint);
            if (!ControlAvailable) { var reason = Text(ControlConnectionNote(), 10); reason.Foreground = secondary; reason.Margin = new Thickness(0, 8, 0, 0); connection.Children.Add(reason); }
            body.Children.Add(SettingsGroup(connection));
            var permissions = new StackPanel();
            permissions.Children.Add(PermissionRow(T("登录时启动", "Start at sign-in"), "power", T("登录 Windows 后启动。", "Launch at Windows sign-in."), fixtureMode ? T("尚未登记", "Not registered") : IsStartupEnabled() ? T("系统已允许", "Enabled in Windows") : T("尚未登记", "Not registered"), !fixtureMode && IsStartupEnabled(), SetStartup, "ms-settings:startupapps"));
            permissions.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            permissions.Children.Add(PermissionRow(T("任务通知", "Task notifications"), "bell", T("仅通知暂停、续接和异常。", "Notify on pauses, resumptions and errors."), preferences.Notifications ? T("已启用 · 系统投递待核验", "Enabled · System delivery unverified") : T("通知已关闭", "Notifications off"), preferences.Notifications, delegate(bool value) { preferences.Notifications = value; SavePreferences(); }, "ms-settings:notifications"));
            permissions.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            permissions.Children.Add(PermissionRow(T("保持后台运行", "Keep running in the background"), "moon", T("防止空闲睡眠，允许熄屏；不保证合盖运行。", "Prevent idle sleep; allow display-off. Closed-lid operation is not guaranteed."), preferences.KeepAwake ? T("已保持系统清醒", "Keep-awake request active") : T("未启用防睡眠保护", "Keep-awake protection off"), preferences.KeepAwake, SetAwake, "ms-settings:powersleep")); body.Children.Add(SettingsGroup(permissions, new Thickness(8)));
            var lid = new StackPanel();
            lid.Children.Add(PermissionRow(T("合盖运行辅助服务", "Closed-lid helper service"), "laptop", T("无外接显示器时的合盖电源支持。", "Power support for closed-lid use without an external display."), T("Windows 版暂不支持", "Unavailable on Windows"), false, delegate(bool value) { }, "ms-settings:powersleep", false));
            lid.Children.Add(DividerLine(border, new Thickness(46, 0, 0, 0)));
            lid.Children.Add(PermissionRow(T("合盖运行", "Closed-lid operation"), "laptop", T("遵循 Windows 电源设置。", "Uses Windows power settings."), T("未启用", "Not enabled"), false, delegate(bool value) { }, "ms-settings:powersleep", false));
            var battery = new DockPanel { Margin = new Thickness(20, 0, 20, 14) }; var batteryToggle = new CheckBox { Content = "", Width = 50, IsChecked = false, IsEnabled = false }; StyleSwitch(batteryToggle, false); DockPanel.SetDock(batteryToggle, Dock.Right); battery.Children.Add(batteryToggle); var batteryText = Text(T("允许使用电池", "Allow battery operation"), 12); batteryText.Margin = new Thickness(0); batteryText.VerticalAlignment = VerticalAlignment.Center; battery.Children.Add(batteryText); lid.Children.Add(battery);
            var powerNote = Text(T("合盖和睡眠请在系统设置中管理。", "Manage lid and sleep behavior in Windows settings."), 10); powerNote.Foreground = secondary; powerNote.TextAlignment = TextAlignment.Center; powerNote.Margin = new Thickness(20, 0, 20, 12); lid.Children.Add(powerNote); body.Children.Add(SettingsGroup(lid, new Thickness(8)));
            var footer = new DockPanel(); var time = Text(T("最近检查：", "Last checked: ") + (fixtureMode ? FormatTime(Json.Number(snapshot, "now")) : DateTime.Now.ToString("HH:mm:ss")), 10); time.Foreground = secondary; DockPanel.SetDock(time, Dock.Right); footer.Children.Add(time);
            var power = Text(PowerLabel(), 10); power.Foreground = secondary; footer.Children.Add(power); body.Children.Add(footer);
            return new Border { Background = background, Child = Scroller(body) };
        }
        string PowerLabel()
        {
            if (fixtureMode) return T("外接电源 · 电量 100% · 系统策略（示例）", "AC power · Battery 100% · System policy (sample)");
            try { var power = Forms.SystemInformation.PowerStatus; return (power.PowerLineStatus == Forms.PowerLineStatus.Online ? T("外接电源", "AC power") : T("电池", "Battery")) + " · " + Math.Round(power.BatteryLifePercent * 100) + "%"; } catch { return T("电源状态暂未提供", "Power status unavailable"); }
        }
        string PreferenceFailureText()
        {
            string detail = preferenceSaveAccessFailure ? StartupDiagnostic.AccessHint(preferences.Language == "zh", preferences.DirectoryPath)
                : T("请检查应用数据目录是否可写。目录：", "Check that the app data folder is writable. Folder: ") + preferences.DirectoryPath;
            return T("设置未保存；当前更改仅在本次运行生效。", "Settings were not saved; changes apply to this session only.") + " " + detail;
        }
        void SavePreferences()
        {
            if (fixtureMode) return;
            Exception failure;
            if (preferences.TrySave(out failure))
            {
                bool recovered = preferenceSaveFailed; preferenceSaveFailed = false;
                if (recovered) { SetNotice(T("设置已保存。", "Settings saved.")); RefreshSettingsWindow(); }
                return;
            }
            preferenceSaveFailed = true; preferenceSaveAccessFailure = StartupDiagnostic.IsAccessFailure(failure);
            SetNotice(PreferenceFailureText()); RefreshSettingsWindow();
        }
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
            SavePreferences();
        }
        public string Localized(Dictionary<string, object> value, string field) { return preferences.Language == "en" ? Json.Text(value, field + "_en", Json.Text(value, field)) : Json.Text(value, field); }
        void SetNotice(string value) { notice = value; if (noticeBlock != null) noticeBlock.Text = notice; UpdateNotices(); BuildTrayMenu(); }
        public void ToggleGlobal()
        {
            if (fixtureMode) return;
            if (baseUri == null || !Json.Bool(snapshot, "running")) { StartHost(); SetNotice(T("正在连接本机后台。", "Connecting to the local service.")); return; }
            if (Json.Bool(snapshot, "control_paused", true) && !ControlAvailable) { SetNotice(T("连接待核验，暂不能开始榨汁。", "Verify the connection before starting.")); return; }
            var action = Json.Bool(snapshot, "control_paused", true) ? "enable" : "pause";
            var ignored = PerformAsync(Json.Values("action", action, "revision", Json.Integer(snapshot, "control_revision")));
        }
        void SetConnectionFailure(string kind, string detail)
        { connectionError = kind; connectionErrorDetail = StartupDiagnostic.Shorten(detail, 512); connectionExitCode = ""; }
        string ConnectionErrorText()
        {
            if (connectionError == "files_missing") return T("应用文件不完整，请重新安装。", "Application files are incomplete. Reinstall the app.");
            if (connectionError == "host_exited")
            {
                string detail = startupDiagnostic == null ? "" : startupDiagnostic.Describe(preferences.Language == "zh", preferences.DirectoryPath);
                return T("后台已退出（退出码 ", "The backend exited (code ") + connectionExitCode + T("）。", ").") + " "
                    + (detail.Length > 0 ? detail : T("请重新连接后台服务；如仍失败，请检查应用数据目录的访问权限。", "Reconnect to the background service. If the problem persists, check access to the app data folder."));
            }
            if (connectionError == "launch_failed") return T("无法启动后台服务。", "The background service could not start.") + " "
                + (startupDiagnostic == null ? connectionErrorDetail : startupDiagnostic.Describe(preferences.Language == "zh", preferences.DirectoryPath));
            if (connectionError == "request_failed") return T("后台连接待恢复：", "Backend connection unavailable: ") + connectionErrorDetail;
            return connectionError;
        }
        void PostWhileRunning(Action action)
        {
            if (quitting || Dispatcher.HasShutdownStarted || Dispatcher.HasShutdownFinished) return;
            try { Dispatcher.BeginInvoke(new Action(delegate { if (!quitting) action(); })); }
            catch (InvalidOperationException) { }
        }
        void RefreshStartupDiagnostic(StartupDiagnostic diagnostic)
        {
            PostWhileRunning(delegate { if (Object.ReferenceEquals(startupDiagnostic, diagnostic) && connectionError == "host_exited") { UpdateNotices(); BuildTrayMenu(); } });
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
            if (!File.Exists(python) || !File.Exists(script)) { SetConnectionFailure("files_missing", ""); RenderSnapshot(); return; }
            var diagnostic = new StartupDiagnostic(); startupDiagnostic = diagnostic;
            try
            {
                try { Directory.CreateDirectory(preferences.DirectoryPath); } catch (Exception ex) { diagnostic.RecordDataDirectoryFailure(ex); throw; }
                var start = new ProcessStartInfo(python, "-B -X utf8 -I \"" + script + "\" --directory \"" + preferences.DirectoryPath + "\"") {
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
                    // Retain stderr before attempting disk I/O. The folder may
                    // be exactly the reason the owned host could not start.
                    if (!String.IsNullOrEmpty(e.Data))
                    {
                        diagnostic.Append(e.Data);
                        try { File.AppendAllText(Path.Combine(preferences.DirectoryPath, "native-host.log"), DateTime.UtcNow.ToString("o") + " " + e.Data + Environment.NewLine, Encoding.UTF8); }
                        catch (Exception ex) { diagnostic.RecordLogFailure(ex); }
                    }
                    // stderr may drain after Process.Exited. Update only the
                    // same attempt so late errors cannot overwrite a retry.
                    RefreshStartupDiagnostic(diagnostic);
                };
                process.Exited += delegate { PostWhileRunning(delegate {
                    if (!Object.ReferenceEquals(host, process)) return;
                    host = null;
                    string code; try { code = process.ExitCode.ToString(CultureInfo.InvariantCulture); } catch { code = "—"; }
                    baseUri = null; SetConnectionFailure("host_exited", ""); connectionExitCode = code; RenderSnapshot();
                }); };
                process.Start(); host = process; process.BeginOutputReadLine(); process.BeginErrorReadLine();
            }
            catch (Exception ex) { diagnostic.Append(ex.GetType().Name + ": " + ex.Message); SetConnectionFailure("launch_failed", ex.GetType().Name + ": " + ex.Message); RenderSnapshot(); }
        }
        public void EnsureHostStarted() { StartHost(); }
        async Task RefreshAsync()
        {
            if (fixtureMode || quitting || refreshing || baseUri == null) return;
            refreshing = true; Uri requestedBase = baseUri; StartupDiagnostic requestedAttempt = startupDiagnostic;
            try
            {
                using (var handshake = await client.GetAsync(requestedBase)) handshake.EnsureSuccessStatusCode();
                using (var response = await client.GetAsync(new Uri(requestedBase, "/api/state")))
                {
                    response.EnsureSuccessStatusCode(); var observed = Json.Parse(await response.Content.ReadAsStringAsync());
                    if (!Object.Equals(baseUri, requestedBase) || !Object.ReferenceEquals(startupDiagnostic, requestedAttempt) || quitting) return;
                    // A GET started before a successful rule save can finish
                    // afterwards. Keep that older response from undoing the
                    // confirmed revision in the editor for this same host.
                    var previousRules = Json.Child(snapshot, "rules"); var observedRules = Json.Child(observed, "rules");
                    if (previousRules.Count > 0 && Json.Integer(observedRules, "revision", -1) < Json.Integer(previousRules, "revision")) observed["rules"] = previousRules;
                    snapshot = observed;
                }
                connectionError = ""; RenderSnapshot();
            }
            catch (Exception ex) { if (Object.Equals(baseUri, requestedBase) && Object.ReferenceEquals(startupDiagnostic, requestedAttempt) && !quitting) { SetConnectionFailure("request_failed", ex.Message); RenderSnapshot(); } }
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
            tray = new Forms.NotifyIcon { Icon = trayBrandIcon ?? System.Drawing.SystemIcons.Application, Text = "TokenMax", Visible = true };
            tray.DoubleClick += delegate { PostWhileRunning(ShowMain); };
            tray.MouseUp += delegate(object sender, Forms.MouseEventArgs e) {
                if (e.Button == Forms.MouseButtons.Left || e.Button == Forms.MouseButtons.Right) PostWhileRunning(ToggleTrayPanel);
            };
        }
        void ToggleTrayPanel()
        {
            if (quitting || (fixtureMode && !lifecycleFixture)) return;
            if (trayPanelWindow != null) { CloseTrayPanel(); return; }
            var panel = new TrayPopupWindow { Width = 400, Height = 570, WindowStyle = WindowStyle.None, ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false, Topmost = true, AllowsTransparency = true, Background = Brushes.Transparent, Foreground = foreground,
                FontFamily = FontFamily, FontSize = 13, Content = BuildTraySurface() };
            bool closing = false, deactivationQueued = false;
            trayPanelWindow = panel; var work = SystemParameters.WorkArea;
            panel.Left = Math.Max(work.Left, work.Right - panel.Width - 12); panel.Top = Math.Max(work.Top, work.Bottom - panel.Height - 12);
            panel.Deactivated += delegate {
                if (closing || deactivationQueued || !Object.ReferenceEquals(trayPanelWindow, panel) || AnyOpenChoice(panel)) return;
                deactivationQueued = true;
                // Closing a window inside its own native deactivation callback
                // can reenter WPF's close path. Close after the callback, and
                // never let a queued old popup close its replacement.
                Dispatcher.BeginInvoke(DispatcherPriority.Background, new Action(delegate {
                    deactivationQueued = false;
                    if (!closing && Object.ReferenceEquals(trayPanelWindow, panel) && !AnyOpenChoice(panel)) CloseTrayPanel();
                }));
            };
            panel.Closing += delegate { closing = true; if (Object.ReferenceEquals(trayPanelWindow, panel)) trayPanelWindow = null; };
            panel.Closed += delegate { if (Object.ReferenceEquals(trayPanelWindow, panel)) trayPanelWindow = null; };
            panel.Show(); panel.Activate();
        }
        void CloseTrayPanel()
        {
            var panel = trayPanelWindow; if (panel == null) return;
            // Clear before Close can synchronously raise Deactivated/Closing.
            trayPanelWindow = null; panel.Close();
        }
        void BuildTrayMenu()
        {
            if (trayPanelWindow == null || AnyOpenChoice(trayPanelWindow)) return;
            trayPanelWindow.Foreground = foreground; trayPanelWindow.Content = BuildTraySurface();
        }
        FrameworkElement TrayAction(string name, string iconName, Action action)
        {
            var line = new StackPanel { Orientation = Orientation.Horizontal }; var glyph = Glyph(iconName, foreground, 15); glyph.Margin = new Thickness(0, 0, 9, 0); line.Children.Add(glyph);
            var label = Text(name, 13); label.Margin = new Thickness(0); line.Children.Add(label);
            var button = MakePlainButton(line, action); button.Tag = iconName; button.HorizontalAlignment = HorizontalAlignment.Stretch; button.Margin = new Thickness(0, 0, 0, 16); return button;
        }
        FrameworkElement BuildTraySurface()
        {
            var body = new StackPanel { Margin = new Thickness(20) };
            var heading = new DockPanel(); var plan = Text(Subscription(Json.Child(Json.Child(snapshot, "usage"), "account")), 10); plan.Foreground = secondary; plan.Margin = new Thickness(0); plan.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(plan, Dock.Right); heading.Children.Add(plan);
            var brand = new StackPanel { Orientation = Orientation.Horizontal }; var brandLogo = new JuicerLogo { Width = 32, Height = 32, Margin = new Thickness(0, 0, 8, 0) }; brandLogo.SetPresentation(LogoState, dark); brand.Children.Add(brandLogo); var title = Text(T("TOKEN榨汁机", "TokenMax"), 13, true); title.Margin = new Thickness(0); brand.Children.Add(title); heading.Children.Add(brand); body.Children.Add(heading);
            var usage = Json.Child(snapshot, "usage"); var windows = VisibleWindows(usage);
            foreach (var window in windows)
            {
                var meter = new StackPanel { Margin = new Thickness(0, 16, 0, 0) }; var top = new DockPanel(); double remaining = Json.Number(window, "remaining", Double.NaN);
                var value = Text(Double.IsNaN(remaining) ? T("未提供", "Not provided") : remaining.ToString("0.0", CultureInfo.InvariantCulture) + "%", 12, true); value.Margin = new Thickness(0); DockPanel.SetDock(value, Dock.Right); top.Children.Add(value);
                var label = Text(WindowTitle(Json.Number(window, "minutes")), 12); label.Margin = new Thickness(0); top.Children.Add(label); meter.Children.Add(top);
                if (!Double.IsNaN(remaining))
                {
                    var track = new Grid { Height = 5, Margin = new Thickness(0, 6, 0, 6) }; track.Children.Add(new Border { Background = Tint(secondary, 0.2), CornerRadius = new CornerRadius(3) });
                    var fill = new Border { Background = remaining <= Json.Number(Json.Child(snapshot, "policy"), "pause", 10) ? Brushes.DarkOrange : accent, CornerRadius = new CornerRadius(3), HorizontalAlignment = HorizontalAlignment.Left };
                    track.Children.Add(fill); track.SizeChanged += delegate { fill.Width = track.ActualWidth * Math.Max(0, Math.Min(100, remaining)) / 100; }; meter.Children.Add(track);
                }
                var reset = Text(Json.Number(window, "reset") > 0 ? T("下次刷新 ", "Next reset ") + FormatTime(Json.Number(window, "reset")) : T("刷新时间未提供", "Reset time not provided"), 10); reset.Foreground = secondary; reset.Margin = new Thickness(0); meter.Children.Add(reset); body.Children.Add(meter);
            }
            string availability = "";
            if (Json.Bool(usage, "blocked")) availability = T("服务暂不允许使用，等待重新核验", "The service currently blocks usage. Waiting for verification.");
            else if (Json.Text(usage, "quota_state") == "service_only" && Json.Bool(usage, "service_allowed")) availability = T("服务已允许使用，未提供固定额度窗口", "Usage is permitted; no fixed quota window was provided.");
            else if (windows.Count == 0) availability = T("额度信息尚未核实", "Allowance has not been verified");
            if (availability.Length > 0) { var note = Text(availability, 10); note.Foreground = secondary; note.Margin = new Thickness(0, 14, 0, 0); body.Children.Add(note); }
            string resetCredits = ResetCreditSummary(usage); if (resetCredits.Length > 0) { var earned = Text(resetCredits, 11); earned.Foreground = secondary; earned.Margin = new Thickness(0, 14, 0, 0); earned.ToolTip = ResetCreditDetails(usage); body.Children.Add(earned); }
            if (UsageStale(usage)) { var stale = Text(T("◷  额度待同步", "◷  Quota awaiting update"), 10); stale.Foreground = Brushes.DarkOrange; stale.Margin = new Thickness(0, 14, 0, 0); body.Children.Add(stale); }
            var controls = new Grid { Margin = new Thickness(0, 16, 0, 0) }; controls.ColumnDefinitions.Add(new ColumnDefinition()); controls.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) }); controls.ColumnDefinitions.Add(new ColumnDefinition());
            string bulkState = Json.Text(Json.Child(snapshot, "bulk_pause"), "state"); bool bulkBusy = bulkState == "pending" || bulkState == "processing";
            var automatic = MakeButton(Json.Bool(snapshot, "control_paused", true) ? T("开始榨汁", "Start Juicing") : T("暂停榨汁", "Pause Juicing"), ToggleGlobal); automatic.FontSize = 11;
            automatic.IsEnabled = !busy && !bulkBusy && (fixtureMode || baseUri != null) && Json.Bool(snapshot, "running") && (!Json.Bool(snapshot, "control_paused", true) || (ControlAvailable && Healthy)); controls.Children.Add(automatic);
            var pause = MakeButton(T("暂停所有任务", "Pause all tasks"), async delegate { await PerformAsync(Json.Values("action", "pause_all", "revision", Json.Integer(snapshot, "control_revision"))); }); pause.FontSize = 11; pause.ToolTip = T("暂停受管任务和榨汁。需手动恢复任务。", "Pause managed tasks and juicing. Resume tasks manually."); pause.IsEnabled = !busy && !bulkBusy && Healthy && ControlAvailable && (fixtureMode || baseUri != null); Grid.SetColumn(pause, 2); controls.Children.Add(pause); body.Children.Add(controls);
            var bulk = Json.Child(snapshot, "bulk_pause"); if (bulk.Count > 0)
            {
                var result = new DockPanel { Margin = new Thickness(0, 12, 0, 0) }; var details = MakePlainButton(T("查看结果", "View results"), ShowBulkResults); details.FontSize = 10; DockPanel.SetDock(details, Dock.Right); result.Children.Add(details);
                var count = Text(T("暂停 ", "Paused ") + Json.Integer(bulk, "paused") + T(" · 跳过 ", " · Skipped ") + Json.Integer(bulk, "skipped") + T(" · 待处理 ", " · Needs attention ") + Json.Integer(bulk, "failed"), 10); count.Foreground = Json.Integer(bulk, "failed") > 0 ? Brushes.DarkOrange : secondary; count.Margin = new Thickness(0); result.Children.Add(count); body.Children.Add(result);
            }
            if (notice.Length > 0) { var message = Text(notice, 10); message.Foreground = secondary; message.Margin = new Thickness(0, 12, 0, 0); body.Children.Add(message); }
            if (connectionError.Length > 0) { var error = Text(ConnectionErrorText(), 10); error.Foreground = Brushes.DarkOrange; error.Margin = new Thickness(0, 12, 0, 0); body.Children.Add(error); }
            body.Children.Add(DividerLine(border, new Thickness(0, 16, 0, 16)));
            body.Children.Add(TrayAction(T("打开TOKEN榨汁机", "Open TokenMax"), "window", ShowMain));
            body.Children.Add(TrayAction(T("设置", "Settings"), "settings", delegate { CloseTrayPanel(); ShowSettingsWindow(); }));
            var language = Choice(new[] { "简体中文", "English" }); language.SelectedIndex = preferences.Language == "en" ? 1 : 0;
            language.SelectionChanged += delegate { preferences.Language = language.SelectedIndex == 1 ? "en" : "zh"; SavePreferences(); RebuildPresentation(); }; body.Children.Add(SettingsChoiceRow(T("语言", "Language"), language, 180));
            var theme = Choice(new[] { T("跟随系统", "System"), T("浅色", "Light"), T("深色", "Dark") }); theme.SelectedIndex = preferences.Theme == "light" ? 1 : preferences.Theme == "dark" ? 2 : 0;
            theme.SelectionChanged += delegate { preferences.Theme = theme.SelectedIndex == 1 ? "light" : theme.SelectedIndex == 2 ? "dark" : "system"; SavePreferences(); RebuildPresentation(); }; body.Children.Add(SettingsChoiceRow(T("外观", "Appearance"), theme, 180));
            var colors = Choice(AccentLabels()); colors.SelectedIndex = Array.IndexOf(ThemePalette.Keys, preferences.Accent); colors.SelectionChanged += delegate { if (colors.SelectedIndex >= 0) { preferences.Accent = ThemePalette.Keys[colors.SelectedIndex]; SavePreferences(); RebuildPresentation(); } }; body.Children.Add(SettingsChoiceRow(T("主题色", "Accent color"), colors, 180));
            body.Children.Add(DividerLine(border, new Thickness(0, 4, 0, 16)));
            var footer = new DockPanel(); var exit = MakePlainButton(T("退出", "Quit"), Quit); exit.Tag = "quit"; exit.FontSize = 10; DockPanel.SetDock(exit, Dock.Right); footer.Children.Add(exit);
            var connected = Text(fixtureMode || (baseUri != null && String.IsNullOrEmpty(connectionError)) ? T("●  后台已连接", "●  Backend connected") : T("●  后台未连接", "●  Backend disconnected"), 10); connected.Foreground = secondary; connected.Margin = new Thickness(0); footer.Children.Add(connected); body.Children.Add(footer);
            return new Border { Background = background, BorderBrush = border, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Child = Scroller(body), ClipToBounds = true };
        }
        void ShowBulkResults()
        {
            if (fixtureMode) return; CloseTrayPanel(); var body = new StackPanel { Margin = new Thickness(24) }; var heading = Text(T("暂停所有任务", "Pause all tasks"), 17, true); body.Children.Add(heading);
            var description = Text(T("暂停受管任务和榨汁。需手动恢复任务。", "Pause managed tasks and juicing. Resume tasks manually."), 12); description.Foreground = secondary; description.Margin = new Thickness(0, 8, 0, 18); body.Children.Add(description);
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
        static FrameworkElement FindLayoutElement(DependencyObject root, Func<FrameworkElement, bool> predicate)
        {
            var element = root as FrameworkElement; if (element != null && predicate(element)) return element;
            for (int index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
            { var found = FindLayoutElement(VisualTreeHelper.GetChild(root, index), predicate); if (found != null) return found; }
            return null;
        }
        static object RectangleReport(Rect value)
        { return value.IsEmpty ? null : Json.Values("x", value.X, "top", value.Top, "width", value.Width, "height", value.Height, "bottom", value.Bottom); }
        static object ThicknessReport(Thickness value)
        { return Json.Values("left", value.Left, "top", value.Top, "right", value.Right, "bottom", value.Bottom); }
        static bool FitsVertically(Rect text, Rect viewport)
        { return !text.IsEmpty && !viewport.IsEmpty && text.Height > 0 && text.Top >= viewport.Top - 0.5 && text.Bottom <= viewport.Bottom + 0.5; }
        static void RenderLayoutElement(FrameworkElement view)
        {
            view.UpdateLayout();
            var bitmap = new RenderTargetBitmap(Math.Max(1, (int)Math.Ceiling(view.ActualWidth)), Math.Max(1, (int)Math.Ceiling(view.ActualHeight)), 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(view);
        }
        static Dictionary<string, object> MeasureTextBoxLayout(TextBox input, int characterIndex = 0)
        {
            input.ApplyTemplate(); input.UpdateLayout(); RenderLayoutElement(input);
            var host = input.Template.FindName("PART_ContentHost", input) as ScrollViewer;
            if (host == null) throw new InvalidOperationException("Native TextBox content host is unavailable.");
            var presenter = FindLayoutElement(host, delegate(FrameworkElement element) { return element is ScrollContentPresenter; });
            var textView = FindLayoutElement(host, delegate(FrameworkElement element) { return element.GetType().Name == "TextBoxView"; });
            if (presenter == null || textView == null) throw new InvalidOperationException("Native TextBox visual parts are unavailable.");
            Rect viewport = presenter.TransformToAncestor(input).TransformBounds(new Rect(new Point(), presenter.RenderSize));
            Rect character = input.GetRectFromCharacterIndex(Math.Max(0, Math.Min(input.Text.Length - 1, characterIndex)), false);
            Rect ink = VisualTreeHelper.GetDescendantBounds(textView);
            if (!ink.IsEmpty) ink = textView.TransformToAncestor(input).TransformBounds(ink);
            bool characterVisible = FitsVertically(character, viewport), inkVisible = !ink.IsEmpty && FitsVertically(ink, viewport);
            return Json.Values("fontFamily", input.FontFamily.Source, "fontSize", input.FontSize, "controlHeight", input.ActualHeight,
                "hostMargin", ThicknessReport(host.Margin), "hostPadding", ThicknessReport(host.Padding),
                "hostViewportHeight", host.ViewportHeight, "contentViewport", RectangleReport(viewport),
                "textViewHeight", textView.ActualHeight, "characterLineHeight", character.IsEmpty ? 0 : character.Height,
                "characterRect", RectangleReport(character), "glyphInkBounds", RectangleReport(ink),
                "characterFullyVisible", characterVisible, "glyphInkFullyVisible", inkVisible,
                "textFullyVisible", characterVisible && inkVisible,
                "singlePadding", host.Margin == new Thickness(0) && host.Padding == input.Padding);
        }
        static void ArrangeLayoutFixture(System.Windows.Interop.HwndSource source, FrameworkElement view)
        {
            source.RootVisual = view; view.Measure(new Size(1500, 1000));
            view.Arrange(new Rect(0, 0, 1500, 1000)); view.UpdateLayout();
        }
        public Dictionary<string, object> RunTextBoxLayoutSelfTest(string comparisonImage)
        {
            if (!fixtureMode) throw new InvalidOperationException("TextBox layout checks require isolated fixture mode.");
            double[] factors = { 1, 1.25, 1.5, 2 }; var measurements = new List<object>();
            bool fixedVisible = true, searchVisible = true, singlePadding = true, multilineScrolling = true, baselineReproduced = false;
            var parameters = new System.Windows.Interop.HwndSourceParameters("TokenMax offline TextBox layout") {
                WindowStyle = unchecked((int)0x80000000), PositionX = -20000, PositionY = -20000, Width = 1500, Height = 1000 };
            double actualDpiX = 0, actualDpiY = 0;
            using (var source = new System.Windows.Interop.HwndSource(parameters))
            {
                actualDpiX = source.CompositionTarget.TransformToDevice.M11; actualDpiY = source.CompositionTarget.TransformToDevice.M22;
                foreach (string language in new[] { "zh", "en" }) foreach (string theme in new[] { "light", "dark" })
                {
                    preferences.Language = language; preferences.Theme = theme; ApplyTheme();
                    foreach (double layoutScale in factors) foreach (double textSize in factors)
                    foreach (string inputKind in new[] { "rules", "search" })
                    foreach (string text in new[] { "10", language == "zh" ? "中文90" : "Ag09" })
                    {
                        var old = inputKind == "rules" ? MakeRuleInput(text, 13 * textSize, true) : MakeSearchInput(text, 12 * textSize, true);
                        var repaired = inputKind == "rules" ? MakeRuleInput(text, 13 * textSize) : MakeSearchInput(text, 12 * textSize);
                        double inputWidth = inputKind == "rules" ? 100 : 280;
                        var row = new Grid { HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top,
                            Margin = new Thickness(20), LayoutTransform = new ScaleTransform(layoutScale, layoutScale) };
                        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(inputWidth) }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(30) }); row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(inputWidth) });
                        old.VerticalAlignment = VerticalAlignment.Top; repaired.VerticalAlignment = VerticalAlignment.Top;
                        row.Children.Add(old); Grid.SetColumn(repaired, 2); row.Children.Add(repaired);
                        var canvas = new Grid { Background = background }; canvas.Children.Add(row); ArrangeLayoutFixture(source, canvas);
                        var before = MeasureTextBoxLayout(old); var after = MeasureTextBoxLayout(repaired);
                        bool visible = Json.Bool(after, "textFullyVisible"); fixedVisible = fixedVisible && visible; singlePadding = singlePadding && Json.Bool(after, "singlePadding");
                        if (inputKind == "search") searchVisible = searchVisible && visible;
                        if (inputKind == "rules" && layoutScale == 1 && textSize == 1 && text == "10" && !Json.Bool(before, "textFullyVisible") && visible
                                && Math.Abs(Json.Number(before, "controlHeight") - Json.Number(after, "controlHeight")) < 0.1
                                && Math.Abs(Json.Number(before, "characterLineHeight") - Json.Number(after, "characterLineHeight")) < 0.1) baselineReproduced = true;
                        measurements.Add(Json.Values("inputKind", inputKind, "language", language, "theme", theme, "layoutScale", layoutScale, "textSizeStress", textSize, "sample", text, "original", before, "fixed", after));
                    }
                    var multiline = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Width = 320, Height = 104,
                        FontFamily = FontFamily, FontSize = 13, Padding = new Thickness(9), VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                        Text = String.Join("\n", Enumerable.Repeat(language == "zh" ? "中文指令 Ag09 10" : "Command Ag09 10", 12)) };
                    StyleTextBox(multiline); var multiCanvas = new Grid { HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top };
                    multiCanvas.Children.Add(multiline); ArrangeLayoutFixture(source, multiCanvas);
                    multiline.ScrollToEnd(); multiline.UpdateLayout(); RenderLayoutElement(multiline); multiline.ScrollToEnd(); multiline.UpdateLayout();
                    var lastLine = MeasureTextBoxLayout(multiline, multiline.Text.Length - 1);
                    multilineScrolling = multilineScrolling && multiline.AcceptsReturn && multiline.VerticalScrollBarVisibility == ScrollBarVisibility.Auto
                        && multiline.ExtentHeight > multiline.ViewportHeight && Json.Bool(lastLine, "characterFullyVisible");
                }
                if (!String.IsNullOrEmpty(comparisonImage))
                {
                    preferences.Language = "en"; preferences.Theme = "light"; preferences.Accent = "blue"; ApplyTheme();
                    var comparison = new StackPanel { Width = 620, Margin = new Thickness(24) };
                    comparison.Children.Add(Text("Native WPF text layout: original / fixed", 20, true));
                    comparison.Children.Add(Text("Same .NET process, font and 30-DIP base control size. Actual controls, not edited screenshots.", 12));
                    foreach (string sample in new[] { "10", "300", "中文90" })
                    {
                        var line = new Grid { Margin = new Thickness(0, 12, 0, 8) };
                        line.ColumnDefinitions.Add(new ColumnDefinition()); line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(30) }); line.ColumnDefinitions.Add(new ColumnDefinition());
                        var before = new StackPanel(); before.Children.Add(Text("Original: " + sample, 13)); before.Children.Add(MakeRuleInput(sample, 13, true));
                        var after = new StackPanel(); after.Children.Add(Text("Fixed: " + sample, 13)); after.Children.Add(MakeRuleInput(sample));
                        line.Children.Add(before); Grid.SetColumn(after, 2); line.Children.Add(after); comparison.Children.Add(line);
                    }
                    var frame = new Border { Background = background, Child = comparison, Width = 680, Height = 420 };
                    ArrangeLayoutFixture(source, frame); frame.Measure(new Size(680, 420)); frame.Arrange(new Rect(0, 0, 680, 420)); frame.UpdateLayout();
                    var bitmap = new RenderTargetBitmap(1360, 840, 192, 192, PixelFormats.Pbgra32); bitmap.Render(frame);
                    var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
                    string path = Path.GetFullPath(comparisonImage); Directory.CreateDirectory(Path.GetDirectoryName(path)); using (var file = File.Create(path)) encoder.Save(file);
                }
                source.RootVisual = null;
            }
            bool passed = baselineReproduced && fixedVisible && searchVisible && singlePadding && multilineScrolling;
            return Json.Values("native", true, "ui", "WPF", "checksPassed", passed, "baselineRegressionReproduced", baselineReproduced,
                "fixedAllTextFullyVisible", fixedVisible, "singlePaddingApplied", singlePadding, "multilineScrollingPreserved", multilineScrolling,
                "searchTextFullyVisible", searchVisible,
                "hostStarted", false, "messagesSent", 0, "privatePreferencesLoaded", false, "layoutScaleFactors", factors, "textSizeStressFactors", factors,
                "languages", new[] { "zh", "en" }, "themes", new[] { "light", "dark" }, "caseCount", measurements.Count,
                "presentationDpiScale", new[] { actualDpiX, actualDpiY }, "dpiSweepVerified", false, "systemDpiSettingsChanged", false, "systemTextSizeSettingsChanged", false,
                "scaleCoverage", "WPF layout transforms and explicit font-size stress; no change to actual Windows monitor DPI or Accessibility settings.",
                "frameworkRelease", Registry.GetValue(@"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full", "Release", null),
                "wpfFileVersion", FileVersionInfo.GetVersionInfo(typeof(TextBox).Assembly.Location).FileVersion,
                "comparisonImage", String.IsNullOrEmpty(comparisonImage) ? null : Path.GetFileName(comparisonImage), "measurements", measurements);
        }
        public Dictionary<string, object> RunRulesEditorSelfTest()
        {
            if (!fixtureMode) throw new InvalidOperationException("Editor checks require isolated fixture mode.");
            currentView = "rules"; BuildContent(); RenderSnapshot(); int originalRevision = rulesDraftRevision;
            ruleInputs["resume_remaining"].Text = "27";
            bool editingCaptured = rulesDirty && rulesDraft["resume_remaining"] == "27";
            var nextValues = RulesPolicy.DefaultsObject(); nextValues["resume_remaining"] = 25;
            snapshot["rules"] = Json.Values("revision", originalRevision + 1, "values", nextValues);
            RenderSnapshot();
            bool pollingPreserved = ruleInputs["resume_remaining"].Text == "27" && rulesDraftRevision == originalRevision && !rulesSave.IsEnabled;
            preferences.Accent = "blue"; RebuildPresentation();
            bool appearancePreserved = ruleInputs["resume_remaining"].Text == "27" && rulesDraftRevision == originalRevision && rulesDirty;
            LoadRulesDraft(); RefreshRulesPresentation();
            bool reloadApplied = ruleInputs["resume_remaining"].Text == "25" && rulesDraftRevision == originalRevision + 1 && !rulesDirty;
            bool passed = editingCaptured && pollingPreserved && appearancePreserved && reloadApplied;
            return Json.Values("native", true, "ui", "WPF", "hostStarted", false, "messagesSent", 0, "privatePreferencesLoaded", false,
                "draftCaptured", editingCaptured, "draftSurvivedPollingConflict", pollingPreserved, "draftSurvivedAppearanceChange", appearancePreserved, "explicitReloadApplied", reloadApplied, "checksPassed", passed);
        }
        static Button FindTaggedButton(DependencyObject parent, string tag)
        {
            var button = parent as Button; if (button != null && Object.Equals(button.Tag, tag)) return button;
            int count = VisualTreeHelper.GetChildrenCount(parent);
            for (int index = 0; index < count; index++) { var found = FindTaggedButton(VisualTreeHelper.GetChild(parent, index), tag); if (found != null) return found; }
            return null;
        }
        async Task LifecycleIdleAsync()
        {
            await Task.Delay(70);
            await Dispatcher.InvokeAsync(new Action(delegate { }), DispatcherPriority.ApplicationIdle);
        }
        static void LifecycleRequire(bool condition, string step)
        { if (!condition) throw new InvalidOperationException("Native lifecycle check failed: " + step); }
        public async Task<Dictionary<string, object>> RunLifecycleSelfTestAsync()
        {
            if (!fixtureMode) throw new InvalidOperationException("Lifecycle testing requires an offline fixture.");
            lifecycleFixture = true;
            var checks = Json.Values("native", true, "ui", "WPF", "webView", false, "privatePreferencesLoaded", false);
            ShowMain(); await LifecycleIdleAsync(); LifecycleRequire(IsVisible, "main window shown"); checks["mainWindowShown"] = true;
            Close(); await LifecycleIdleAsync(); LifecycleRequire(!IsVisible && !quitting, "close button hides main window"); checks["closeHidesWindow"] = true;
            ToggleTrayPanel(); await LifecycleIdleAsync(); var panel = trayPanelWindow as TrayPopupWindow;
            LifecycleRequire(panel != null && panel.IsVisible, "native tray popup opens"); checks["trayPopupShown"] = true;
            var open = FindTaggedButton(panel, "window"); LifecycleRequire(open != null, "real open-main button exists");
            open.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); await LifecycleIdleAsync();
            LifecycleRequire(IsVisible && trayPanelWindow == null, "tray button reopens main window"); checks["trayButtonReopensWindow"] = true;
            Close(); await LifecycleIdleAsync(); ToggleTrayPanel(); await LifecycleIdleAsync(); panel = trayPanelWindow as TrayPopupWindow;
            LifecycleRequire(panel != null, "second native popup exists");
            // Queue the actual production Deactivated handler, then invoke the
            // actual Open action before it drains and create a replacement.
            panel.RaiseDeactivatedForFixture(); open = FindTaggedButton(panel, "window");
            LifecycleRequire(open != null, "second real open-main button exists"); open.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
            ToggleTrayPanel(); var replacement = trayPanelWindow; await LifecycleIdleAsync();
            LifecycleRequire(replacement != null && replacement.IsVisible && Object.ReferenceEquals(trayPanelWindow, replacement), "old deactivation cannot close replacement popup");
            checks["deactivationReplacementSafe"] = true;
            CloseTrayPanel(); CloseTrayPanel(); ShowMain(); await LifecycleIdleAsync();
            LifecycleRequire(IsVisible && trayPanelWindow == null, "repeated close and reopen are safe"); checks["repeatedCloseSafe"] = true;
            LifecycleRequire(host == null && timer == null && tray == null, "no backend, poll timer or system tray created");
            int cooperativeStops = 0, cooperativeForces = 0, cooperativeDisposals = 0;
            var cooperative = await ExitCleanup.StopAsync(new ExitWork {
                RequestStop = delegate { cooperativeStops++; }, WaitForExit = delegate(int milliseconds) { return true; },
                ForceStop = delegate { cooperativeForces++; }, Dispose = delegate { cooperativeDisposals++; }
            }, 60, 40, 30);
            LifecycleRequire(cooperative.GracefulExit && cooperative.ExitConfirmed && cooperativeStops == 1 && cooperativeForces == 0 && cooperativeDisposals == 1, "cooperative host exits without force");
            checks["cooperativeExitAvoidsForce"] = true;
            var releaseCleanup = new ManualResetEventSlim(false);
            try
            {
                var cleanup = ExitCleanup.StopAsync(new ExitWork {
                    WaitForExit = delegate(int milliseconds) { return false; },
                    ForceStop = delegate { releaseCleanup.Wait(); }, Dispose = delegate { releaseCleanup.Wait(); }
                }, 60, 40, 30);
                LifecycleRequire(await Task.WhenAny(cleanup, Task.Delay(3000)) == cleanup, "blocked force and dispose remain bounded");
                var result = await cleanup; LifecycleRequire(result.ForceAttempted && !result.DisposeCompleted, "cleanup deadline covers force and dispose");
                checks["blockedForceAndDisposeAreBounded"] = true;
            }
            finally { releaseCleanup.Set(); }
            var releaseStop = new ManualResetEventSlim(false); int forced = 0, disposed = 0;
            fixtureExitWork = new ExitWork {
                RequestStop = delegate { releaseStop.Wait(); }, WaitForExit = delegate(int milliseconds) { return false; },
                ForceStop = delegate { Interlocked.Increment(ref forced); throw new IOException("fixture force failure"); },
                Dispose = delegate { Interlocked.Increment(ref disposed); throw new IOException("fixture dispose failure"); }
            };
            try
            {
                ToggleTrayPanel(); await LifecycleIdleAsync(); var quit = FindTaggedButton(trayPanelWindow, "quit");
                LifecycleRequire(quit != null, "explicit native tray Quit action exists");
                var elapsed = Stopwatch.StartNew(); quit.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                Task firstQuit = quitTask, repeatedQuit = BeginQuitAsync();
                LifecycleRequire(firstQuit != null && Object.ReferenceEquals(firstQuit, repeatedQuit), "repeated Quit shares one completion");
                checks["quitIsIdempotent"] = true;
                LifecycleRequire(await Task.WhenAny(firstQuit, Task.Delay(3000)) == firstQuit, "blocked stop cannot hold exit indefinitely"); await firstQuit;
                LifecycleRequire(elapsed.ElapsedMilliseconds < 3000 && lastExitResult != null && lastExitResult.ForceAttempted && forced == 1, "stop timeout escalates within budget");
                checks["blockedStopIsBounded"] = true;
                LifecycleRequire(disposed == 1 && lastExitResult.Errors >= 2 && shutdownRequests == 1, "cleanup exceptions cannot prevent final shutdown request");
                checks["cleanupErrorsDoNotBlockQuit"] = true;
                LifecycleRequire(host == null && tray == null && trayPanelWindow == null && !IsEnabled && !IsVisible, "Quit removes owned UI and connection resources");
                checks["quitReleasesOwnedResources"] = true;
                ShowMain(); ToggleTrayPanel(); LifecycleRequire(trayPanelWindow == null, "late tray actions cannot reopen during Quit");
                checks["lateTrayActionsIgnored"] = true; checks["productionHostExitBudgetMilliseconds"] = ExitCleanup.GraceMilliseconds + ExitCleanup.ForceMilliseconds + ExitCleanup.DisposeMilliseconds;
            }
            finally { releaseStop.Set(); }
            checks["hostStarted"] = false; checks["messagesSent"] = 0; checks["systemTrayCreated"] = false; checks["checksPassed"] = true; return checks;
        }
        public void EndLifecycleFixture()
        {
            if (!fixtureMode) throw new InvalidOperationException("Fixture cleanup cannot run in the installed application.");
            quitting = true; ExitAction(CloseTrayPanel); ExitAction(Close); ExitAction(client.Dispose);
        }
        void ReadNotifications()
        {
            if (quitting) return;
            try
            {
                string path = Path.Combine(preferences.DirectoryPath, "state", "native-notices.json");
                var rootNotices = Json.Serializer().DeserializeObject(File.ReadAllText(path)) as IEnumerable;
                if (rootNotices == null) return;
                foreach (object raw in rootNotices)
                {
                    var noticeValue = Json.Object(raw); string key = Json.Text(noticeValue, "key");
                    if (!notificationKeys.Add(key) || firstNotices || !preferences.Notifications || tray == null) continue;
                    tray.ShowBalloonTip(5000, NotificationCopy.Title(Json.Text(noticeValue, "title"), preferences.Language == "en"),
                        preferences.Language == "en" ? Json.Text(noticeValue, "body_en", "Open TokenMax for details.") : Json.Text(noticeValue, "body"), Forms.ToolTipIcon.Info);
                }
                firstNotices = false;
            }
            catch (Exception) { }
        }
        void ShowMain() { if (quitting) return; CloseTrayPanel(); Show(); if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal; Activate(); }
        void OnClosing(object sender, CancelEventArgs e)
        {
            if (quitting || (fixtureMode && !lifecycleFixture)) return; e.Cancel = true; Hide();
        }
        static void ExitAction(Action action)
        {
            try { action(); }
            catch (Exception error) { Debug.WriteLine("TokenMax exit cleanup: " + error.GetType().Name); }
        }
        void Quit() { BeginQuitAsync(); }
        Task BeginQuitAsync()
        {
            if (quitTask != null) return quitTask;
            // Publish the shared completion before cleanup can raise nested UI
            // events. Repeated Quit actions cannot start another shutdown.
            var completion = new TaskCompletionSource<bool>(); quitTask = completion.Task; quitting = true;
            var owned = host; host = null; baseUri = null;
            ExitAction(delegate { if (timer != null) timer.Stop(); });
            ExitAction(delegate { IsEnabled = false; });
            ExitAction(Hide);
            ExitAction(CloseTrayPanel);
            var settings = settingsWindow; settingsWindow = null; ExitAction(delegate { if (settings != null) settings.Close(); });
            if (!fixtureMode) ExitAction(delegate { SetThreadExecutionState(ExecutionContinuous); });
            var ownedTray = tray; tray = null;
            var ownedIcon = trayBrandIcon; trayBrandIcon = null;
            ExitWork work = fixtureMode ? fixtureExitWork : owned == null ? null : new ExitWork {
                RequestStop = delegate {
                    if (owned.HasExited) return;
                    owned.StandardInput.WriteLine("stop"); owned.StandardInput.Flush(); owned.StandardInput.Close();
                },
                WaitForExit = delegate(int milliseconds) { return owned.HasExited || owned.WaitForExit(milliseconds); },
                ForceStop = delegate { if (!owned.HasExited) owned.Kill(); },
                Dispose = owned.Dispose
            };
            CompleteQuitAsync(work, completion, ownedTray, ownedIcon); return quitTask;
        }
        async Task CompleteQuitAsync(ExitWork work, TaskCompletionSource<bool> completion,
                Forms.NotifyIcon ownedTray, System.Drawing.Icon ownedIcon)
        {
            try
            {
                // Cancel/dispose transport concurrently with host cleanup. A
                // wedged HTTP callback cannot extend the process deadline.
                Task transport = ExitCleanup.BoundedAsync(delegate {
                    ExitAction(client.CancelPendingRequests); ExitAction(client.Dispose);
                }, ExitCleanup.DisposeMilliseconds);
                Task trayCleanup = ExitCleanup.BoundedAsync(delegate {
                    // NotifyIcon is detached before this worker starts. Any
                    // queued native callback sees quitting and cannot reuse it.
                    ExitAction(delegate { if (ownedTray != null) ownedTray.Visible = false; });
                    ExitAction(delegate { if (ownedTray != null) ownedTray.Dispose(); });
                    ExitAction(delegate { if (ownedIcon != null) ownedIcon.Dispose(); });
                }, ExitCleanup.DisposeMilliseconds);
                Task<ExitResult> process = fixtureMode ? ExitCleanup.StopAsync(work, 60, 40, 30) : ExitCleanup.StopAsync(work);
                await Task.WhenAll(transport, trayCleanup, process); lastExitResult = process.Result;
            }
            catch (Exception error) { Debug.WriteLine("TokenMax bounded exit: " + error.GetType().Name); }
            finally
            {
                shutdownRequests++;
                // Fixture shutdown is recorded, never applied to the test
                // Application until its receipt has been written.
                if (!fixtureMode) ExitAction(delegate { if (Application.Current != null) Application.Current.Shutdown(); });
                completion.TrySetResult(true);
            }
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
            local["key"] = "unsupported:remote:offline-fixture"; local["kind"] = "unsupported"; local["host_id"] = "cloud"; local["plan"] = Json.Values("state", "armed");
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
            var columns = new Grid(); columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(24) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(360) }); Child = columns;
            var info = new StackPanel(); columns.Children.Add(info);
            var rowHeading = new Grid(); rowHeading.ColumnDefinitions.Add(new ColumnDefinition()); rowHeading.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var identityLine = new DockPanel { Margin = new Thickness(0, 0, 14, 0) }; typeIconHost = new ContentControl { Width = 18, Height = 15, Margin = new Thickness(0, 2, 8, 0), VerticalAlignment = VerticalAlignment.Top }; DockPanel.SetDock(typeIconHost, Dock.Left); identityLine.Children.Add(typeIconHost);
            var identity = new StackPanel(); title = Label("", 14, true); title.Margin = new Thickness(0); open = owner.MakePlainButton(title, delegate { owner.ShowChatDetails(chat); }); open.HorizontalContentAlignment = HorizontalAlignment.Left; identity.Children.Add(open);
            detail = Label("", 10); detail.FontFamily = new FontFamily("Consolas"); detail.Foreground = owner.SecondaryBrush; detail.Margin = new Thickness(0, 6, 0, 0); identity.Children.Add(detail); identityLine.Children.Add(identity); rowHeading.Children.Add(identityLine);
            var badgeLine = new StackPanel { Orientation = Orientation.Horizontal }; statusDot = new System.Windows.Shapes.Ellipse { Width = 6, Height = 6, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 7, 0) }; badgeLine.Children.Add(statusDot);
            status = Label("", 10, true); status.MaxWidth = 122; status.Margin = new Thickness(0); badgeLine.Children.Add(status);
            statusBadge = new Border { CornerRadius = new CornerRadius(7), Padding = new Thickness(9, 7, 9, 7), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top, Child = badgeLine }; Grid.SetColumn(statusBadge, 1); rowHeading.Children.Add(statusBadge); info.Children.Add(rowHeading);
            var stageBody = new StackPanel(); var stageHeading = Label(owner.T("当前执行阶段", "Execution stage"), 10, true); stageHeading.Foreground = owner.AccentBrush; stageHeading.Margin = new Thickness(0, 0, 0, 8); stageBody.Children.Add(stageHeading);
            stageStamp = Label("", 10); stageStamp.Foreground = owner.SecondaryBrush; stageStamp.Margin = new Thickness(0, 0, 0, 8); stageBody.Children.Add(stageStamp);
            stage = Label("", 12); stage.Foreground = owner.SecondaryBrush; stage.LineHeight = 17; stage.MaxHeight = 119; stage.TextTrimming = TextTrimming.CharacterEllipsis; stage.Margin = new Thickness(0); stageBody.Children.Add(stage);
            info.Children.Add(new Border { Background = owner.StageBrush, CornerRadius = new CornerRadius(8), Padding = new Thickness(14), Margin = new Thickness(0, 14, 0, 0), Child = stageBody });
            var right = new StackPanel(); Grid.SetColumn(right, 2); columns.Children.Add(right);
            var controlHeader = new Grid { Margin = new Thickness(0, 0, 0, 14) }; controlHeader.ColumnDefinitions.Add(new ColumnDefinition()); controlHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var bookingHeading = Label(owner.T("额度恢复后执行", "After quota recovery"), 11, true); bookingHeading.Foreground = owner.SecondaryBrush; bookingHeading.VerticalAlignment = VerticalAlignment.Center; bookingHeading.Margin = new Thickness(0, 0, 12, 0); controlHeader.Children.Add(bookingHeading);
            var autoBlock = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            autoHeading = Label(owner.T("榨汁状态", "Juicing"), 10); autoHeading.Foreground = owner.SecondaryBrush; autoHeading.VerticalAlignment = VerticalAlignment.Center; autoHeading.Margin = new Thickness(0, 0, 9, 0); autoBlock.Children.Add(autoHeading);
            auto = new CheckBox { Foreground = owner.ForegroundBrush, VerticalAlignment = VerticalAlignment.Center }; owner.StyleSwitch(auto);
            auto.Click += async delegate { if (!updating) await owner.PerformAsync(Json.Values("action", "set_auto", "key", Json.Text(chat, "key"), "enabled", auto.IsChecked == true, "revision", Json.Integer(chat, "revision"))); }; autoBlock.Children.Add(auto); Grid.SetColumn(autoBlock, 1); controlHeader.Children.Add(autoBlock); right.Children.Add(controlHeader);
            retry = owner.MakeButton(owner.T("重试连接", "Retry connection"), async delegate { await owner.PerformAsync(Json.Values("action", "set_auto", "key", Json.Text(chat, "key"), "enabled", true, "revision", Json.Integer(chat, "revision"))); }); retry.FontSize = 10; retry.Margin = new Thickness(0, 0, 0, 7); retry.HorizontalAlignment = HorizontalAlignment.Right; right.Children.Add(retry);
            autoError = Label("", 10); autoError.Foreground = Brushes.DarkOrange; autoError.MaxHeight = 46; autoError.Margin = new Thickness(0, 0, 0, 10); right.Children.Add(autoError);
            directoryPanel = new StackPanel(); var directoryHeading = new StackPanel { Orientation = Orientation.Horizontal };
            var eye = owner.Glyph("eye", owner.SecondaryBrush, 16); eye.Margin = new Thickness(0, 0, 8, 0); directoryHeading.Children.Add(eye); var label = Label(owner.T("目录暂不可操作", "Controls unavailable"), 12); label.Foreground = owner.SecondaryBrush; label.Margin = new Thickness(0); directoryHeading.Children.Add(label); directoryPanel.Children.Add(directoryHeading);
            directoryText = Label("", 10); directoryText.Foreground = owner.SecondaryBrush; directoryText.Margin = new Thickness(0, 10, 0, 0); directoryPanel.Children.Add(directoryText); right.Children.Add(directoryPanel);
            editorPanel = new StackPanel(); right.Children.Add(editorPanel);
            schedule = new CheckBox { Foreground = owner.ForegroundBrush, Margin = new Thickness(0, 0, 0, 10) }; owner.StyleSwitch(schedule);
            schedule.Click += async delegate { if (!updating) await SavePlan(schedule.IsChecked == true); }; editorPanel.Children.Add(schedule);
            planLabel = Label("", 10); planLabel.Foreground = owner.SecondaryBrush; planLabel.Margin = new Thickness(0, 0, 0, 10); editorPanel.Children.Add(planLabel);
            prompt = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 104, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Padding = new Thickness(9), FontSize = 13, MaxLength = 8000, Margin = new Thickness(0, 0, 0, 12) }; owner.StyleTextBox(prompt);
            prompt.TextChanged += delegate { if (!updating) { if (!dirty) draftRevision = Json.Integer(Json.Child(chat, "plan"), "revision"); dirty = true; owner.RememberDraft(Json.Text(chat, "key"), prompt.Text, draftRevision); } }; editorPanel.Children.Add(prompt);
            var buttons = new WrapPanel(); save = owner.MakeButton(owner.T("保存并预约", "Save & schedule"), async delegate { await SavePlan(true); }); save.Margin = new Thickness(0, 0, 8, 0); buttons.Children.Add(save);
            now = owner.MakeButton(owner.T("立刻执行", "Run now"), async delegate { await owner.PerformAsync(Json.Values("action", "execute_now", "key", Json.Text(chat, "key"), "prompt", prompt.Text, "revision", Json.Integer(chat, "revision"), "request_id", Guid.NewGuid().ToString("D"))); }, true); buttons.Children.Add(now); editorPanel.Children.Add(buttons);
            receiptLabel = Label("", 10); receiptLabel.Foreground = owner.SecondaryBrush; receiptLabel.Margin = new Thickness(0, 10, 0, 0); editorPanel.Children.Add(receiptLabel);
            cancel = owner.MakePlainButton(owner.T("取消此预约", "Cancel this schedule"), async delegate { await SavePlan(false); }); cancel.FontSize = 10; cancel.Foreground = owner.SecondaryBrush; cancel.Margin = new Thickness(0, 8, 0, 0); cancel.HorizontalAlignment = HorizontalAlignment.Left; editorPanel.Children.Add(cancel);
            bool layoutInitialized = false, narrowLayout = false;
            SizeChanged += delegate {
                bool narrow = ActualWidth - Padding.Left - Padding.Right < 740; if (layoutInitialized && narrow == narrowLayout) return; layoutInitialized = true; narrowLayout = narrow;
                columns.ColumnDefinitions.Clear(); columns.RowDefinitions.Clear(); Grid.SetRow(info, 0); Grid.SetColumn(info, 0); Grid.SetColumnSpan(info, 1);
                if (narrow)
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); columns.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    info.Margin = new Thickness(0, 0, 0, 22); Grid.SetRow(right, 1); Grid.SetColumn(right, 0);
                }
                else
                {
                    columns.ColumnDefinitions.Add(new ColumnDefinition()); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(24) }); columns.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(360) });
                    info.Margin = new Thickness(0); Grid.SetRow(right, 0); Grid.SetColumn(right, 2);
                }
            };
        }
        TextBlock Label(string value, int size, bool bold = false)
        { return new TextBlock { Text = value, FontSize = size, Foreground = owner.ForegroundBrush, FontWeight = bold ? FontWeights.Bold : FontWeights.Normal, TextWrapping = TextWrapping.Wrap, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, LineHeight = MissionWindow.TextLineHeight(size), Margin = new Thickness(0) }; }
        async Task SavePlan(bool enabled)
        {
            var plan = Json.Child(chat, "plan"); int revision = enabled && dirty ? draftRevision : Json.Integer(plan, "revision");
            string text = enabled ? prompt.Text : Json.Text(plan, "prompt", owner.T("继续任务", "Continue the task"));
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
            string iconName = "terminal"; if (!Object.Equals(typeIconHost.Tag, iconName)) { typeIconHost.Tag = iconName; typeIconHost.Content = owner.Glyph(iconName, owner.AccentBrush, 15); }
            string source = owner.T("Codex · 本机", "Codex · Local");
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
            auto.Content = ""; auto.Width = 50;
            string autoState = !Json.Bool(chat, "can_control") ? owner.T("不可用", "Unavailable") : connection == "waiting_global" ? owner.T("等待启用", "Waiting") : connection == "failed" ? owner.T("未连接", "Not connected") : Json.Bool(chat, "auto_pending") ? owner.T("连接中", "Connecting") : automatic ? owner.T("已开启", "On") : owner.T("已关闭", "Off");
            System.Windows.Automation.AutomationProperties.SetName(auto, owner.T("榨汁状态", "Juicing") + " · " + autoState);
            auto.ToolTip = autoState;
            bool controllable = Json.Bool(chat, "can_control") && owner.ControlAvailable, available = owner.Healthy && !owner.IsBusy;
            auto.IsEnabled = ChatControlPolicy.CanToggleAutomatic(chat, owner.Healthy, owner.ControlAvailable, owner.IsBusy, owner.CanSubmitLocalChange);
            retry.Visibility = connection == "failed" ? Visibility.Visible : Visibility.Collapsed; retry.IsEnabled = controllable && available;
            autoError.Text = owner.Localized(chat, "auto_error"); autoError.Visibility = connection == "failed" && autoError.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
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
            string draftText; int revision; if (owner.ReadDraft(Json.Text(chat, "key"), out draftText, out revision)) { dirty = true; draftRevision = revision; if (!prompt.IsKeyboardFocusWithin && prompt.Text != draftText) prompt.Text = draftText; }
            else if (!dirty && !prompt.IsKeyboardFocusWithin) { string storedPrompt = Json.Text(plan, "prompt", owner.T("继续任务", "Continue the task")); if (prompt.Text != storedPrompt) prompt.Text = storedPrompt; draftRevision = Json.Integer(plan, "revision"); }
            prompt.IsReadOnly = !controllable || planState == "sending";
            save.Content = scheduled ? owner.T("保存指令", "Save instruction") : owner.T("保存并预约", "Save & schedule"); save.IsEnabled = controllable && available && canSchedule && planState != "sending";
            var immediate = Json.Child(chat, "immediate"); string receipt = Json.Text(immediate, "state");
            now.IsEnabled = controllable && available && Json.Text(runtime, "type") != "active" && !waitingInput && receipt != "pending" && receipt != "checking" && receipt != "sending" && planState != "sending" && PermitsImmediate(usage);
            receiptLabel.Text = receipt.Length > 0 ? ReceiptLabel(receipt) + " " + owner.Localized(immediate, "message") : !canSchedule ? owner.T("暂无可预约窗口", "No reset window available") : "";
            string reason = owner.Localized(plan, "reason"); if (reason.Length > 0) receiptLabel.Text += (receiptLabel.Text.Length == 0 ? "" : "\n") + reason;
            receiptLabel.Visibility = receiptLabel.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            cancel.Visibility = planState == "needs_review" ? Visibility.Visible : Visibility.Collapsed; cancel.IsEnabled = !owner.IsBusy && owner.CanSubmitLocalChange && ChatControlPolicy.IsLocal(chat);
            bool editorVisible = Json.Bool(chat, "can_control") || (ChatControlPolicy.IsLocal(chat) && (planState == "armed" || planState == "needs_review"));
            editorPanel.Visibility = editorVisible ? Visibility.Visible : Visibility.Collapsed; directoryPanel.Visibility = editorVisible ? Visibility.Collapsed : Visibility.Visible;
            directoryText.Text = owner.T("Codex 客户端控制尚待核验，当前只读显示。", "Codex client control awaits verification. This task is read-only.");
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
        static string AppVersion()
        {
            var assembly = System.Reflection.Assembly.GetExecutingAssembly();
            var attribute = assembly.GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false).FirstOrDefault() as System.Reflection.AssemblyInformationalVersionAttribute;
            return attribute != null ? attribute.InformationalVersion : assembly.GetName().Version.ToString();
        }
        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--self-test")
            {
                bool revocationChecks = ChatControlPolicy.SelfTest(); bool startupChecks = StartupDiagnostic.SelfTest(); bool paletteChecks = ThemePalette.SelfTest(); bool rulesChecks = RulesPolicy.SelfTest(); bool quotaEventChecks = QuotaRestorationEvents.SelfTest(); bool activityFilterChecks = ActivityEventFilter.SelfTest(); bool brandChecks = JuicerLogo.SelfTest() && NotificationCopy.SelfTest();
                string result = Json.Stringify(Json.Values("version", AppVersion(), "platform", "windows", "native", true, "ui", "WPF", "webView", false,
                    "hostStarted", false, "messagesSent", 0, "cacheRefreshSeconds", 5, "localRevocationChecks", revocationChecks, "startupDiagnosticFallbackChecks", startupChecks, "themePaletteChecks", paletteChecks, "rulesValidationChecks", rulesChecks, "quotaRestorationEventChecks", quotaEventChecks, "activityFilterChecks", activityFilterChecks, "brandPresentationChecks", brandChecks));
                if (args.Length > 1) File.WriteAllText(args[1], result, new UTF8Encoding(false));
                Console.WriteLine(result); return revocationChecks && startupChecks && paletteChecks && rulesChecks && quotaEventChecks && activityFilterChecks && brandChecks ? 0 : 1;
            }
            if (args.Length > 0 && args[0] == "--textbox-layout-self-test")
            {
                if (args.Length != 2 && (args.Length != 4 || args[2] != "--image")) return 1;
                try
                {
                    var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                    var fixture = Json.Values("healthy", true, "stale", false, "running", true, "tasks", new object[0]);
                    var window = new MissionWindow(true, fixture, "en", "light");
                    var result = window.RunTextBoxLayoutSelfTest(args.Length == 4 ? args[3] : null);
                    string path = Path.GetFullPath(args[1]); Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllText(path, Json.Stringify(result), new UTF8Encoding(false));
                    bool passed = Json.Bool(result, "checksPassed"); window.EndLifecycleFixture(); app.Shutdown(); return passed ? 0 : 1;
                }
                catch (Exception error) { Console.Error.WriteLine(error.ToString()); return 1; }
            }
            if (args.Length > 0 && args[0] == "--editor-self-test")
            {
                if (args.Length != 2) return 1;
                try
                {
                    var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                    var fixture = Json.Values("healthy", true, "stale", false, "running", true, "tasks", new object[0], "rules", Json.Values("revision", 4, "values", RulesPolicy.DefaultsObject()));
                    var window = new MissionWindow(true, fixture, "en", "light"); var result = window.RunRulesEditorSelfTest();
                    File.WriteAllText(Path.GetFullPath(args[1]), Json.Stringify(result), new UTF8Encoding(false));
                    app.Shutdown(); return Json.Bool(result, "checksPassed") ? 0 : 1;
                }
                catch (Exception ex) { Console.Error.WriteLine(ex.ToString()); return 1; }
            }
            if (args.Length > 0 && args[0] == "--lifecycle-self-test")
            {
                if (args.Length != 2) return 1;
                var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown }; var failures = new List<string>();
                app.DispatcherUnhandledException += delegate(object sender, DispatcherUnhandledExceptionEventArgs e) { failures.Add(e.Exception.ToString()); e.Handled = true; };
                var fixture = Json.Values("healthy", true, "stale", false, "running", true, "tasks", new object[0]);
                var window = new MissionWindow(true, fixture, "en", "light"); app.MainWindow = window; int lifecycleExit = 1;
                app.Startup += delegate { window.Dispatcher.BeginInvoke(new Action(async delegate {
                    Dictionary<string, object> result;
                    try { result = await window.RunLifecycleSelfTestAsync(); }
                    catch (Exception ex) { result = Json.Values("native", true, "hostStarted", false, "messagesSent", 0, "checksPassed", false, "error", ex.ToString()); }
                    try { window.EndLifecycleFixture(); } catch (Exception ex) { failures.Add(ex.ToString()); }
                    result["dispatcherExceptions"] = failures.ToArray(); bool passed = Json.Bool(result, "checksPassed") && failures.Count == 0; result["checksPassed"] = passed;
                    lifecycleExit = passed ? 0 : 1;
                    try { string path = Path.GetFullPath(args[1]); Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllText(path, Json.Stringify(result), new UTF8Encoding(false)); }
                    catch { lifecycleExit = 1; }
                    app.Shutdown(lifecycleExit);
                })); }; app.Run(); return lifecycleExit;
            }
            if (args.Length > 0 && args[0] == "--ui-self-test")
            {
                try
                {
                    if (args.Length < 3) throw new ArgumentException("Usage: --ui-self-test fixture.json preview.png [--language zh|en] [--theme system|light|dark] [--view home|settings|activity|rules|tray] [--accent green|blue|purple|yellow] [--scale 1|2]");
                    string language = "zh", theme = "system", previewView = "home", accent = "green"; double scale = 2; int positional = 0;
                    for (int index = 3; index < args.Length; index++)
                    {
                        if (args[index] == "--language" && index + 1 < args.Length) language = args[++index];
                        else if (args[index] == "--theme" && index + 1 < args.Length) theme = args[++index];
                        else if (args[index] == "--accent" && index + 1 < args.Length) accent = args[++index];
                        else if (args[index] == "--view" && index + 1 < args.Length) previewView = args[++index];
                        else if (args[index] == "--scale" && index + 1 < args.Length) scale = Double.Parse(args[++index], CultureInfo.InvariantCulture);
                        else if (args[index].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Unknown or incomplete fixture option.");
                        else if (positional++ == 0) language = args[index];
                        else if (positional == 2) theme = args[index];
                        else throw new ArgumentException("Unknown fixture argument.");
                    }
                    if (!new[] { "home", "settings", "activity", "rules", "tray" }.Contains(previewView)) throw new ArgumentException("Unknown fixture view.");
                    if (scale != 1 && scale != 2) throw new ArgumentException("Fixture scale must be 1 or 2.");
                    if (!ThemePalette.Keys.Contains(accent)) throw new ArgumentException("Unknown fixture accent.");
                    var fixture = Json.Parse(File.ReadAllText(args[1])); var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                    var window = new MissionWindow(true, fixture, language, theme, accent);
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
                            "desktopResolutionIndependent", true, "privatePreferencesLoaded", false, "language", language, "theme", theme, "accent", accent)), new UTF8Encoding(false));
                        }
                        catch (Exception ex) { renderExit = 1; Console.Error.WriteLine(ex.ToString()); }
                        finally { app.Shutdown(renderExit); }
                    })); }; app.Run(); return renderExit;
                }
                catch (Exception ex) { Console.Error.WriteLine(ex.ToString()); return 1; }
            }
            bool created; using (var mutex = new Mutex(true, @"Local\CodexMissionManager-Windows", out created))
            {
                if (!created) { MessageBox.Show("TOKEN榨汁机已在运行，请从系统托盘打开。\nTokenMax is already running. Open it from the system tray.", "TokenMax"); return 0; }
                var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
                var window = new MissionWindow(false, null); app.MainWindow = window;
                app.Startup += delegate { if (args.Contains("--background")) window.EnsureHostStarted(); else window.Show(); };
                app.Run(); return 0;
            }
        }
    }
}
