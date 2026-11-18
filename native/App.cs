using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyFileVersion("0.2.0.0")]
namespace MailPilot {
    internal static class App {
        public static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
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
                    case "enable": Deployment.Enable(); return 0;
                    case "disable": Deployment.Disable(); return 0;
                    case "ai": case "search": case "settings": Launch(a); return 0;
                    case "manager": Application.Run(new Manager()); return 0;
                    default: return 2;
                }
            } catch(Exception e){Error(e);return 1;}
        }
    }
    internal sealed class Manager : Form {
        readonly Label status=new Label(){Dock=DockStyle.Fill,AutoEllipsis=true};
        public Manager() {
            Text="MailPilot · 部署管理";Font=new Font("Microsoft YaHei UI",9F);StartPosition=FormStartPosition.CenterScreen;
            Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            ClientSize=new Size(610,260); MinimumSize=new Size(530,280);Padding=new Padding(18);
            var layout=new TableLayoutPanel(){Dock=DockStyle.Fill,RowCount=5,ColumnCount=1};
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,44));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,32));
            layout.Controls.Add(new Label(){Text="MailPilot",Font=new Font(Font.FontFamily,18F,FontStyle.Bold),AutoSize=true},0,0);
            layout.Controls.Add(status,0,1);
            var row=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};
            row.Controls.Add(App.Button("启用此目录",(s,e)=>Run(Deployment.Enable)));
            row.Controls.Add(App.Button("停用此目录",(s,e)=>Run(Deployment.Disable)));
            row.Controls.Add(App.Button("打开 Outlook",(s,e)=>Run(()=>Process.Start("outlook.exe"))));
            layout.Controls.Add(row,0,2);
            var tools=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};
            tools.Controls.Add(App.Button("正则查找",(s,e)=>Run(()=>App.Launch("search"))));
            tools.Controls.Add(App.Button("AI 助手",(s,e)=>Run(()=>App.Launch("ai"))));
            tools.Controls.Add(App.Button("设置",(s,e)=>Run(()=>App.Launch("settings"))));
            layout.Controls.Add(tools,0,3);
            layout.Controls.Add(new Label(){Text="启用或停用后，重新打开经典 Outlook 以应用更改。",Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft},0,4);
            Controls.Add(layout);status.Text=Deployment.Status();
        }
        void Run(Action a){try{a();status.Text=Deployment.Status();}catch(Exception e){App.Error(e);}}
    }
}
