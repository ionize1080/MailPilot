$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root=Split-Path $PSScriptRoot
$env:MAILPILOT_HOME=Join-Path $root '.build\qa-mailbox'
$settings=Join-Path $env:MAILPILOT_HOME 'settings.json'
$original=[IO.File]::ReadAllBytes($settings)
$cfg=Get-Content -Raw $settings | ConvertFrom-Json -AsHashtable
$cfg['autoRefresh']=$false
$cfg['mode']='all'
[IO.File]::WriteAllText($settings,($cfg|ConvertTo-Json))
function Named($parent,$name) {
    $condition=[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$name)
    $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
}
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
    $null=Until {$p.Refresh();$p.MainWindowHandle -ne 0} 'search window'
    $w=[System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
    $box=Until {Named $w '正则表达式'} 'input'
    $set=$box.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $set.SetValue('Aurora-QA-[0-9]+')
    $null=Until {Named $w 'Attachment receipt'} 'matched Outlook fixture'
    $set.SetValue('NoMatch_43867')
    $null=Until {$null -eq (Named $w 'Attachment receipt')} 'old results cleared'
    $p.Refresh()
    'PASS native search window, automatic query, matched attachment and refresh. Window working set MiB: '+[Math]::Round($p.WorkingSet64/1MB,1)
} finally {
    $p.CloseMainWindow() | Out-Null
    $p.WaitForExit(5000) | Out-Null
    [IO.File]::WriteAllBytes($settings,$original)
}
