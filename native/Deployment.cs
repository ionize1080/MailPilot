using System;
using System.IO;
using System.Reflection;
using Microsoft.Win32;

namespace MailPilot {
    internal static class Deployment {
        const string Id="{85C590EA-8141-4C33-99A0-F304FFA27D7E}", Prog="MailPilot.Outlook";
        const string Classes=@"Software\Classes\", Addins=@"Software\Microsoft\Office\Outlook\Addins\MailPilot.Outlook";
        static RegistryView[] Views { get { return Environment.Is64BitOperatingSystem ?
            new[]{RegistryView.Registry64,RegistryView.Registry32}:new[]{RegistryView.Registry32}; } }
        static string Dll {get {return Path.Combine(App.Root,"MailPilot.Outlook.dll");}}
        static string CodeBase {get {return AssemblyName.GetAssemblyName(Dll).CodeBase;}}
        static string Command {get {return "\""+Path.Combine(App.Root,"MailPilot.exe")+"\" \"%1\"";}}
        static void Put(RegistryKey root,string key,string name,object value) {
            using(var k=root.CreateSubKey(key)) k.SetValue(name,value);
        }
        public static void Enable() {
            string assembly=AssemblyName.GetAssemblyName(Dll).FullName;
            foreach(var view in Views) using(var r=RegistryKey.OpenBaseKey(RegistryHive.CurrentUser,view)) {
                string cls=Classes+@"CLSID\"+Id, server=cls+@"\InprocServer32";
                Put(r,cls,null,"MailPilot.Connect"); Put(r,cls+@"\ProgId",null,Prog);
                Put(r,Classes+Prog+@"\CLSID",null,Id);
                Put(r,server,null,"mscoree.dll"); Put(r,server,"ThreadingModel","Both");
                Put(r,server,"Class","MailPilot.Connect"); Put(r,server,"Assembly",assembly);
                Put(r,server,"RuntimeVersion","v4.0.30319"); Put(r,server,"CodeBase",CodeBase);
                Put(r,Addins,"FriendlyName","MailPilot"); Put(r,Addins,"Description","正则邮件查找与只读 AI 助手");
                Put(r,Addins,"LoadBehavior",3);
                Put(r,Classes+"mailpilot",null,"URL:MailPilot"); Put(r,Classes+"mailpilot","URL Protocol","");
                Put(r,Classes+@"mailpilot\shell\open\command",null,Command);
            }
        }
        static string Read(RegistryKey r,string path,string name) {
            using(var k=r.OpenSubKey(path)) return k==null ? "" : Convert.ToString(k.GetValue(name));
        }
        public static void Disable() {
            // HKCU class registrations may be shared between views. Snapshot ownership before deleting.
            var owned=new System.Collections.Generic.List<RegistryView>();
            foreach(var v in Views) using(var r=RegistryKey.OpenBaseKey(RegistryHive.CurrentUser,v))
                if(string.Equals(Read(r,Classes+@"CLSID\"+Id+@"\InprocServer32","CodeBase"),CodeBase,StringComparison.OrdinalIgnoreCase)) owned.Add(v);
            foreach(var v in owned) using(var r=RegistryKey.OpenBaseKey(RegistryHive.CurrentUser,v)) {
                r.DeleteSubKeyTree(Addins,false);
                r.DeleteSubKeyTree(Classes+@"CLSID\"+Id,false);
                r.DeleteSubKeyTree(Classes+Prog,false);
                if(string.Equals(Read(r,Classes+@"mailpilot\shell\open\command",null),Command,StringComparison.OrdinalIgnoreCase))
                    r.DeleteSubKeyTree(Classes+"mailpilot",false);
            }
        }
        public static string Status() {
            using(var r=RegistryKey.OpenBaseKey(RegistryHive.CurrentUser,Views[0])) {
                var uri=Read(r,Classes+@"CLSID\"+Id+@"\InprocServer32","CodeBase");
                if(uri=="") return "当前用户尚未启用 MailPilot";
                bool here=string.Equals(uri,CodeBase,StringComparison.OrdinalIgnoreCase);
                return (here ? "已启用此目录" : "已启用另一个目录")+" · Outlook 加载状态 "+Read(r,Addins,"LoadBehavior")+
                       Environment.NewLine+new Uri(uri).LocalPath;
            }
        }
    }
}
