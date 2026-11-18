using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Principal;
using System.Text;
using System.Threading;
using Microsoft.Win32;

namespace MailPilot {
    internal static class Deployment {
        internal const string Prog = "MailPilot.Outlook";
        const string Id = "{85C590EA-8141-4C33-99A0-F304FFA27D7E}", Connect = "MailPilot.Connect";
        const string PaneId = "{3AD910BB-5093-45FA-AB6E-68094BC37F22}", PaneProg = "MailPilot.DockHost";
        const string Classes = @"Software\Classes\", Addins = @"Software\Microsoft\Office\Outlook\Addins\" + Prog;
        const string Protocol = Classes + "mailpilot", ProtocolCommand = Protocol + @"\shell\open\command";
        static readonly string[] RegistrationKeys = { Classes + @"CLSID\" + Id, Classes + Prog,
            Classes + @"CLSID\" + PaneId, Classes + PaneProg, Addins, Protocol };

        internal static RegistryView[] Views { get { return Environment.Is64BitOperatingSystem ?
            new[]{RegistryView.Registry64, RegistryView.Registry32} : new[]{RegistryView.Registry32}; } }
        internal static string Dll { get { return Path.Combine(App.Root, "MailPilot.Outlook.dll"); } }
        static string Server(string id) { return Classes + @"CLSID\" + id + @"\InprocServer32"; }
        // RegAsm and earlier MailPilot versions write an unescaped file URI.
        static string CodeBase(string file) { return new Uri(file).GetComponents(UriComponents.AbsoluteUri, UriFormat.Unescaped); }
        static string Command { get { return "\"" + Path.Combine(App.Root, "MailPilot.exe") + "\" \"%1\""; } }
        internal static bool Same(string a, string b) { return string.Equals(a, b, StringComparison.OrdinalIgnoreCase); }
        internal static bool Elevated {
            get { using (var id = WindowsIdentity.GetCurrent())
                return new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator); }
        }
        internal static string ScopeName(RegistryHive scope) { return scope == RegistryHive.LocalMachine ? "整台电脑" : "当前用户"; }

        static string Read(RegistryKey root, string key, string name) {
            using (var k = root.OpenSubKey(key)) return k == null ? "" : Convert.ToString(k.GetValue(name));
        }
        static void Put(RegistryKey root, string key, string name, object value) {
            using (var k = root.CreateSubKey(key)) k.SetValue(name, value);
        }
        static void WriteAssembly(RegistryKey key, string type, AssemblyName assembly) {
            key.SetValue("Class", type);
            key.SetValue("Assembly", assembly.FullName);
            key.SetValue("RuntimeVersion", "v4.0.30319");
            key.SetValue("CodeBase", assembly.CodeBase);
        }
        static void RegisterClass(RegistryKey root, string id, string prog, string type, AssemblyName assembly) {
            string cls = Classes + @"CLSID\" + id;
            Put(root, cls, null, type);
            Put(root, cls + @"\ProgId", null, prog);
            Put(root, Classes + prog + @"\CLSID", null, id);
            using (var server = root.CreateSubKey(Server(id))) {
                server.SetValue(null, "mscoree.dll");
                server.SetValue("ThreadingModel", "Both");
                WriteAssembly(server, type, assembly);
                string version = assembly.Version.ToString();
                using (var entry = server.CreateSubKey(version)) WriteAssembly(entry, type, assembly);
                // The CLR prefers versioned entries, even when the top-level CodeBase is correct.
                foreach (string name in server.GetSubKeyNames()) {
                    Version old;
                    if (name != version && Version.TryParse(name, out old) && Same(Read(server, name, "Class"), type))
                        server.DeleteSubKeyTree(name);
                }
            }
        }
        static void Install(RegistryKey root, AssemblyName assembly) {
            RegisterClass(root, Id, Prog, Connect, assembly);
            RegisterClass(root, PaneId, PaneProg, PaneProg, assembly);
            Put(root, Classes + @"CLSID\" + PaneId + @"\Control", null, "");
            Put(root, Protocol, null, "URL:MailPilot");
            Put(root, Protocol, "URL Protocol", "");
            Put(root, ProtocolCommand, null, Command);
            using (var key = root.CreateSubKey(Addins)) {
                key.SetValue("FriendlyName", "MailPilot");
                key.SetValue("Description", "正则邮件查找与只读 AI 助手");
                key.SetValue("LoadBehavior", 3, RegistryValueKind.DWord);
            }
        }
        static void CheckClass(RegistryKey root, string id, string prog, string type) {
            var cls = Read(root, Server(id), "Class");
            var target = Read(root, Classes + prog + @"\CLSID", null);
            var reverse = Read(root, Classes + @"CLSID\" + id + @"\ProgId", null);
            if ((cls.Length != 0 && !Same(cls, type)) || (target.Length != 0 && !Same(target, id)) ||
                (reverse.Length != 0 && !Same(reverse, prog)))
                throw new InvalidOperationException(prog + " 的注册项属于其他组件，无法替换。");
        }
        static bool OwnsProtocol(RegistryKey root, string registeredDll) {
            string cmd = Read(root, ProtocolCommand, null);
            const string suffix = "\" \"%1\"";
            if (!cmd.StartsWith("\"") || !cmd.EndsWith(suffix, StringComparison.Ordinal) || cmd.Length <= suffix.Length + 1)
                return false;
            string exe = cmd.Substring(1, cmd.Length - suffix.Length - 1);
            return Path.IsPathRooted(exe) && Same(Path.GetFileName(exe), "MailPilot.exe")
                && Same(CodeBase(Path.Combine(Path.GetDirectoryName(exe), "MailPilot.Outlook.dll")), registeredDll);
        }

        internal static void Change(RegistryHive scope, bool enable) {
            if (scope == RegistryHive.LocalMachine && !Elevated)
                throw new InvalidOperationException("整台电脑注册需要管理员权限。请右键 MailPilot.exe，选择“以管理员身份运行”，再选择“整台电脑”。");
            using (var mutex = new Mutex(false, @"Global\MailPilot.Deployment")) {
                try { if (!mutex.WaitOne(0)) throw new InvalidOperationException("另一窗口正在更改 MailPilot 注册，请稍后再试。"); }
                catch (AbandonedMutexException) { }
                try { Apply(scope, enable, RegistryKey.OpenBaseKey); }
                finally { mutex.ReleaseMutex(); }
            }
        }
        internal static void Apply(RegistryHive scope, bool enable, Func<RegistryHive, RegistryView, RegistryKey> open) {
            var assembly = enable ? AssemblyName.GetAssemblyName(Dll) : null;
            var targets = new List<RegistrationChange>();
            try {
                if (!enable) {
                    // An old copy must also preserve the ProgIDs shared with a different active view.
                    foreach (var view in Views) using (var root = open(scope, view)) {
                        string owner = Read(root, Server(Id), "CodeBase");
                        if (owner.Length != 0 && !Same(owner, CodeBase(Dll))) return;
                    }
                }
                // Snapshot both views first. ProgIDs and some Office keys are shared between views.
                foreach (var view in Views) {
                    Plan(targets, open(scope, view), assembly, false);
                    if (enable && scope == RegistryHive.LocalMachine)
                        Plan(targets, open(RegistryHive.CurrentUser, view), null, true);
                }
                try {
                    foreach (var target in targets) if (target.Assembly != null) target.Apply();
                    foreach (var target in targets) if (target.Assembly == null) target.Apply();
                } catch (Exception error) {
                    var errors = new List<Exception>{error};
                    for (int i = targets.Count - 1; i >= 0; i--) targets[i].Restore(errors);
                    if (errors.Count > 1) throw new AggregateException("注册出错，恢复旧注册时也遇到了错误。", errors);
                    throw;
                }
            } finally { foreach (var target in targets) target.Root.Dispose(); }
        }
        static void Plan(List<RegistrationChange> targets, RegistryKey root, AssemblyName assembly, bool migrateUser) {
            try {
                var registered = Read(root, Server(Id), "CodeBase");
                if (assembly == null && !migrateUser && !Same(registered, CodeBase(Dll))) return;
                CheckClass(root, Id, Prog, Connect);
                CheckClass(root, PaneId, PaneProg, PaneProg);
                string handler = Read(root, ProtocolCommand, null);
                if (assembly != null && handler.Length != 0 && !Same(handler, Command) && !OwnsProtocol(root, registered))
                    throw new InvalidOperationException("mailpilot 链接已绑定到其他程序，请检查原有注册。");
                var keys = new List<string>(RegistrationKeys);
                if (assembly == null) {
                    if (!Same(handler, Command) && !OwnsProtocol(root, registered)) keys.Remove(Protocol);
                    keys.RemoveAll(path => { using (var key = root.OpenSubKey(path)) return key == null; });
                    if (keys.Count == 0) return;
                }
                targets.Add(new RegistrationChange(root, keys, assembly));
                root = null;
            } finally { if (root != null) root.Dispose(); }
        }
        sealed class RegistrationChange {
            internal readonly RegistryKey Root;
            internal readonly AssemblyName Assembly;
            readonly Dictionary<string, RegistrySnapshot> before = new Dictionary<string, RegistrySnapshot>();
            bool started;
            internal RegistrationChange(RegistryKey root, List<string> keys, AssemblyName assembly) {
                Root = root; Assembly = assembly;
                foreach (var path in keys) using (var k = root.OpenSubKey(path))
                    before.Add(path, k == null ? null : new RegistrySnapshot(k));
            }
            internal void Apply() {
                started = true;
                if (Assembly != null) Install(Root, Assembly);
                else foreach (var path in before.Keys) Root.DeleteSubKeyTree(path, false);
            }
            internal void Restore(List<Exception> errors) {
                if (!started) return;
                foreach (var entry in before) {
                    try {
                        using (var k = Root.OpenSubKey(entry.Key))
                            if (k == null ? entry.Value == null : entry.Value != null && entry.Value.Matches(k)) continue;
                        Root.DeleteSubKeyTree(entry.Key, false);
                        if (entry.Value != null) using (var k = Root.CreateSubKey(entry.Key)) entry.Value.Write(k);
                    } catch (Exception error) { errors.Add(error); }
                }
            }
        }
        sealed class RegistrySnapshot {
            readonly Dictionary<string, Tuple<object, RegistryValueKind>> values = new Dictionary<string, Tuple<object, RegistryValueKind>>();
            readonly Dictionary<string, RegistrySnapshot> children = new Dictionary<string, RegistrySnapshot>();
            internal RegistrySnapshot(RegistryKey key) {
                foreach (var name in key.GetValueNames()) values.Add(name, Tuple.Create(
                    key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames), key.GetValueKind(name)));
                foreach (var name in key.GetSubKeyNames()) using (var child = key.OpenSubKey(name)) children.Add(name, new RegistrySnapshot(child));
            }
            internal bool Matches(RegistryKey key) {
                if (key.ValueCount != values.Count || key.SubKeyCount != children.Count) return false;
                foreach (var name in key.GetValueNames()) {
                    Tuple<object, RegistryValueKind> value;
                    if (!values.TryGetValue(name, out value) || key.GetValueKind(name) != value.Item2 ||
                        !StructuralComparisons.StructuralEqualityComparer.Equals(value.Item1,
                            key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames))) return false;
                }
                foreach (var pair in children) using (var child = key.OpenSubKey(pair.Key))
                    if (child == null || !pair.Value.Matches(child)) return false;
                return true;
            }
            internal void Write(RegistryKey key) {
                foreach (var pair in values) key.SetValue(pair.Key, pair.Value.Item1, pair.Value.Item2);
                foreach (var pair in children) using (var child = key.CreateSubKey(pair.Key)) pair.Value.Write(child);
            }
        }

        internal static RegistryHive PreferredScope() {
            foreach (var scope in new[]{RegistryHive.CurrentUser, RegistryHive.LocalMachine})
                foreach (var view in Views) using (var root = RegistryKey.OpenBaseKey(scope, view))
                    if (Read(root, Server(Id), "CodeBase") != "") return scope;
            return RegistryHive.CurrentUser;
        }
        internal static string Status(RegistryHive scope) {
            var lines = new StringBuilder();
            foreach (var view in Views) using (var root = RegistryKey.OpenBaseKey(scope, view)) {
                var uri = Read(root, Server(Id), "CodeBase");
                var behavior = Read(root, Addins, "LoadBehavior");
                lines.Append(view == RegistryView.Registry64 ? "64 位" : "32 位").Append(" · ");
                if (uri.Length == 0 && behavior.Length == 0) lines.Append("尚未注册");
                else {
                    lines.Append(uri.Length == 0 ? "缺少 COM 类" : Same(uri, CodeBase(Dll)) ? "已注册此目录" : "已注册其他目录 " + uri);
                    lines.Append(" · 启动设置 LoadBehavior=").Append(behavior.Length == 0 ? "缺失" : behavior);
                }
                lines.AppendLine();
            }
            return lines.ToString().TrimEnd();
        }
    }
}
