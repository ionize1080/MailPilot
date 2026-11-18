using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace MailPilot {
    internal sealed class Worker : IDisposable {
        Process process; int serial; bool disposed;
        readonly Dictionary<int,TaskCompletionSource<object>> pending=new Dictionary<int,TaskCompletionSource<object>>();
        readonly object gate=new object();
        public Worker(){
            var ps=App.Python("ui");ps.RedirectStandardInput=true;ps.RedirectStandardOutput=true;ps.StandardOutputEncoding=Encoding.UTF8;
            process=new Process(){StartInfo=ps,EnableRaisingEvents=true};
            process.OutputDataReceived+=(s,e)=>{if(e.Data==null) return;try{
                var r=App.Json().Deserialize<Dictionary<string,object>>(e.Data); int id=Convert.ToInt32(r["id"]);
                TaskCompletionSource<object> t;
                lock(gate){if(!pending.TryGetValue(id,out t))return;pending.Remove(id);}
                if(r.ContainsKey("error")) t.TrySetException(new Exception(Convert.ToString(r["error"]))); else t.TrySetResult(r["result"]);
            }catch(Exception ex){Fail(ex);}};
            process.Exited+=(s,e)=>Fail(new IOException("邮件查找进程已退出。"));
            process.Start();process.BeginOutputReadLine();
        }
        void Fail(Exception ex){
            lock(gate){foreach(var t in pending.Values)t.TrySetException(ex);pending.Clear();}
        }
        public Task<object> Call(string method,object args){
            var t=new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
            lock(gate){
                if(disposed||process.HasExited) throw new IOException("邮件查找进程已退出。");
                int id=++serial;pending[id]=t;
                var line=App.Json().Serialize(new {id=id,method=method,@params=args});
                // The embedded worker expects UTF-8 regardless of the Windows console codepage.
                byte[] bytes=Encoding.UTF8.GetBytes(line+"\n");
                process.StandardInput.BaseStream.Write(bytes,0,bytes.Length);process.StandardInput.BaseStream.Flush();
            }
            return t.Task;
        }
        public void Dispose(){
            lock(gate){if(disposed)return;disposed=true;}
            try{process.StandardInput.Close();}catch(InvalidOperationException){}
            Fail(new OperationCanceledException());
            var p=process; Task.Run(()=>{try{if(!p.WaitForExit(4000))p.Kill();}catch(InvalidOperationException){}finally{p.Dispose();}});
        }
    }

    internal sealed class SearchForm : Form {
        Config cfg; Worker worker;
        readonly TextBox input=new TextBox(){Dock=DockStyle.Fill,Font=new Font("Microsoft YaHei UI",12)};
        readonly ComboBox mode=new ComboBox(){DropDownStyle=ComboBoxStyle.DropDownList,Width=160};
        readonly ComboBox folder=new ComboBox(){DropDownStyle=ComboBoxStyle.DropDownList,Width=195,DropDownWidth=420};
        readonly CheckBox matchCase=new CheckBox(){Text="区分大小写",AutoSize=true,Anchor=AnchorStyles.Left};
        readonly ListView results=new ListView(){Dock=DockStyle.Fill,View=View.Details,FullRowSelect=true,HideSelection=false};
        readonly Label stats=new Label(){AutoSize=true,Anchor=AnchorStyles.Left};
        readonly Label queryInfo=new Label(){Text="输入正则表达式开始查找",AutoSize=true,Anchor=AnchorStyles.Left};
        readonly Timer debounce=new Timer(), poll=new Timer();
        Button more; object cursor; int generation; bool busyPoll, oldActive, closing;
        public SearchForm(){
            cfg=Config.Load();Text="MailPilot · 正则查找";Font=new Font("Microsoft YaHei UI",9F);StartPosition=FormStartPosition.CenterScreen;
            ClientSize=new Size(900,520);MinimumSize=new Size(710,370);Padding=new Padding(14);
            var layout=new TableLayoutPanel(){Dock=DockStyle.Fill,ColumnCount=1,RowCount=5};
            for(int i=0;i<5;i++)layout.RowStyles.Add(i==2?new RowStyle(SizeType.Percent,100):new RowStyle(SizeType.AutoSize));
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            var top=new TableLayoutPanel(){Dock=DockStyle.Fill,ColumnCount=3,AutoSize=true};top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            top.Controls.Add(input,0,0);top.Controls.Add(App.Button("查找",(s,e)=>Query(false)),1,0);
            top.Controls.Add(App.Button("AI 助手",(s,e)=>{try{App.AI();}catch(Exception ex){App.Error(ex);}}),2,0);layout.Controls.Add(top,0,0);
            var opts=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill,WrapContents=true};
            mode.Items.AddRange(App.Labels);folder.Items.Add("全部已索引文件夹");folder.SelectedIndex=0;
            opts.Controls.Add(mode);opts.Controls.Add(matchCase);opts.Controls.Add(folder);layout.Controls.Add(opts,0,1);
            foreach(var c in new[]{"标题","命中位置","匹配片段","发件人","收件时间 (UTC)","文件夹"})results.Columns.Add(c);
            int[] widths={210,76,230,100,145,170};for(int i=0;i<widths.Length;i++) results.Columns[i].Width=widths[i];
            layout.Controls.Add(results,0,2);
            var q=new FlowLayoutPanel(){Dock=DockStyle.Fill,AutoSize=true}; more=App.Button("下一页",(s,e)=>Query(true));more.Enabled=false;
            q.Controls.Add(more);q.Controls.Add(queryInfo);layout.Controls.Add(q,0,3);
            var foot=new FlowLayoutPanel(){Dock=DockStyle.Fill,AutoSize=true};
            foot.Controls.Add(App.Button("刷新索引",async (s,e)=>{try{await worker.Call("refresh",new{});poll.Interval=600;await Status();}catch(Exception ex){App.Error(ex);}}));
            foot.Controls.Add(App.Button("暂停索引",async (s,e)=>{try{await worker.Call("pause",new{});}catch(Exception ex){App.Error(ex);}}));
            foot.Controls.Add(App.Button("设置",(s,e)=>{using(var f=new Options()){if(f.ShowDialog(this)==DialogResult.OK)Restart();}}));
            foot.Controls.Add(stats);layout.Controls.Add(foot,0,4);Controls.Add(layout);
            input.AccessibleName="正则表达式";mode.AccessibleName="查找范围";folder.AccessibleName="文件夹";
            input.TextChanged+=(s,e)=>Schedule();mode.SelectedIndexChanged+=(s,e)=>Schedule();matchCase.CheckedChanged+=(s,e)=>Schedule();
            folder.SelectionChangeCommitted+=(s,e)=>Schedule();
            input.KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Enter){e.SuppressKeyPress=true;Query(false);}};
            results.DoubleClick+=(s,e)=>OpenSelected();results.KeyDown+=(s,e)=>{if(e.KeyCode==Keys.Enter)OpenSelected();};
            debounce.Tick+=(s,e)=>Query(false);poll.Tick+=async(s,e)=>await Status();Shown+=(s,e)=>Restart();
            FormClosed+=(s,e)=>{closing=true;++generation;poll.Dispose();debounce.Dispose();if(worker!=null)worker.Dispose();};
        }
        async void Restart(){
            try{
                ++generation;oldActive=false;if(worker!=null) worker.Dispose();cfg=Config.Load();worker=new Worker();
                mode.SelectedIndex=Math.Max(0,Array.IndexOf(App.Modes,cfg.mode));matchCase.Checked=cfg.caseSensitive;
                debounce.Interval=Math.Max(100,cfg.debounceMs);poll.Interval=800;poll.Start();
                await worker.Call("auto",new{});await Status();await Folders();Schedule();input.Focus();
            }catch(Exception ex){if(!closing)stats.Text=ex.GetBaseException().Message;}
        }
        async Task Folders(){
            var list=(IEnumerable)await worker.Call("list_folders",new{});if(closing)return;
            var selected=Convert.ToString(folder.SelectedItem);folder.Items.Clear();folder.Items.Add("全部已索引文件夹");
            foreach(Dictionary<string,object> entry in list)folder.Items.Add(entry["folder"]);
            folder.SelectedIndex=Math.Max(0,folder.Items.IndexOf(selected));
        }
        async Task Status(){
            if(busyPoll||closing||worker==null)return;busyPoll=true;
            try{
                var r=(Dictionary<string,object>)await worker.Call("index_status",new{});if(closing)return;
                var sync=(Dictionary<string,object>)r["sync"];
                bool active=sync.ContainsKey("active") && Convert.ToBoolean(sync["active"]);
                string text="已索引 "+r["count"]+" 封";
                if(active)text+=" · 已检查 "+sync["checked"]+" 封";
                if(sync.ContainsKey("error"))text+=" · "+sync["error"];
                if(sync.ContainsKey("errors") && Convert.ToInt32(sync["errors"])>0)text+=" · "+sync["errors"]+" 封读取失败";
                stats.Text=text;poll.Interval=active?850:3500;
                if(oldActive&&!active){await Folders();Schedule();}oldActive=active;
            }catch(Exception ex){if(!closing)stats.Text=ex.GetBaseException().Message;}finally{busyPoll=false;}
        }
        void Schedule(){
            ++generation;debounce.Stop();more.Enabled=false;cursor=null;
            if(input.Text.Length==0){results.Items.Clear();queryInfo.Text="输入正则表达式开始查找";return;}
            debounce.Start();
        }
        async void Query(bool next){
            debounce.Stop();if(input.Text.Length==0 || worker==null)return;
            int ticket=++generation;queryInfo.Text="正在查找…";more.Enabled=false;
            try{
                var r=(Dictionary<string,object>)await worker.Call("search_mail",new {pattern=input.Text,mode=App.Modes[mode.SelectedIndex],
                    caseSensitive=matchCase.Checked,limit=cfg.limit,folder=folder.SelectedIndex>0?folder.Text:null,cursor=next?cursor:null});
                if(ticket!=generation||closing)return;
                results.BeginUpdate();try{
                    results.Items.Clear();
                    foreach(Dictionary<string,object> hit in (IEnumerable)r["items"]){
                        string field=Convert.ToString(hit["field"]);
                        var li=new ListViewItem(new[]{Convert.ToString(hit["subject"]),field=="body"?"正文":field=="attachment"?"附件名":"标题",
                            Convert.ToString(hit["snippet"]),Convert.ToString(hit["sender"]),Convert.ToString(hit["received"]).Replace("T"," ").Split('.')[0],Convert.ToString(hit["folder"])});
                        li.Tag=hit["id"];results.Items.Add(li);
                    }
                }finally{results.EndUpdate();}
                cursor=r["next"];more.Enabled=cursor!=null;
                queryInfo.Text=results.Items.Count+" 封 · "+r["ms"]+" ms"+(cursor!=null?" · 还有结果":"")+"  "+r["partial"];
            }catch(Exception ex){if(ticket==generation&&!closing){results.Items.Clear();queryInfo.Text=ex.GetBaseException().Message;}}
        }
        async void OpenSelected(){
            if(results.SelectedItems.Count==0)return;
            try{await worker.Call("open",new{id=results.SelectedItems[0].Tag});}catch(Exception ex){if(!closing)App.Error(ex);}
        }
    }
}
