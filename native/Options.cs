using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace MailPilot {
    internal sealed class Options : Form {
        readonly Config cfg=Config.Load();
        readonly Dictionary<string,Control> fields=new Dictionary<string,Control>();
        readonly TabControl tabs=new TabControl(){Dock=DockStyle.Fill};
        TableLayoutPanel grid;
        public Options() {
            Text="MailPilot · 设置";Font=new Font("Microsoft YaHei UI",9F);
            StartPosition=FormStartPosition.CenterParent;ClientSize=new Size(620,410);MinimumSize=new Size(540,400);
            Page("查找");
            Choice("mode","默认查找范围",App.Labels,Array.IndexOf(App.Modes,cfg.mode));
            Check("caseSensitive","区分大小写",cfg.caseSensitive);
            Number("limit","每页结果数",cfg.limit,1,1000);
            Number("debounceMs","停止输入后查找（毫秒）",cfg.debounceMs,100,2000);
            Number("timeoutMs","单字段匹配时限（毫秒）",cfg.timeoutMs,5,500);
            Page("索引与资源");
            Folder("indexDir","本地索引目录",cfg.indexDir);
            Choice("storeScope","经典 Outlook 索引范围",new[]{"默认邮箱","所有已打开的邮箱和 PST"},cfg.storeScope=="all"?1:0);
            Check("autoRefresh","打开查找或助手时按需刷新",cfg.autoRefresh);
            Number("refreshMinutes","索引刷新间隔（分钟）",cfg.refreshMinutes,1,1440);
            Number("cacheMiB","每个索引连接缓存（MiB）",cfg.cacheMiB,1,64);
            Number("batchSize","每批读取封数",cfg.batchSize,8,256);
            Number("pauseMs","批次间休息（毫秒）",cfg.pauseMs,0,1000);
            Note("切换目录后会使用该目录中的索引。选择空目录会重新建索引，原索引保留。");
            Page("AI 与邮箱");
            Folder("chatDir","Chatbox 数据目录",cfg.chatDir);
            Choice("source","独立启动时使用",new[]{"经典 Outlook","新版 Outlook · Microsoft Graph"},cfg.source=="graph"?1:0);
            var id=new TextBox(){Text=cfg.clientId,Dock=DockStyle.Fill}; Add("clientId","Microsoft 应用（客户端）ID",id);
            var login=App.Button("连接 Microsoft 邮箱",(s,e)=>ConnectMailbox());
            Add("login","新版 Outlook",login);
            Note("Microsoft 365 或 Outlook.com 使用已启用公共客户端流的应用 ID，并授予委托的 Mail.Read。模型、API 密钥及对话参数在 Chatbox 设置中配置。");
            var actions=new FlowLayoutPanel(){Dock=DockStyle.Bottom,Height=46,FlowDirection=FlowDirection.RightToLeft,Padding=new Padding(4)};
            actions.Controls.Add(App.Button("保存",(s,e)=>{try{SaveSettings();DialogResult=DialogResult.OK;Close();}catch(Exception ex){App.Error(ex);}}));
            actions.Controls.Add(App.Button("取消",(s,e)=>Close()));
            Controls.Add(tabs); Controls.Add(actions);
        }
        void Page(string title) {
            var page=new TabPage(title){Padding=new Padding(10),AutoScroll=true}; tabs.TabPages.Add(page);
            grid=new TableLayoutPanel(){Dock=DockStyle.Top,AutoSize=true,ColumnCount=2,Padding=new Padding(3),GrowStyle=TableLayoutPanelGrowStyle.AddRows};
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,178));grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));page.Controls.Add(grid);
        }
        void Add(string key,string label,Control control) {
            int r=grid.RowCount++; grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            grid.Controls.Add(new Label(){Text=label,AutoSize=true,Anchor=AnchorStyles.Left,Margin=new Padding(3,9,3,9)},0,r);
            control.Anchor=AnchorStyles.Left|AnchorStyles.Right;grid.Controls.Add(control,1,r);fields[key]=control;
        }
        void Note(string text) {
            int r=grid.RowCount++;var l=new Label(){Text=text,AutoSize=true,MaximumSize=new Size(550,0),ForeColor=SystemColors.GrayText,Margin=new Padding(3,12,3,3)};
            grid.Controls.Add(l,0,r);grid.SetColumnSpan(l,2);
        }
        void Number(string key,string label,int val,int min,int max) {
            Add(key,label,new NumericUpDown(){Minimum=min,Maximum=max,Value=Math.Max(min,Math.Min(max,val))});
        }
        void Check(string key,string label,bool value){Add(key,label,new CheckBox(){Checked=value,AutoSize=true});}
        void Choice(string key,string label,string[] values,int selected) {
            var c=new ComboBox(){DropDownStyle=ComboBoxStyle.DropDownList}; c.Items.AddRange(values);c.SelectedIndex=Math.Max(0,selected);Add(key,label,c);
        }
        void Folder(string key,string label,string value) {
            var panel=new TableLayoutPanel(){ColumnCount=2,AutoSize=true,Dock=DockStyle.Fill,Margin=Padding.Empty};
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));panel.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            var box=new TextBox(){Text=value,Dock=DockStyle.Fill,Anchor=AnchorStyles.Left|AnchorStyles.Right};
            var button=App.Button("浏览",(s,e)=>{using(var d=new FolderBrowserDialog(){SelectedPath=box.Text}){if(d.ShowDialog(this)==DialogResult.OK)box.Text=d.SelectedPath;}});
            panel.Controls.Add(box,0,0);panel.Controls.Add(button,1,0);Add(key,label,panel);fields[key]=box;
        }
        int N(string key){return (int)((NumericUpDown)fields[key]).Value;}
        int C(string key){return ((ComboBox)fields[key]).SelectedIndex;}
        string Dir(string key){
            string p=Environment.ExpandEnvironmentVariables(fields[key].Text.Trim());
            if(!Path.IsPathRooted(p)||p.StartsWith(@"\\",StringComparison.Ordinal)) throw new ArgumentException("请选择本地磁盘上的绝对目录。");
            p=Path.GetFullPath(p); Directory.CreateDirectory(p);return p;
        }
        void SaveSettings() {
            cfg.indexDir=Dir("indexDir");cfg.chatDir=Dir("chatDir");cfg.mode=App.Modes[C("mode")];
            cfg.caseSensitive=((CheckBox)fields["caseSensitive"]).Checked;cfg.autoRefresh=((CheckBox)fields["autoRefresh"]).Checked;
            cfg.limit=N("limit");cfg.debounceMs=N("debounceMs");cfg.timeoutMs=N("timeoutMs");cfg.cacheMiB=N("cacheMiB");
            cfg.refreshMinutes=N("refreshMinutes");cfg.pauseMs=N("pauseMs");cfg.batchSize=N("batchSize");cfg.storeScope=C("storeScope")==0?"default":"all";
            cfg.source=C("source")==0?"classic":"graph";cfg.clientId=fields["clientId"].Text.Trim();
            Guid id;if(cfg.clientId!="" && !Guid.TryParse(cfg.clientId,out id)) throw new ArgumentException("Microsoft 应用 ID 格式不正确。");
            if(cfg.clientId!="") cfg.clientId=new Guid(cfg.clientId).ToString();cfg.Save();
        }
        void ConnectMailbox(){
            try{SaveSettings();if(cfg.clientId=="") throw new ArgumentException("请先填写 Microsoft 应用 ID。");Process.Start(App.Python("login"));}
            catch(Exception ex){App.Error(ex);}
        }
    }
}
