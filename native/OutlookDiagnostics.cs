using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;

namespace MailPilot {
    internal static class OutlookDiagnostics {
        static string Bitness(string file) {
            try {
                using (var reader = new BinaryReader(File.Open(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))) {
                    if (reader.ReadUInt16() != 0x5A4D) return "位数未知";
                    reader.BaseStream.Position = 0x3C;
                    uint offset = reader.ReadUInt32();
                    reader.BaseStream.Position = offset;
                    if (reader.ReadUInt32() != 0x4550) return "位数未知";
                    switch (reader.ReadUInt16()) {
                        case 0x014C: return "32 位";
                        case 0x8664: case 0xAA64: return "64 位";
                    }
                }
            } catch (IOException) { } catch (UnauthorizedAccessException) { }
            return "位数未知";
        }

        static string OutlookFile() {
            const string path = @"Software\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE";
            foreach (var hive in new[]{RegistryHive.CurrentUser, RegistryHive.LocalMachine})
                foreach (var view in Deployment.Views) using (var root = RegistryKey.OpenBaseKey(hive, view))
                    using (var key = root.OpenSubKey(path)) {
                        string file = key == null ? "" : Convert.ToString(key.GetValue("")).Trim('"');
                        if (File.Exists(file)) return file;
                    }
            return null;
        }
        static string Connection() {
            object app = null, addins = null, item = null, automation = null;
            try {
                dynamic outlook = app = Marshal.GetActiveObject("Outlook.Application");
                string version = Convert.ToString(outlook.Version);
                addins = outlook.COMAddIns;
                dynamic entry = item = ((dynamic)addins).Item(Deployment.Prog);
                if (!entry.Connect) return "Outlook " + version + " 报告 MailPilot 未连接（Connect=False）。";
                dynamic plugin = automation = entry.Object;
                if (plugin == null) return "Outlook " + version + " 已连接 MailPilot，但未提供加载项对象。";
                bool ready = plugin.RibbonReady;
                string file;
                try { file = plugin.LoadedPath; }
                catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException) {
                    return "Outlook " + version + " 已连接，正在使用不提供 DLL 路径的旧版 MailPilot。";
                }
                if (!Deployment.Same(file, Deployment.Dll)) return "Outlook " + version + " 已连接其他目录的 MailPilot　" + file;
                return ready ? "Outlook " + version + " 已连接此目录，功能区已加载（已验证）。"
                    : "Outlook " + version + " 已连接此目录的 MailPilot，尚未收到功能区加载回执。请打开收件箱主窗口再检查。";
            } catch (COMException e) {
                var receipt = OutlookLoad.Current(Deployment.Dll);
                if (receipt != null) return receipt;
                if ((uint)e.ErrorCode == 0x800401E3)
                    return "未取得正在运行的经典 Outlook（0x800401E3）。请打开收件箱，并以与 Outlook 相同的账户和权限检查。";
                return "读取 Outlook 的实时状态失败（0x" + e.ErrorCode.ToString("X8") + "）　" + e.Message;
            } catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException e) {
                return "读取 Outlook 加载项接口失败　" + e.Message;
            } finally {
                foreach (var obj in new[]{automation,item,addins,app})
                    if (obj != null && Marshal.IsComObject(obj)) Marshal.ReleaseComObject(obj);
            }
        }
        internal static string Report() {
            var text = new StringBuilder();
            text.AppendLine(Connection()).AppendLine();
            text.AppendLine("部署器目录　" + App.Root);
            text.AppendLine("部署器权限　" + (Deployment.Elevated ? "管理员" : "普通用户"));
            string outlook = OutlookFile();
            if (outlook != null) {
                text.AppendLine("已安装 Outlook　" + FileVersionInfo.GetVersionInfo(outlook).FileVersion + " · " + Bitness(outlook) + " · " + outlook);
            }
            foreach (var scope in new[]{RegistryHive.CurrentUser, RegistryHive.LocalMachine})
                text.AppendLine().AppendLine(Deployment.ScopeName(scope)).AppendLine(Deployment.Status(scope));
            if (File.Exists(OutlookLoad.ErrorFile)) {
                try { text.AppendLine().AppendLine("最近一次 OnConnection 异常（历史记录）").AppendLine(File.ReadAllText(OutlookLoad.ErrorFile)); }
                catch (IOException) { } catch (UnauthorizedAccessException) { }
            }
            return text.ToString().TrimEnd();
        }
    }
}
