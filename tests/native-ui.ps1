$ErrorActionPreference='Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class MailPilotUiTest {
    delegate bool Visit(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h,Visit v,IntPtr p);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h,StringBuilder b,int n);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr h,int m,IntPtr w,string s);
    [DllImport("user32.dll",EntryPoint="SendMessageW")] static extern IntPtr Query(IntPtr h,int m,IntPtr w,IntPtr l);
    public static IntPtr Child(IntPtr window,string classPart) {
        IntPtr found=IntPtr.Zero;
        EnumChildWindows(window,delegate(IntPtr h,IntPtr p){
            var name=new StringBuilder(256);GetClassName(h,name,256);
            if(name.ToString().IndexOf(classPart,StringComparison.OrdinalIgnoreCase)>=0){found=h;return false;}
            return true;
        },IntPtr.Zero);return found;
    }
    public static void SetText(IntPtr h,string text){SendMessage(h,12,IntPtr.Zero,text);}
    public static int Results(IntPtr h){return Query(h,0x1004,IntPtr.Zero,IntPtr.Zero).ToInt32();}
}
'@
$root=Split-Path $PSScriptRoot
$env:MAILPILOT_HOME=Join-Path $root '.build\qa-mailbox'
$settings=Join-Path $env:MAILPILOT_HOME 'settings.json'
$original=[IO.File]::ReadAllBytes($settings)
$cfg=Get-Content -Raw $settings | ConvertFrom-Json -AsHashtable
$cfg['autoRefresh']=$false
$cfg['mode']='all'
[IO.File]::WriteAllText($settings,($cfg|ConvertTo-Json))
function Until($code,$label) {
    for($i=0;$i -lt 60;$i++){
        $r=& $code
        if($r){return $r}
        Start-Sleep -Milliseconds 150
    }
    throw "Timed out: $label"
}
$p=Start-Process -FilePath (Join-Path $root 'dist\MailPilot\MailPilot.exe') -ArgumentList 'search' -PassThru
try {
    $null=Until {$p.Refresh();$p.MainWindowTitle -eq 'MailPilot · 正则查找'} 'search window'
    $box=[MailPilotUiTest]::Child($p.MainWindowHandle,'.EDIT.')
    $list=[MailPilotUiTest]::Child($p.MainWindowHandle,'SysListView32')
    if($box -eq 0 -or $list -eq 0){throw 'Search controls unavailable'}
    [MailPilotUiTest]::SetText($box,'Aurora-QA-[0-9]+')
    $null=Until {[MailPilotUiTest]::Results($list) -eq 1} 'matched Outlook fixture'
    [MailPilotUiTest]::SetText($box,'NoMatch_43867')
    $null=Until {[MailPilotUiTest]::Results($list) -eq 0} 'old results cleared'
    $p.Refresh()
    'PASS native search window, automatic query, matched attachment and refresh. Window working set MiB: '+[Math]::Round($p.WorkingSet64/1MB,1)
} finally {
    $p.CloseMainWindow() | Out-Null
    $p.WaitForExit(5000) | Out-Null
    [IO.File]::WriteAllBytes($settings,$original)
}
