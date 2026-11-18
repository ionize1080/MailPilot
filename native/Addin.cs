using System;
using System.Diagnostics;
using System.IO;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Reflection;
using System.Runtime.InteropServices;
using Extensibility;
using Office = Microsoft.Office.Core;

[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.2.1.0")]
[assembly: ComVisible(false)]
namespace MailPilot {
    [ComVisible(true), Guid("E6946569-C68F-49E1-BEFC-727F546F20B9"), InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    public interface IRibbonActions {
        [DispId(1)] void Search(Office.IRibbonControl control);
        [DispId(2)] void Assistant(Office.IRibbonControl control);
        [DispId(3)] void Settings(Office.IRibbonControl control);
        [DispId(4)] void Loaded(Office.IRibbonUI ui);
        [DispId(5)] bool RibbonReady { get; }
        [DispId(6)] bool SetPanel(string action,string tool,string handle,string side,int width);
        [DispId(7)] object RibbonImage(Office.IRibbonControl control);
        [DispId(8)] string LoadedPath { get; }
    }

    [ComVisible(true), Guid("85C590EA-8141-4C33-99A0-F304FFA27D7E"), ProgId("MailPilot.Outlook"),
     ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IRibbonActions))]
    public sealed class Connect : IDTExtensibility2, Office.IRibbonExtensibility, Office.ICustomTaskPaneConsumer, IRibbonActions {
        Office.ICTPFactory factory;
        Office.IRibbonUI ribbon;
        dynamic outlook;
        Control dispatcher;
        bool connected;
        readonly Dictionary<string,Office.CustomTaskPane> panes=new Dictionary<string,Office.CustomTaskPane>();
        readonly Dictionary<string,object> images=new Dictionary<string,object>();
        public bool RibbonReady { get; private set; }
        public string LoadedPath { get { return typeof(Connect).Assembly.Location; } }
        public void OnConnection(object app, ext_ConnectMode mode, object addin, ref Array custom) {
            try {
                outlook=app; dispatcher=new Control();dispatcher.CreateControl();
                ((Office.COMAddIn)addin).Object=this;
                connected=true;
                OutlookLoad.Record(LoadedPath,RibbonReady ? "ribbon" : "connected");
            } catch (Exception error) {
                OutlookLoad.Record(LoadedPath,"failed",error);
                if (dispatcher != null) dispatcher.Dispose();
                dispatcher=null;outlook=null;
                throw;
            }
        }
        public void OnDisconnection(ext_DisconnectMode mode, ref Array custom) {
            connected=false;
            OutlookLoad.Record(LoadedPath,"disconnected");
            RibbonReady=false;foreach(var pane in panes.Values){try{((DockHost)pane.ContentControl).HostClosed();pane.Delete();}catch(COMException){}}
            panes.Clear();factory=null;ribbon=null;outlook=null;if(dispatcher!=null)dispatcher.Dispose();
        }
        public void CTPFactoryAvailable(Office.ICTPFactory value){factory=value;}
        public bool SetPanel(string action,string tool,string handle,string side,int width){
            if(dispatcher==null || dispatcher.IsDisposed)return false;
            if(dispatcher.InvokeRequired) return (bool)dispatcher.Invoke(new Func<string,string,string,string,int,bool>(SetPanel),action,tool,handle,side,width);
            if(action=="icons"){if(ribbon!=null)ribbon.Invalidate();return true;}
            long value;if((tool!="search" && tool!="ai") || !long.TryParse(handle,out value))return false;
            var hwnd=new IntPtr(value);
            if(!DockHost.OwnsElectron(hwnd))return false;
            Office.CustomTaskPane existing;
            if(panes.TryGetValue(handle,out existing)){
                try {
                    var host=(DockHost)existing.ContentControl;
                    if(action=="hide"){existing.Visible=false;return true;}
                    host.Detach();existing.Delete();
                }catch(COMException){}
                panes.Remove(handle);
            }
            if(action=="detach")return true;
            if(action!="attach" || factory==null)return false;
            object window=outlook.ActiveWindow();
            if(window==null)return false;
            var p=factory.CreateCTP("MailPilot.DockHost",tool=="ai"?"MailPilot · AI 助手":"MailPilot · 正则查找",window);
            panes.Add(handle,p);
            p.DockPosition=side=="left"?Office.MsoCTPDockPosition.msoCTPDockPositionLeft:Office.MsoCTPDockPosition.msoCTPDockPositionRight;
            var panel=(DockHost)p.ContentControl;
            using(var g=panel.CreateGraphics())p.Width=(int)(Math.Max(300,Math.Min(800,width))*g.DpiX/96);
            panel.ChildClosed=()=>{panes.Remove(handle);try{p.Delete();}catch(COMException){}};
            p.Visible=true;panel.Attach(hwnd);return true;
        }
        class Pictures : AxHost {
            Pictures():base(""){}
            public static object ConvertImage(Image image){return GetIPictureDispFromPicture(image);}
        }
        public object RibbonImage(Office.IRibbonControl control){
            string palette="jade", file=control.Id=="MailPilotAI"?"ai":control.Id=="MailPilotSearch"?"search":"settings";
            try{
                string home=Environment.GetEnvironmentVariable("MAILPILOT_HOME")??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MailPilot");
                var settings=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(home,"settings.json")));
                object selected;if(settings.TryGetValue("palette",out selected) && (Equals(selected,"ocean")||Equals(selected,"graphite")))palette=(string)selected;
            }catch(IOException){}catch(ArgumentException){}
            string key=palette+"-"+file;
            if(!images.ContainsKey(key)){
                string path=Path.Combine(Path.GetDirectoryName(typeof(Connect).Assembly.Location),"Desktop","icons",key+".png");
                using(var img=Image.FromFile(path))using(var small=new Bitmap(img,32,32))images[key]=Pictures.ConvertImage(small);
            }
            return images[key];
        }
        public void OnAddInsUpdate(ref Array custom) {}
        public void OnStartupComplete(ref Array custom) {}
        public void OnBeginShutdown(ref Array custom) {}
        public string GetCustomUI(string id) {
            if(id!="Microsoft.Outlook.Explorer" && id!="Microsoft.Outlook.Mail.Read") return null;
            return @"<customUI xmlns=""http://schemas.microsoft.com/office/2009/07/customui"" onLoad=""Loaded""><ribbon><tabs>
              <tab id=""MailPilotTab"" label=""MailPilot""><group id=""MailPilotTools"" label=""邮件工具"">
              <button id=""MailPilotSearch"" label=""正则查找"" size=""large"" getImage=""RibbonImage"" onAction=""Search""/>
              <button id=""MailPilotAI"" label=""AI 助手"" size=""large"" getImage=""RibbonImage"" onAction=""Assistant""/>
              <button id=""MailPilotSettings"" label=""设置"" size=""large"" getImage=""RibbonImage"" onAction=""Settings""/>
              </group></tab></tabs></ribbon></customUI>";
        }
        public void Loaded(Office.IRibbonUI ui) {
            ribbon=ui;RibbonReady=true;
            if(connected) OutlookLoad.Record(LoadedPath,"ribbon");
        }
        static void Launch(string action) {
            var root=Path.GetDirectoryName(typeof(Connect).Assembly.Location);
            Process.Start(new ProcessStartInfo(Path.Combine(root,"MailPilot.exe"),action) {WorkingDirectory=root,UseShellExecute=false});
        }
        public void Search(Office.IRibbonControl control) { Launch("classic-search"); }
        public void Assistant(Office.IRibbonControl control) { Launch("classic-ai"); }
        public void Settings(Office.IRibbonControl control) { Launch("settings"); }
    }
}
