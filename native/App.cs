using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace MailPilot {
    internal class Config {
        public string indexDir {get;set;} public string chatDir {get;set;} public string source {get;set;}
        public string mode {get;set;} public bool caseSensitive {get;set;} public int limit {get;set;}
        public int debounceMs {get;set;} public int cacheMiB {get;set;} public int batchSize {get;set;}
        public int pauseMs {get;set;} public int timeoutMs {get;set;} public bool autoRefresh {get;set;}
        public int refreshMinutes {get;set;} public string storeScope {get;set;} public string clientId {get;set;}
        public Config() {
            indexDir=Path.Combine(App.Home,"Index");chatDir=Path.Combine(App.Home,"Chatbox");source="classic";mode="subject";
            limit=100;debounceMs=280;cacheMiB=8;batchSize=64;pauseMs=25;timeoutMs=60;autoRefresh=true;refreshMinutes=30;
            storeScope="default";clientId="";
        }
        public static Config Load() {
            string path=Path.Combine(App.Home,"settings.json");
            return File.Exists(path)?App.Json().Deserialize<Config>(File.ReadAllText(path)):new Config();
        }
        public void Save() {
            Directory.CreateDirectory(App.Home);
            string path=Path.Combine(App.Home,"settings.json"), tmp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            File.WriteAllText(tmp,App.Json().Serialize(this),new System.Text.UTF8Encoding(false));
            if(File.Exists(path)) File.Replace(tmp,path,null); else File.Move(tmp,path);
        }
    }
    internal static class App {
        public static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
        public static readonly string Home=Environment.GetEnvironmentVariable("MAILPILOT_HOME")??
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MailPilot");
        public static JavaScriptSerializer Json(){return new JavaScriptSerializer(){MaxJsonLength=16777216};}
        public static readonly string[] Modes={"subject","subject_body","all","attachment"};
        public static readonly string[] Labels={"仅标题","标题 + 正文","标题 + 正文 + 附件名","仅附件名"};
        public static Button Button(string text, EventHandler click) {
            var b=new Button(){Text=text,AutoSize=true,Height=32,MinimumSize=new Size(68,30),Margin=new Padding(3)};
            b.Click+=click;return b;
        }
        public static void Error(Exception e){MessageBox.Show(e.GetBaseException().Message,"MailPilot",MessageBoxButtons.OK,MessageBoxIcon.Warning);}
        public static ProcessStartInfo Python(string mode) {
            return new ProcessStartInfo(Path.Combine(Root,@"Runtime\python.exe"),"-B \""+Path.Combine(Root,@"engine\service.py")+"\" --"+mode)
                      {UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Root};
        }
        public static void AI() {
            var cfg=Config.Load(); string source=Environment.GetEnvironmentVariable("MAILPILOT_SOURCE")??cfg.source;
            if(source=="graph" && !File.Exists(Path.Combine(Home,"graph-account.json"))) throw new InvalidOperationException("请先在设置中连接 Microsoft 邮箱。");
            var ps=new ProcessStartInfo(Path.Combine(Root,@"Browser\electron.exe"),"\""+Path.Combine(Root,"Chatbox")+"\"")
                {UseShellExecute=false,WorkingDirectory=Root};
            ps.EnvironmentVariables["MAILPILOT_SOURCE"]=source;
            ps.EnvironmentVariables["MAILPILOT_CHAT_DIR"]=Path.Combine(cfg.chatDir,source);
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
                    case "ai": AI(); return 0;
                    case "search": Application.Run(new SearchForm()); return 0;
                    case "settings": Application.Run(new Options()); return 0;
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
            tools.Controls.Add(App.Button("正则查找",(s,e)=>new SearchForm().Show()));
            tools.Controls.Add(App.Button("AI 助手",(s,e)=>Run(App.AI)));
            tools.Controls.Add(App.Button("设置",(s,e)=>new Options().ShowDialog(this)));
            layout.Controls.Add(tools,0,3);
            layout.Controls.Add(new Label(){Text="启用或停用后，重新打开经典 Outlook 以应用更改。",Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft},0,4);
            Controls.Add(layout);status.Text=Deployment.Status();
        }
        void Run(Action a){try{a();status.Text=Deployment.Status();}catch(Exception e){App.Error(e);}}
    }
}
