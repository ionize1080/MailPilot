using System;
using System.IO;
using Microsoft.Win32;

namespace MailPilot {
    // Exercise the production registration code with both hives redirected into disposable test keys.
    internal static class App { internal static string Root; }
    internal static class ScopeTests {
        const string Addin = @"Software\Microsoft\Office\Outlook\Addins\MailPilot.Outlook";
        const string Server = @"Software\Classes\CLSID\{85C590EA-8141-4C33-99A0-F304FFA27D7E}\InprocServer32";
        const string Pane = @"Software\Classes\CLSID\{3AD910BB-5093-45FA-AB6E-68094BC37F22}\InprocServer32";
        const string Link = @"Software\Classes\mailpilot\shell\open\command";
        static readonly string TestKey = @"Software\MailPilot-qa-" + Guid.NewGuid().ToString("N");
        static RegistryKey Open(RegistryHive hive, RegistryView view) {
            return Registry.CurrentUser.CreateSubKey(TestKey + "\\" + hive + "\\" + view);
        }
        static void Check(bool ok, string message) { if (!ok) throw new Exception(message); }
        static object Read(RegistryKey root, string path, string name) {
            using (var k = root.OpenSubKey(path)) return k == null ? null : k.GetValue(name);
        }
        static void Put(RegistryKey root, string path, string name, object value) {
            using (var k = root.CreateSubKey(path)) k.SetValue(name, value);
        }
        static void Change(RegistryHive hive, bool enable) { Deployment.Apply(hive, enable, Open); }
        static void Main(string[] args) {
            var user = RegistryHive.CurrentUser;
            var machine = RegistryHive.LocalMachine;
            var sentinels = new[]{@"Software\Microsoft\Office\Word\Addins\PagePilot.Connect",
                @"Software\Microsoft\Office\Excel\Addins\Existing.Excel", @"Software\Microsoft\Office\Outlook\Addins\Other.Addin"};
            try {
                foreach (var hive in new[]{user,machine}) foreach (var view in Deployment.Views)
                    using (var root = Open(hive,view)) foreach (var key in sentinels) Put(root,key,"LoadBehavior",2);
                App.Root = args[0];
                Change(user, true);
                App.Root = args[1];
                foreach (var view in Deployment.Views) using (var root = Open(machine,view)) {
                    Put(root, Server + @"\9.9.9.9", "Class", "MailPilot.Connect");
                    Put(root, Server + @"\9.9.9.9", "CodeBase", "file:///old/MailPilot.Outlook.dll");
                }
                if (Deployment.Views.Length == 2) {
                    bool rejected = false;
                    try {
                        Deployment.Apply(machine, true, (h,v) => h == machine && v == RegistryView.Registry32
                            ? Registry.CurrentUser.OpenSubKey(TestKey + "\\" + h + "\\" + v, false) : Open(h,v));
                    } catch (UnauthorizedAccessException) { rejected = true; }
                    Check(rejected, "Expected a write failure in the second machine view");
                    foreach (var view in Deployment.Views) using (var root=Open(machine,view)) {
                        Check(Read(root, Addin, "LoadBehavior") == null, "Partial machine install after failure");
                        Check((string)Read(root, Server + @"\9.9.9.9", "CodeBase") == "file:///old/MailPilot.Outlook.dll", "Lost previous record on rollback");
                    }
                    foreach (var view in Deployment.Views) using (var root=Open(user,view))
                        Check((int)Read(root, Addin, "LoadBehavior") == 3, "User registration removed before successful machine install");
                }
                Change(machine, true);
                foreach (var view in Deployment.Views) using (var root=Open(user,view)) Put(root,Addin,"LoadBehavior",2);
                Change(machine, true);
                foreach (var view in Deployment.Views) {
                    using (var root=Open(machine,view)) {
                        Check((int)Read(root, Addin, "LoadBehavior") == 3, "Machine startup flag");
                        foreach (var s in new[]{Server, Pane}) {
                            var code = (string)Read(root,s,"CodeBase");
                            Check(new Uri(code).LocalPath == Path.Combine(args[1],"MailPilot.Outlook.dll"), "Machine DLL path");
                            Check((string)Read(root,s + @"\0.1.0.0","CodeBase") == code, "Version-specific DLL path");
                        }
                        Check(Read(root,Server + @"\9.9.9.9","CodeBase") == null, "Stale CLR version overrides active DLL");
                    }
                    using (var root=Open(user,view))
                        Check(Read(root,Addin,"LoadBehavior")==null && Read(root,Server,"CodeBase")==null &&
                              Read(root,Pane,"CodeBase")==null && Read(root,Link,null)==null, "User copy still shadows machine");
                }
                App.Root = args[0];
                Change(machine,false);
                foreach (var view in Deployment.Views) using (var root=Open(machine,view))
                    Check((int)Read(root,Addin,"LoadBehavior")==3,"Old directory disabled machine copy");
                App.Root = args[1];
                Change(machine,false);
                foreach (var view in Deployment.Views) using (var root=Open(machine,view))
                    Check(Read(root,Addin,"LoadBehavior")==null && Read(root,Server,"CodeBase")==null &&
                          Read(root,Pane,"CodeBase")==null && Read(root,Link,null)==null, "Machine disable");
                foreach (var hive in new[]{user,machine}) foreach (var view in Deployment.Views)
                    using (var root=Open(hive,view)) foreach (var key in sentinels)
                        Check((int)Read(root,key,"LoadBehavior")==2, "Unrelated Office add-in changed");
                Console.WriteLine("PASS isolated machine migration, rollback, ownership, disable and Word/Excel/Outlook isolation");
            } finally { Registry.CurrentUser.DeleteSubKeyTree(TestKey,false); }
        }
    }
}
