using System;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace MailPilot {
    [ComVisible(true), Guid("3AD910BB-5093-45FA-AB6E-68094BC37F22"), ProgId("MailPilot.DockHost")]
    public sealed class DockHost : UserControl {
        // Chromium keeps its own keyboard message loop as an owned top-level window.
        [DllImport("user32.dll")] static extern IntPtr GetAncestor(IntPtr h, uint flag);
        [DllImport("user32.dll")] static extern bool IsWindow(IntPtr h);
        [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
        [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h,uint msg,IntPtr w,IntPtr l);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int w,int ht,uint flags);
        [DllImport("user32.dll",EntryPoint="SetWindowLongW")] static extern int SetLong(IntPtr h,int index,int value);
        [DllImport("user32.dll",EntryPoint="SetWindowLongPtrW")] static extern IntPtr SetLongPtr(IntPtr h,int index,IntPtr value);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
        [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr proc,int flags,StringBuilder name,ref int size);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr proc);
        static void Owner(IntPtr child, IntPtr value) {
            if(IntPtr.Size==8) SetLongPtr(child,-8,value); else SetLong(child,-8,value.ToInt32());
        }
        internal static bool OwnsElectron(IntPtr h) {
            uint pid; GetWindowThreadProcessId(h,out pid);
            var proc=OpenProcess(0x1000,false,pid);
            if(proc==IntPtr.Zero) return false;
            try {
                int size=32768;var name=new StringBuilder(size);
                string root=Path.GetDirectoryName(typeof(DockHost).Assembly.Location);
                return QueryFullProcessImageName(proc,0,name,ref size) &&
                    string.Equals(name.ToString(),Path.Combine(root,@"Browser\electron.exe"),StringComparison.OrdinalIgnoreCase);
            } finally {CloseHandle(proc);}
        }
        internal IntPtr Child {get;private set;}
        internal Action ChildClosed;
        readonly Timer track=new Timer { Interval=120 };
        Rectangle last;
        public DockHost() { BackColor=Color.White;track.Tick+=(s,e)=>Fit(); }
        internal void Attach(IntPtr child) {
            Child=child;Owner(child,GetAncestor(Handle,2));last=Rectangle.Empty;track.Start();Fit();
        }
        internal void Detach() {
            track.Stop();
            if(Child!=IntPtr.Zero && IsWindow(Child)) Owner(Child,IntPtr.Zero);
            Child=IntPtr.Zero;
        }
        internal void HostClosed() {
            var window=Child;Detach();
            if(window!=IntPtr.Zero && IsWindow(window))PostMessage(window,0x802A,IntPtr.Zero,IntPtr.Zero);
        }
        void Fit() {
            if(Child==IntPtr.Zero || !IsHandleCreated) return;
            if(!IsWindow(Child)) {Detach();if(ChildClosed!=null)ChildClosed();return;}
            if(!Visible || !IsWindowVisible(Handle) || IsIconic(GetAncestor(Handle,2))) {ShowWindow(Child,0);return;}
            var r=RectangleToScreen(ClientRectangle);
            if(r.Width<10 || r.Height<10) return;
            if(r!=last) {SetWindowPos(Child,IntPtr.Zero,r.X,r.Y,r.Width,r.Height,0x0014);last=r;}
            if(!IsWindowVisible(Child)) ShowWindow(Child,4);
        }
        protected override void OnVisibleChanged(EventArgs e){base.OnVisibleChanged(e);Fit();}
        protected override void OnResize(EventArgs e){base.OnResize(e);Fit();}
        protected override void Dispose(bool disposing){if(disposing){HostClosed();track.Dispose();}base.Dispose(disposing);}
    }
}
