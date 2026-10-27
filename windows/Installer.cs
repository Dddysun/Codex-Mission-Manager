// Native, per-user preview installer. C# 5 / .NET Framework 4.8.
// The build appends a reviewed ZIP and footer to this compiled stub.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace CodexMissionManagerSetup
{
    static class Installer
    {
        const string ProductVersion = "__PRODUCT_VERSION__";
        const string ExpectedSha256 = "__PAYLOAD_SHA256__";
        const string ExpectedBytes = "__PAYLOAD_BYTES__";
        const string FooterMagic = "CMM-PAYLOAD-0001";
        const string ProductMarker = "CodexMissionManager.Windows.PerUser";
        const string UninstallRegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexMissionManager";
        const string RunRegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        static readonly bool Chinese = CultureInfo.CurrentUICulture.Name.StartsWith("zh", StringComparison.OrdinalIgnoreCase);

        static string T(string zh, string en) { return Chinese ? zh : en; }
        static string InstallationDirectory
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "CodexMissionManager"); }
        }
        static string Serialize(object value) { return new JavaScriptSerializer().Serialize(value); }
        static string ArgumentValue(string[] args, string key)
        {
            int index = Array.IndexOf(args, key);
            return index >= 0 && index + 1 < args.Length && !args[index + 1].StartsWith("--", StringComparison.Ordinal) ? args[index + 1] : null;
        }
        static void Report(string[] args, object value)
        {
            string text = Serialize(value);
            string path = ArgumentValue(args, "--report");
            if (path == null && Array.IndexOf(args, "--self-test") >= 0) path = ArgumentValue(args, "--self-test");
            if (path != null) File.WriteAllText(Path.GetFullPath(path), text + Environment.NewLine, new UTF8Encoding(false));
            Console.WriteLine(text);
        }
        static byte[] Payload()
        {
            long expected;
            if (ExpectedSha256.Length != 64 || !Int64.TryParse(ExpectedBytes, NumberStyles.None, CultureInfo.InvariantCulture, out expected))
                throw new InvalidDataException("This installer has no sealed payload.");
            byte[] magic = Encoding.ASCII.GetBytes(FooterMagic);
            using (FileStream file = File.Open(Assembly.GetExecutingAssembly().Location, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (file.Length < 24) throw new InvalidDataException("Installer payload footer is missing.");
                file.Position = file.Length - magic.Length - 8;
                long length;
                using (BinaryReader reader = new BinaryReader(file, Encoding.UTF8, true))
                {
                    length = reader.ReadInt64();
                    byte[] actualMagic = reader.ReadBytes(magic.Length);
                    if (actualMagic.Length != magic.Length) throw new InvalidDataException("Installer footer is incomplete.");
                    for (int i = 0; i < magic.Length; i++)
                        if (actualMagic[i] != magic[i]) throw new InvalidDataException("Installer footer does not match.");
                }
                if (length != expected || length < 64 || length > 256L * 1024 * 1024 || file.Length - 24 - length < 512)
                    throw new InvalidDataException("Installer payload length is invalid.");
                file.Position = file.Length - 24 - length;
                byte[] bytes = new byte[(int)length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = file.Read(bytes, offset, bytes.Length - offset);
                    if (read <= 0) throw new EndOfStreamException("Installer payload is incomplete.");
                    offset += read;
                }
                using (SHA256 hash = SHA256.Create())
                {
                    string actual = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                    if (!String.Equals(actual, ExpectedSha256, StringComparison.Ordinal))
                        throw new InvalidDataException("Installer payload checksum verification failed.");
                }
                return bytes;
            }
        }
        static int ValidateArchive(byte[] payload, string destination, bool extract)
        {
            string root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long total = 0;
            using (var stream = new MemoryStream(payload, false))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Read, false))
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
                    if (String.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.IndexOf(':') >= 0)
                        throw new InvalidDataException("Archive contains an invalid path.");
                    string path = Path.GetFullPath(Path.Combine(root, relative));
                    if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !names.Add(path))
                        throw new InvalidDataException("Archive path escapes the installation directory or is duplicated.");
                    total += entry.Length;
                    if (total > 512L * 1024 * 1024) throw new InvalidDataException("Archive expansion exceeds the package limit.");
                    if (!extract) continue;
                    if (entry.FullName.EndsWith("/", StringComparison.Ordinal) || entry.FullName.EndsWith("\\", StringComparison.Ordinal))
                    {
                        Directory.CreateDirectory(path);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using (Stream input = entry.Open())
                    using (FileStream output = File.Open(path, FileMode.CreateNew, FileAccess.Write, FileShare.None)) input.CopyTo(output);
                }
            }
            foreach (string required in new[] { "CodexMissionManager.exe", "runtime/python/python.exe", "backend/app_host.py", "backend/config.example.json" })
            {
                string path = Path.GetFullPath(Path.Combine(root, required.Replace('/', Path.DirectorySeparatorChar)));
                if (!names.Contains(path)) throw new InvalidDataException("Archive is missing a required application file.");
            }
            if (names.Contains(Path.Combine(root, "backend", "config.json")) || names.Contains(Path.Combine(root, "auth.json")))
                throw new InvalidDataException("Archive contains private runtime configuration.");
            return names.Count;
        }
        static void EnsureStopped(string target)
        {
            string expected = Path.Combine(target, "CodexMissionManager.exe");
            string python = Path.Combine(target, "runtime", "python", "python.exe");
            var candidates = new List<Process>();
            candidates.AddRange(Process.GetProcessesByName("CodexMissionManager"));
            candidates.AddRange(Process.GetProcessesByName("python"));
            foreach (Process process in candidates)
            {
                using (process)
                {
                    if (process.HasExited) continue;
                    string path;
                    try { path = process.MainModule.FileName; }
                    catch (InvalidOperationException) { continue; }
                    catch (System.ComponentModel.Win32Exception)
                    {
                        if (process.ProcessName == "python") continue;
                        throw new InvalidOperationException(T("无法核对正在运行的任务管家。请先退出程序后再继续。", "A running Mission Manager could not be checked. Close it before continuing."));
                    }
                    if (String.Equals(Path.GetFullPath(path), expected, StringComparison.OrdinalIgnoreCase) || String.Equals(Path.GetFullPath(path), python, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException(T("任务管家仍在运行，请从托盘菜单退出并等待后台停止后再继续。", "Mission Manager is still running. Quit it from its tray menu and wait for its background process to stop before continuing."));
                }
            }
        }
        static void Shortcut(string path, string executable)
        {
            object shell = null, shortcut = null;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                if (File.Exists(path))
                    File.Copy(path, path + ".previous-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N").Substring(0, 6));
                Type type = Type.GetTypeFromProgID("WScript.Shell", true);
                shell = Activator.CreateInstance(type);
                shortcut = type.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { executable });
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { Path.GetDirectoryName(executable) });
                shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { "Codex Mission Manager" });
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { executable + ",0" });
                shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, new object[0]);
            }
            finally
            {
                if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
                if (shell != null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
            }
        }
        static string ShortcutTarget(string path)
        {
            if (!File.Exists(path)) return null;
            object shell = null, shortcut = null;
            try
            {
                Type type = Type.GetTypeFromProgID("WScript.Shell", true);
                shell = Activator.CreateInstance(type);
                shortcut = type.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
                return shortcut.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, shortcut, null) as string;
            }
            finally
            {
                if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
                if (shell != null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
            }
        }
        sealed class RegistrySnapshot
        {
            public bool Exists;
            public Dictionary<string, object> Values = new Dictionary<string, object>();
            public Dictionary<string, RegistryValueKind> Kinds = new Dictionary<string, RegistryValueKind>();
        }
        static RegistrySnapshot SnapshotRegistration()
        {
            var snapshot = new RegistrySnapshot();
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(UninstallRegistryKey))
            {
                snapshot.Exists = key != null;
                if (key != null) foreach (string name in key.GetValueNames()) { snapshot.Values[name] = key.GetValue(name); snapshot.Kinds[name] = key.GetValueKind(name); }
            }
            return snapshot;
        }
        static void RestoreRegistration(RegistrySnapshot snapshot)
        {
            Registry.CurrentUser.DeleteSubKeyTree(UninstallRegistryKey, false);
            if (snapshot.Exists) using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallRegistryKey))
                foreach (var pair in snapshot.Values) key.SetValue(pair.Key, pair.Value, snapshot.Kinds[pair.Key]);
        }
        static void RegisterUninstall(string target)
        {
            string uninstall = Path.Combine(target, "Uninstall.exe");
            long size = 0;
            foreach (string path in Directory.GetFiles(target, "*", SearchOption.AllDirectories)) size += new FileInfo(path).Length;
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallRegistryKey))
            {
                key.SetValue("DisplayName", "任务管家 · Codex Mission Manager");
                key.SetValue("DisplayVersion", ProductVersion + " Windows preview 1");
                key.SetValue("Publisher", "Codex Mission Manager contributors");
                key.SetValue("InstallLocation", target);
                key.SetValue("DisplayIcon", Path.Combine(target, "CodexMissionManager.exe") + ",0");
                key.SetValue("UninstallString", "\"" + uninstall + "\" --uninstall");
                key.SetValue("QuietUninstallString", "\"" + uninstall + "\" --uninstall --quiet");
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                key.SetValue("EstimatedSize", (int)Math.Min(Int32.MaxValue, (size + 1023) / 1024), RegistryValueKind.DWord);
            }
        }
        static Dictionary<string, object> InstalledMarker()
        {
            string target = InstallationDirectory;
            string markerPath = Path.Combine(target, "installation.json");
            if (!Directory.Exists(target) || !File.Exists(markerPath)) throw new InvalidOperationException("No registered Mission Manager installation was found.");
            var marker = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(markerPath, Encoding.UTF8));
            object product, id, path;
            if (marker == null || !marker.TryGetValue("product_marker", out product) || !String.Equals(product as string, ProductMarker, StringComparison.Ordinal) ||
                !marker.TryGetValue("installation_id", out id) || String.IsNullOrWhiteSpace(id as string) ||
                !marker.TryGetValue("install_path", out path) || !String.Equals(path as string, target, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("The installed application marker does not match this per-user application.");
            return marker;
        }
        static void CopyCleanupStub(string destination)
        {
            // Only copy the PE stub; no Python/runtime payload is needed for cleanup.
            using (FileStream source = File.OpenRead(Assembly.GetExecutingAssembly().Location))
            {
                source.Position = source.Length - 24;
                long length;
                using (var reader = new BinaryReader(source, Encoding.UTF8, true)) length = reader.ReadInt64();
                long count = source.Length - 24 - length;
                if (count < 512 || count > 4 * 1024 * 1024) throw new InvalidDataException("The cleanup program boundary is invalid.");
                source.Position = 0;
                using (FileStream output = File.Open(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    byte[] buffer = new byte[65536];
                    while (count > 0)
                    {
                        int read = source.Read(buffer, 0, (int)Math.Min(buffer.Length, count));
                        if (read <= 0) throw new EndOfStreamException();
                        output.Write(buffer, 0, read); count -= read;
                    }
                }
            }
        }
        static int BeginUninstall(string[] args, bool quiet)
        {
            Payload(); // Authenticate the installed uninstaller before starting cleanup.
            var marker = InstalledMarker();
            EnsureStopped(InstallationDirectory);
            if (!quiet && MessageBox.Show(T("仅移除任务管家程序和快捷方式。账号登录、任务账本及私人配置将保留。是否继续？", "Remove the Mission Manager application and shortcuts? Account sign-in, task ledger and private configuration will be preserved."), T("卸载任务管家", "Uninstall Mission Manager"), MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 2;
            string cleanup = Path.Combine(Path.GetTempPath(), "CodexMissionManager-Cleanup-" + Guid.NewGuid().ToString("N") + ".exe");
            CopyCleanupStub(cleanup);
            string arguments = "--complete-uninstall --parent-pid " + Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture) + " --installation-id " + (string)marker["installation_id"];
            string report = ArgumentValue(args, "--report");
            if (quiet) arguments += " --quiet";
            if (report != null) arguments += " --report \"" + Path.GetFullPath(report) + "\"";
            Process.Start(new ProcessStartInfo(cleanup, arguments) { UseShellExecute = false, CreateNoWindow = true });
            return 0;
        }
        static int CompleteUninstall(string[] args, bool quiet)
        {
            int parent;
            if (!Int32.TryParse(ArgumentValue(args, "--parent-pid"), NumberStyles.None, CultureInfo.InvariantCulture, out parent) || parent <= 0)
                throw new ArgumentException("The uninstall parent process is invalid.");
            try
            {
                using (Process process = Process.GetProcessById(parent))
                    if (!process.WaitForExit(20000)) throw new InvalidOperationException("The uninstall program has not exited.");
            }
            catch (ArgumentException) { }
            string target = InstallationDirectory;
            using (FileStream installLock = File.Open(target + ".install.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
            {
                var marker = InstalledMarker();
                if (!String.Equals(marker["installation_id"] as string, ArgumentValue(args, "--installation-id"), StringComparison.Ordinal))
                    throw new InvalidOperationException("The installation changed after uninstall was requested; it was preserved.");
                EnsureStopped(target);
                // Record only links that still point to this exact installation.
                string executable = Path.Combine(target, "CodexMissionManager.exe");
                string menuFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Codex Mission Manager");
                var links = new List<string>();
                foreach (string path in new[] { Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "任务管家.lnk"), Path.Combine(menuFolder, "任务管家.lnk") })
                    if (String.Equals(ShortcutTarget(path), executable, StringComparison.OrdinalIgnoreCase)) links.Add(path);
                Directory.Delete(target, true);
                foreach (string link in links) if (File.Exists(link)) File.Delete(link);
                if (Directory.Exists(menuFolder) && Directory.GetFileSystemEntries(menuFolder).Length == 0) Directory.Delete(menuFolder);
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(RunRegistryKey, true))
                {
                    string value = key == null ? null : key.GetValue("CodexMissionManager") as string;
                    if (String.Equals(value, "\"" + executable + "\" --background", StringComparison.OrdinalIgnoreCase)) key.DeleteValue("CodexMissionManager", false);
                }
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(UninstallRegistryKey))
                {
                    string location = key == null ? null : key.GetValue("InstallLocation") as string;
                    if (String.Equals(location, target, StringComparison.OrdinalIgnoreCase)) Registry.CurrentUser.DeleteSubKeyTree(UninstallRegistryKey, false);
                }
            }
            Report(args, new Dictionary<string, object> { { "uninstalled", true }, { "private_data_directory_preserved", true }, { "other_applications_modified", false }, { "cleanup_stub_retained_in_temp", true } });
            if (!quiet) MessageBox.Show(T("任务管家已卸载，私人数据已保留。", "Mission Manager was removed. Private data was preserved."), T("任务管家", "Mission Manager"), MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        static Dictionary<string, object> Install(byte[] payload, bool launch, Action<string> progress)
        {
            string target = InstallationDirectory;
            string parent = Path.GetDirectoryName(target);
            Directory.CreateDirectory(parent);
            string token = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N").Substring(0, 8);
            string staging = target + ".staging-" + token;
            string previous = target + ".previous-" + token;
            bool movedPrevious = false, installed = false;
            RegistrySnapshot registration = SnapshotRegistration();
            using (FileStream installLock = File.Open(target + ".install.lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
            {
                EnsureStopped(target);
                progress(T("正在校验并展开应用…", "Verifying and extracting application…"));
                Directory.CreateDirectory(staging);
                try
                {
                    int fileCount = ValidateArchive(payload, staging, true);
                    EnsureStopped(target);
                    if (Directory.Exists(target)) { Directory.Move(target, previous); movedPrevious = true; }
                    Directory.Move(staging, target);
                    installed = true;
                    progress(T("正在创建快捷方式…", "Creating shortcuts…"));
                    string executable = Path.Combine(target, "CodexMissionManager.exe");
                    File.Copy(Assembly.GetExecutingAssembly().Location, Path.Combine(target, "Uninstall.exe"), true);
                    Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "任务管家.lnk"), executable);
                    Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Codex Mission Manager", "任务管家.lnk"), executable);
                    var result = new Dictionary<string, object> {
                        { "version", ProductVersion }, { "preview", "windows.1" }, { "installed", true },
                        { "product_marker", ProductMarker }, { "installation_id", Guid.NewGuid().ToString("N") },
                        { "install_path", target }, { "file_count", fileCount }, { "payload_sha256", ExpectedSha256 },
                        { "previous_application_retained", movedPrevious }, { "private_data_directory_modified", false },
                        { "system_security_settings_changed", false }, { "system_power_settings_changed", false },
                        { "shortcuts_created", true }, { "app_launched", false }, { "per_user_uninstall_registered", true }
                    };
                    File.WriteAllText(Path.Combine(target, "installation.json"), Serialize(result) + Environment.NewLine, new UTF8Encoding(false));
                    RegisterUninstall(target);
                    if (launch)
                    {
                        Process.Start(new ProcessStartInfo(executable) { WorkingDirectory = target, UseShellExecute = true });
                        result["app_launched"] = true;
                    }
                    return result;
                }
                catch
                {
                    if (installed && Directory.Exists(target)) Directory.Move(target, target + ".failed-" + token);
                    if (movedPrevious && Directory.Exists(previous) && !Directory.Exists(target)) Directory.Move(previous, target);
                    RestoreRegistration(registration);
                    throw;
                }
                finally
                {
                    // Only this transaction's generated staging directory is removed.
                    if (Directory.Exists(staging)) Directory.Delete(staging, true);
                }
            }
        }
        static int ShowInstaller(byte[] payload, string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            var form = new Form { Text = T("任务管家安装", "Mission Manager Setup"), ClientSize = new Size(560, 305), StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, Font = new Font("Segoe UI", 10F), BackColor = Color.White };
            var title = new Label { Text = T("安装任务管家", "Install Mission Manager"), Location = new Point(28, 24), AutoSize = true, Font = new Font("Segoe UI", 19F, FontStyle.Bold) };
            var description = new Label { Text = T("V" + ProductVersion + " · Windows 预览版\n包含原生窗口及 Python 运行环境。现有聊天、预约及账号登录数据保留。", "V" + ProductVersion + " · Windows preview\nIncludes the native app and Python runtime. Existing chats, plans and sign-in data are preserved."), Location = new Point(30, 76), Size = new Size(500, 62) };
            var pathLabel = new Label { Text = InstallationDirectory, Location = new Point(30, 148), Size = new Size(500, 42), ForeColor = Color.DimGray };
            var launch = new CheckBox { Text = T("安装后打开任务管家", "Open Mission Manager after installation"), Location = new Point(30, 195), AutoSize = true, Checked = Array.IndexOf(args, "--no-launch") < 0 };
            var status = new Label { Text = "", Location = new Point(30, 231), Size = new Size(340, 50) };
            var install = new Button { Text = T("安装", "Install"), Location = new Point(408, 235), Size = new Size(120, 37), FlatStyle = FlatStyle.System };
            bool busy = false, success = false;
            form.FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) e.Cancel = true; };
            install.Click += async delegate
            {
                if (success) { form.Close(); return; }
                busy = true; install.Enabled = false; launch.Enabled = false;
                try
                {
                    bool shouldLaunch = launch.Checked;
                    Dictionary<string, object> result = await Task.Run(() => Install(payload, shouldLaunch, message => form.BeginInvoke(new Action(() => status.Text = message))));
                    Report(args, result);
                    success = true;
                    status.Text = T("安装完成。", "Installation complete.");
                    install.Text = T("完成", "Done");
                }
                catch (Exception error)
                {
                    status.Text = T("安装未完成。", "Installation did not complete.");
                    MessageBox.Show(form, error.Message, form.Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    launch.Enabled = true;
                }
                finally { busy = false; install.Enabled = true; }
            };
            form.Controls.AddRange(new Control[] { title, description, pathLabel, launch, status, install });
            Application.Run(form);
            return success ? 0 : 2;
        }
        [STAThread]
        static int Main(string[] args)
        {
            bool selfTest = Array.IndexOf(args, "--self-test") >= 0;
            bool quiet = Array.IndexOf(args, "--quiet") >= 0 || selfTest;
            try
            {
                if (Array.IndexOf(args, "--complete-uninstall") >= 0) return CompleteUninstall(args, quiet);
                if (Array.IndexOf(args, "--uninstall") >= 0) return BeginUninstall(args, quiet);
                byte[] payload = Payload();
                if (selfTest)
                {
                    int count = ValidateArchive(payload, Path.Combine(Path.GetTempPath(), "MissionManagerValidation-" + Guid.NewGuid().ToString("N")), false);
                    Report(args, new Dictionary<string, object> { { "version", ProductVersion }, { "native_installer", true }, { "payload_verified", true }, { "payload_sha256", ExpectedSha256 }, { "payload_bytes", payload.Length }, { "files", count }, { "installed", false }, { "host_started", false }, { "private_data_loaded", false }, { "per_user_uninstaller_available", true } });
                    return 0;
                }
                if (!quiet) return ShowInstaller(payload, args);
                Report(args, Install(payload, Array.IndexOf(args, "--no-launch") < 0, message => { }));
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.Message);
                if (!quiet) MessageBox.Show(error.Message, T("任务管家安装", "Mission Manager Setup"), MessageBoxButtons.OK, MessageBoxIcon.Error);
                try { Report(args, new Dictionary<string, object> { { "installed", false }, { "error", error.Message } }); } catch { }
                return 1;
            }
        }
    }
}
