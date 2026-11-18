using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyFileVersion("0.2.1.0")]
namespace MailPilot {
    internal static class App {
        public static readonly string Root=Path.GetDirectoryName(typeof(App).Assembly.Location);
        public static Button Button(string text, EventHandler click) {
            var b=new Button(){Text=text,AutoSize=true,Height=32,MinimumSize=new Size(68,30),Margin=new Padding(3)};
            b.Click+=click;return b;
        }
        public static void Error(Exception e){MessageBox.Show(e.GetBaseException().Message,"MailPilot",MessageBoxButtons.OK,MessageBoxIcon.Warning);}
        public static void Launch(string action) {
            var desktop=Path.Combine(Root,"Desktop");
            var ps=new ProcessStartInfo(Path.Combine(Root,@"Browser\electron.exe"),"\""+desktop+"\" "+action)
                {UseShellExecute=false,WorkingDirectory=Root};
            Process.Start(ps);
        }
        [STAThread] static int Main(string[] args) {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            try {
                string a=args.Length==0?"manager":args[0];
                if(a.StartsWith("mailpilot:",StringComparison.OrdinalIgnoreCase)){
                    Uri uri=new Uri(a);
                    if(uri.Scheme!="mailpilot" || (uri.Host!="search" && uri.Host!="ai" && uri.Host!="settings") ||
                        uri.Query!="" || uri.Fragment!="" || uri.AbsolutePath.Trim('/')!="" || uri.UserInfo!="") return 2;
                    a="graph-"+uri.Host;
                }
                if(a.StartsWith("classic-") || a.StartsWith("graph-")) {
                    var pair=a.Split(new[]{'-'},2); Environment.SetEnvironmentVariable("MAILPILOT_SOURCE",pair[0]); a=pair[1];
                }
                switch(a) {
                    case "enable": case "disable":
                        var scope=RegistryHive.CurrentUser;
                        if(args.Length==3 && args[1]=="--scope" && args[2]=="machine") scope=RegistryHive.LocalMachine;
                        else if(args.Length!=1 && !(args.Length==3 && args[1]=="--scope" && args[2]=="user")) return 2;
                        Deployment.Change(scope,a=="enable"); return 0;
                    case "diagnose":
                        if(args.Length!=2) return 2;
                        File.WriteAllText(args[1], OutlookDiagnostics.Report()); return 0;
                    case "ai": case "search": case "settings": Launch(a); return 0;
                    case "manager": Application.Run(new Manager()); return 0;
                    default: return 2;
                }
            } catch(Exception e){Error(e);return 1;}
        }
    }
    internal sealed class Manager : Form {
        readonly Label status=new Label(){Dock=DockStyle.Fill,AutoEllipsis=true};
        readonly ComboBox scope=new ComboBox(){DropDownStyle=ComboBoxStyle.DropDownList,Width=210};
        readonly Label hint=new Label(){Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft};
        RegistryHive Scope { get { return scope.SelectedIndex==1 ? RegistryHive.LocalMachine : RegistryHive.CurrentUser; } }
        public Manager() {
            Text="MailPilot · 部署管理";Font=new Font("Microsoft YaHei UI",9F);StartPosition=FormStartPosition.CenterScreen;
            Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            ClientSize=new Size(630,320); MinimumSize=new Size(600,355);Padding=new Padding(18);
            var layout=new TableLayoutPanel(){Dock=DockStyle.Fill,RowCount=6,ColumnCount=1};
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,46));
            layout.Controls.Add(new Label(){Text="MailPilot",Font=new Font(Font.FontFamily,18F,FontStyle.Bold),AutoSize=true},0,0);
            var selector=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};
            selector.Controls.Add(new Label(){Text="部署范围",AutoSize=true,Margin=new Padding(3,7,6,3)});
            scope.Items.AddRange(new[]{"当前用户","整台电脑（需管理员权限）"});
            scope.SelectedIndex=Deployment.PreferredScope()==RegistryHive.LocalMachine ? 1 : 0;
            scope.SelectedIndexChanged+=(s,e)=>RefreshStatus();
            selector.Controls.Add(scope);layout.Controls.Add(selector,0,1);
            layout.Controls.Add(status,0,2);
            var row=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};
            row.Controls.Add(App.Button("启用此目录",(s,e)=>Run(()=>Deployment.Change(Scope,true))));
            row.Controls.Add(App.Button("停用此目录",(s,e)=>Run(()=>Deployment.Change(Scope,false))));
            row.Controls.Add(App.Button("打开 Outlook",(s,e)=>Run(()=>Process.Start("outlook.exe"))));
            row.Controls.Add(App.Button("检查实际加载",(s,e)=>Run(ShowDiagnostics)));
            layout.Controls.Add(row,0,3);
            var tools=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};
            tools.Controls.Add(App.Button("正则查找",(s,e)=>Run(()=>App.Launch("search"))));
            tools.Controls.Add(App.Button("AI 助手",(s,e)=>Run(()=>App.Launch("ai"))));
            tools.Controls.Add(App.Button("设置",(s,e)=>Run(()=>App.Launch("settings"))));
            layout.Controls.Add(tools,0,4);
            layout.Controls.Add(hint,0,5);
            Controls.Add(layout);RefreshStatus();
        }
        void RefreshStatus() {
            status.Text=Deployment.Status(Scope);
            hint.Text=Scope==RegistryHive.LocalMachine
                ? "整机启用会接替本账户的 MailPilot 注册。请选择由管理员维护的程序目录。"
                : "启用后重新打开经典 Outlook，再点“检查实际加载”。";
        }
        void ShowDiagnostics() {
            using (var dialog=new Form(){Text="MailPilot · Outlook 加载检查",Font=Font,ClientSize=new Size(680,370),
                    MinimizeBox=false,StartPosition=FormStartPosition.CenterParent,Padding=new Padding(12)}) {
                var report=new TextBox(){Multiline=true,ReadOnly=true,Dock=DockStyle.Fill,ScrollBars=ScrollBars.Vertical,
                    Text=OutlookDiagnostics.Report()};
                var copy=App.Button("复制检查结果",(s,e)=>Clipboard.SetText(report.Text));
                var buttons=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Bottom,FlowDirection=FlowDirection.RightToLeft};
                buttons.Controls.Add(copy);dialog.Controls.Add(report);dialog.Controls.Add(buttons);
                dialog.ShowDialog(this);
            }
        }
        void Run(Action a){try{a();RefreshStatus();}catch(Exception e){App.Error(e);}}
    }
}
