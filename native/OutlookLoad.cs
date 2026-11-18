using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Security;

namespace MailPilot {
    internal static class OutlookLoad {
        static string Folder { get { return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MailPilot"); } }
        internal static string ErrorFile { get { return Path.Combine(Folder, "outlook-load-error.txt"); } }
        static string Receipt(int session) { return Path.Combine(Folder, "outlook-load-" + session + ".txt"); }

        internal static void Record(string dll, string state, Exception error = null) {
            try {
                using (var host = Process.GetCurrentProcess()) {
                    if (!host.ProcessName.Equals("OUTLOOK", StringComparison.OrdinalIgnoreCase)) return;
                    Directory.CreateDirectory(Folder);
                    if (error != null) File.WriteAllText(ErrorFile, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") +
                        " · Outlook " + (IntPtr.Size * 8) + " 位" + Environment.NewLine + dll + Environment.NewLine +
                        "OnConnection · 0x" + error.HResult.ToString("X8") + " · " + error.Message);
                    string file = Receipt(host.SessionId), temp = file + "." + host.Id + ".tmp";
                    try {
                        File.WriteAllLines(temp, new[]{host.Id.ToString(), host.StartTime.ToUniversalTime().Ticks.ToString(),
                            host.MainModule.FileVersionInfo.FileVersion, dll, state});
                        if (File.Exists(file)) File.Replace(temp,file,null);
                        else File.Move(temp,file);
                    } finally { File.Delete(temp); }
                }
            } catch (IOException) { } catch (UnauthorizedAccessException) { } catch (SecurityException) { }
              catch (Win32Exception) { } catch (InvalidOperationException) { } catch (NotSupportedException) { }
        }
        internal static string Current(string expectedDll) {
            try {
                using (var self = Process.GetCurrentProcess()) {
                    string file = Receipt(self.SessionId);
                    if (!File.Exists(file)) return null;
                    var lines = File.ReadAllLines(file);
                    int pid; long start;
                    if (lines.Length != 5 || !int.TryParse(lines[0], out pid) || !long.TryParse(lines[1], out start)) return null;
                    using (var host = Process.GetProcessById(pid)) {
                        if (!host.ProcessName.Equals("OUTLOOK",StringComparison.OrdinalIgnoreCase) || host.SessionId != self.SessionId ||
                            host.StartTime.ToUniversalTime().Ticks != start) return null;
                    }
                    string name = "Outlook " + lines[2];
                    if (lines[4] == "failed") return name + " 调用 MailPilot 的 OnConnection 时遇到错误。";
                    if (lines[4] == "disconnected") return name + " 已断开 MailPilot。";
                    if (lines[4] != "connected" && lines[4] != "ribbon") return null;
                    if (!string.Equals(lines[3], expectedDll, StringComparison.OrdinalIgnoreCase))
                        return name + " 已连接其他目录的 MailPilot　" + lines[3];
                    return lines[4] == "ribbon" ? name + " 已连接此目录，功能区已加载（已验证）。"
                        : name + " 已连接此目录，正在等待功能区加载回执。请打开收件箱主窗口再检查。";
                }
            } catch (IOException) { } catch (UnauthorizedAccessException) { } catch (SecurityException) { }
              catch (ArgumentException) { } catch (InvalidOperationException) { } catch (Win32Exception) { }
            return null;
        }
    }
}
