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
        const string ProductPreview = "__PRODUCT_PREVIEW__";
        const string ExpectedSha256 = "__PAYLOAD_SHA256__";
        const string ExpectedBytes = "__PAYLOAD_BYTES__";
        const string FooterMagic = "CMM-PAYLOAD-0001";
        const string ProductMarker = "CodexMissionManager.Windows.PerUser";
        const string UninstallRegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexMissionManager";
        const string RunRegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        static string selfTestStage = "not_started";
        static readonly Dictionary<string, object> selfTestEvidence = new Dictionary<string, object>();
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
                        throw new InvalidOperationException(T("请先退出榨汁机，再继续安装。", "Quit TokenMax before continuing."));
                    }
                    if (String.Equals(Path.GetFullPath(path), expected, StringComparison.OrdinalIgnoreCase) || String.Equals(Path.GetFullPath(path), python, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException(T("请从托盘菜单退出榨汁机后继续。", "Quit TokenMax from its tray menu before continuing."));
                }
            }
        }
        // Explicit Unicode shell COM contract. WScript.Shell can lose Chinese
        // .lnk names through ANSI conversion on an English Windows installation.
        // The complete IShellLinkW vtable order must be preserved, even for unused methods.
        // https://learn.microsoft.com/windows/win32/api/shobjidl_core/nn-shobjidl_core-ishelllinkw
        [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
        sealed class ShellLink { }
        [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IShellLinkW
        {
            void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int capacity, IntPtr findData, uint flags);
            void GetIDList(out IntPtr idList);
            void SetIDList(IntPtr idList);
            void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder description, int capacity);
            void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string description);
            void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder directory, int capacity);
            void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string directory);
            void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder arguments, int capacity);
            void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string arguments);
            void GetHotkey(out short hotkey);
            void SetHotkey(short hotkey);
            void GetShowCmd(out int command);
            void SetShowCmd(int command);
            void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int capacity, out int index);
            void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
            void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
            void Resolve(IntPtr window, uint flags);
            void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
        }
        static void Shortcut(string path, string executable)
        {
            object instance = null;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                if (File.Exists(path))
                    File.Copy(path, path + ".previous-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N").Substring(0, 6));
                instance = new ShellLink();
                var shortcut = (IShellLinkW)instance;
                shortcut.SetPath(executable);
                shortcut.SetWorkingDirectory(Path.GetDirectoryName(executable));
                shortcut.SetDescription(T("榨汁机", "TokenMax"));
                shortcut.SetIconLocation(executable, 0);
                var file = (System.Runtime.InteropServices.ComTypes.IPersistFile)instance;
                file.Save(path, true);
                file.SaveCompleted(null);
            }
            finally { if (instance != null && Marshal.IsComObject(instance)) Marshal.FinalReleaseComObject(instance); }
        }
        static string ShortcutTarget(string path)
        {
            if (!File.Exists(path)) return null;
            object instance = null;
            try
            {
                instance = new ShellLink();
                ((System.Runtime.InteropServices.ComTypes.IPersistFile)instance).Load(path, 0); // STGM_READ
                var target = new StringBuilder(32768);
                ((IShellLinkW)instance).GetPath(target, target.Capacity, IntPtr.Zero, 4); // SLGP_RAWPATH; never resolve or rewrite a target.
                return target.Length == 0 ? null : target.ToString();
            }
            finally { if (instance != null && Marshal.IsComObject(instance)) Marshal.FinalReleaseComObject(instance); }
        }
        static string ShortcutName { get { return T("榨汁机.lnk", "TokenMax.lnk"); } }
        static IEnumerable<string> KnownShortcutPaths()
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
            foreach (string name in new[] { "任务管家.lnk", "榨汁机.lnk", "TokenMax.lnk" })
            {
                yield return Path.Combine(desktop, name);
                foreach (string folder in new[] { "Codex Mission Manager", "TokenMax" }) yield return Path.Combine(programs, folder, name);
            }
        }
        static bool MatchesShortcut(string path, string executable)
        {
            try { return String.Equals(ShortcutTarget(path), executable, StringComparison.OrdinalIgnoreCase); }
            catch (System.Runtime.InteropServices.COMException) { return false; }
            catch (IOException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
        }
        static void RemoveEmptyShortcutFolders()
        {
            foreach (string name in new[] { "Codex Mission Manager", "TokenMax" })
            {
                string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), name);
                if (Directory.Exists(folder) && Directory.GetFileSystemEntries(folder).Length == 0) Directory.Delete(folder);
            }
        }
        static void RemoveMatchingShortcuts(IEnumerable<string> paths, string executable, string desktop, string menu)
        {
            foreach (string path in paths)
            {
                if (String.Equals(path, desktop, StringComparison.OrdinalIgnoreCase) || String.Equals(path, menu, StringComparison.OrdinalIgnoreCase)) continue;
                if (MatchesShortcut(path, executable))
                { try { File.Delete(path); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
            }
        }
        static void MigrateOwnedShortcuts(string executable, string desktop, string menu)
        {
            RemoveMatchingShortcuts(KnownShortcutPaths(), executable, desktop, menu);
            try { RemoveEmptyShortcutFolders(); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
        static bool ShortcutMigrationSelfTest()
        {
            // A private temporary fixture: never inspect or modify real shortcuts.
            string root = Path.Combine(Path.GetTempPath(), "TokenMax-shortcut-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string executable = Path.Combine(root, "CodexMissionManager.exe"), other = Path.Combine(root, "Other.exe");
                string legacy = Path.Combine(root, "任务管家.lnk"), current = Path.Combine(root, "TokenMax.lnk"), foreign = Path.Combine(root, "榨汁机.lnk");
                // Existing inert files avoid shell resolution of dangling targets; never execute them.
                File.WriteAllBytes(executable, new byte[0]); File.WriteAllBytes(other, new byte[0]);
                selfTestEvidence["target_files_exist"] = File.Exists(executable) && File.Exists(other);
                selfTestStage = "shortcut_create_legacy"; Shortcut(legacy, executable);
                selfTestStage = "shortcut_create_current"; Shortcut(current, executable);
                selfTestStage = "shortcut_create_foreign"; Shortcut(foreign, other);
                selfTestStage = "shortcut_read_targets";
                selfTestEvidence["expected_target"] = executable;
                selfTestEvidence["legacy_target"] = ShortcutTarget(legacy);
                selfTestEvidence["current_target"] = ShortcutTarget(current);
                selfTestEvidence["foreign_target"] = ShortcutTarget(foreign);
                if (!MatchesShortcut(legacy, executable)) throw new InvalidOperationException("The legacy shortcut target did not match its fixture executable.");
                if (MatchesShortcut(foreign, executable)) throw new InvalidOperationException("A foreign shortcut incorrectly matched the fixture executable.");
                selfTestStage = "shortcut_migration";
                RemoveMatchingShortcuts(new[] { legacy, current, foreign }, executable, current, Path.Combine(root, "Menu.lnk"));
                selfTestEvidence["legacy_removed"] = !File.Exists(legacy);
                selfTestEvidence["current_preserved"] = File.Exists(current) && MatchesShortcut(current, executable);
                selfTestEvidence["foreign_preserved"] = File.Exists(foreign) && MatchesShortcut(foreign, other);
                return (bool)selfTestEvidence["legacy_removed"] && (bool)selfTestEvidence["current_preserved"] && (bool)selfTestEvidence["foreign_preserved"];
            }
            finally { Directory.Delete(root, true); }
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
                key.SetValue("DisplayName", T("榨汁机 · TokenMax", "TokenMax"));
                key.SetValue("DisplayVersion", ProductVersion + "-" + ProductPreview);
                key.SetValue("Publisher", "TokenMax contributors");
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
            if (!Directory.Exists(target) || !File.Exists(markerPath)) throw new InvalidOperationException("No registered TokenMax installation was found.");
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
            if (!quiet && MessageBox.Show(T("卸载榨汁机？账号和任务数据将保留。", "Uninstall TokenMax? Account and task data will be kept."), T("卸载榨汁机", "Uninstall TokenMax"), MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return 2;
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
                var links = new List<string>();
                foreach (string path in KnownShortcutPaths()) if (MatchesShortcut(path, executable)) links.Add(path);
                Directory.Delete(target, true);
                foreach (string link in links) if (File.Exists(link)) File.Delete(link);
                RemoveEmptyShortcutFolders();
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
            if (!quiet) MessageBox.Show(T("榨汁机已卸载，私人数据已保留。", "TokenMax was removed. Private data was preserved."), T("榨汁机", "TokenMax"), MessageBoxButtons.OK, MessageBoxIcon.Information);
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
                    string desktopLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), ShortcutName);
                    string menuLink = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "TokenMax", ShortcutName);
                    Shortcut(desktopLink, executable);
                    Shortcut(menuLink, executable);
                    var result = new Dictionary<string, object> {
                        { "version", ProductVersion }, { "preview", ProductPreview }, { "installed", true },
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
                    MigrateOwnedShortcuts(executable, desktopLink, menuLink);
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
            var form = new Form { Text = T("榨汁机安装", "TokenMax Setup"), ClientSize = new Size(560, 305), StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, Font = new Font("Segoe UI", 10F), BackColor = Color.White };
            var title = new Label { Text = T("安装榨汁机", "Install TokenMax"), Location = new Point(28, 24), AutoSize = true, Font = new Font("Segoe UI", 19F, FontStyle.Bold) };
            var description = new Label { Text = T("V" + ProductVersion + " · Windows 预览版\n包含所需运行环境；保留账号和任务数据。", "V" + ProductVersion + " · Windows preview\nIncludes required runtime. Keeps account and task data."), Location = new Point(30, 76), Size = new Size(500, 62) };
            var pathLabel = new Label { Text = InstallationDirectory, Location = new Point(30, 148), Size = new Size(500, 42), ForeColor = Color.DimGray };
            var launch = new CheckBox { Text = T("安装后打开榨汁机", "Open TokenMax after installation"), Location = new Point(30, 195), AutoSize = true, Checked = Array.IndexOf(args, "--no-launch") < 0 };
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
                if (selfTest) selfTestStage = "payload_verification";
                byte[] payload = Payload();
                if (selfTest)
                {
                    selfTestStage = "archive_validation";
                    int count = ValidateArchive(payload, Path.Combine(Path.GetTempPath(), "MissionManagerValidation-" + Guid.NewGuid().ToString("N")), false);
                    selfTestEvidence["shortcut_api"] = "IShellLinkW/IPersistFile";
                    selfTestStage = "shortcut_fixture_setup";
                    bool shortcutChecks = ShortcutMigrationSelfTest();
                    if (!shortcutChecks) throw new InvalidOperationException("Shortcut migration safety checks failed.");
                    selfTestStage = "complete";
                    Report(args, new Dictionary<string, object> { { "self_test_stage", selfTestStage }, { "shortcut_migration_checks", shortcutChecks }, { "version", ProductVersion }, { "preview", ProductPreview }, { "native_installer", true }, { "payload_verified", true }, { "payload_sha256", ExpectedSha256 }, { "payload_bytes", payload.Length }, { "files", count }, { "installed", false }, { "host_started", false }, { "private_data_loaded", false }, { "per_user_uninstaller_available", true } });
                    return 0;
                }
                if (!quiet) return ShowInstaller(payload, args);
                Report(args, Install(payload, Array.IndexOf(args, "--no-launch") < 0, message => { }));
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.Message);
                if (!quiet) MessageBox.Show(error.Message, T("榨汁机安装", "TokenMax Setup"), MessageBoxButtons.OK, MessageBoxIcon.Error);
                try
                {
                    var failure = new Dictionary<string, object> { { "installed", false }, { "error", error.Message } };
                    if (selfTest)
                    {
                        var chain = new List<Dictionary<string, object>>();
                        for (Exception current = error; current != null; current = current.InnerException)
                            chain.Add(new Dictionary<string, object> { { "type", current.GetType().FullName }, { "message", current.Message }, { "hresult", current.HResult.ToString("X8", CultureInfo.InvariantCulture) } });
                        failure["self_test_stage"] = selfTestStage; failure["exceptions"] = chain; failure["fixture_evidence"] = selfTestEvidence;
                    }
                    Report(args, failure);
                }
                catch { }
                return 1;
            }
        }
    }
}
