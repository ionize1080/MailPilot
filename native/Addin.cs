using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using Extensibility;
using Office = Microsoft.Office.Core;

[assembly: AssemblyVersion("0.1.0.0")]
[assembly: ComVisible(false)]
namespace MailPilot {
    [ComVisible(true), Guid("E6946569-C68F-49E1-BEFC-727F546F20B9"), InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    public interface IRibbonActions {
        [DispId(1)] void Search(Office.IRibbonControl control);
        [DispId(2)] void Assistant(Office.IRibbonControl control);
        [DispId(3)] void Settings(Office.IRibbonControl control);
        [DispId(4)] void Loaded(Office.IRibbonUI ui);
        [DispId(5)] bool RibbonReady { get; }
    }

    [ComVisible(true), Guid("85C590EA-8141-4C33-99A0-F304FFA27D7E"), ProgId("MailPilot.Outlook"),
     ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IRibbonActions))]
    public sealed class Connect : IDTExtensibility2, Office.IRibbonExtensibility, IRibbonActions {
        public bool RibbonReady { get; private set; }
        public void OnConnection(object app, ext_ConnectMode mode, object addin, ref Array custom) {
            addin.GetType().InvokeMember("Object",BindingFlags.SetProperty,null,addin,new object[]{this});
        }
        public void OnDisconnection(ext_DisconnectMode mode, ref Array custom) { RibbonReady=false; }
        public void OnAddInsUpdate(ref Array custom) {}
        public void OnStartupComplete(ref Array custom) {}
        public void OnBeginShutdown(ref Array custom) {}
        public string GetCustomUI(string id) {
            if(id!="Microsoft.Outlook.Explorer" && id!="Microsoft.Outlook.Mail.Read") return null;
            return @"<customUI xmlns=""http://schemas.microsoft.com/office/2009/07/customui"" onLoad=""Loaded""><ribbon><tabs>
              <tab id=""MailPilotTab"" label=""MailPilot""><group id=""MailPilotTools"" label=""邮件工具"">
              <button id=""MailPilotSearch"" label=""正则查找"" size=""large"" imageMso=""FindDialog"" onAction=""Search""/>
              <button id=""MailPilotAI"" label=""AI 助手"" size=""large"" imageMso=""ResearchPane"" onAction=""Assistant""/>
              <button id=""MailPilotSettings"" label=""设置"" size=""large"" imageMso=""PropertySheet"" onAction=""Settings""/>
              </group></tab></tabs></ribbon></customUI>";
        }
        public void Loaded(Office.IRibbonUI ui) { RibbonReady=true; }
        static void Launch(string action) {
            var root=Path.GetDirectoryName(typeof(Connect).Assembly.Location);
            Process.Start(new ProcessStartInfo(Path.Combine(root,"MailPilot.exe"),action) {WorkingDirectory=root,UseShellExecute=false});
        }
        public void Search(Office.IRibbonControl control) { Launch("classic-search"); }
        public void Assistant(Office.IRibbonControl control) { Launch("classic-ai"); }
        public void Settings(Office.IRibbonControl control) { Launch("settings"); }
    }
}
