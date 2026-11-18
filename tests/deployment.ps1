$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$production=Join-Path $root 'dist\MailPilot'
$temp=Join-Path $root '.build\部署 测试'
New-Item $temp -ItemType Directory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $production 'MailPilot.exe'),(Join-Path $production 'MailPilot.Outlook.dll') -Destination $temp -Force
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
$scopeTest=Join-Path $temp 'scope-test.exe'
& $csc /nologo /codepage:65001 /target:exe "/out:$scopeTest" "$root\native\Deployment.cs" "$PSScriptRoot\deployment-scopes.cs"
if($LASTEXITCODE){throw 'Scope regression compilation failed'}
& $scopeTest $temp $production
if($LASTEXITCODE){throw 'Scope regression failed'}
function Deploy($dir,$action) {
    $p=Start-Process -FilePath (Join-Path $dir 'MailPilot.exe') -ArgumentList $action -PassThru -WindowStyle Hidden -Wait
    if($p.ExitCode) {throw "Manager failed: $action"}
}
try {
    Deploy $temp enable
    $server='Software\Classes\CLSID\{85C590EA-8141-4C33-99A0-F304FFA27D7E}\InprocServer32'
    foreach($view in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)) {
        $reg=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
        try {
            $version=$reg.OpenSubKey("$server\0.1.0.0",$true)
            try {$version.SetValue('CodeBase','file:///missing/MailPilot.Outlook.dll')} finally {$version.Dispose()}
        } finally {$reg.Dispose()}
    }
    Deploy $temp enable
    Deploy $production disable
    $path='HKCU:\Software\Classes\CLSID\{85C590EA-8141-4C33-99A0-F304FFA27D7E}\InprocServer32'
    if(([uri](Get-ItemProperty $path).CodeBase).LocalPath -ne (Join-Path $temp 'MailPilot.Outlook.dll')) {throw 'An old copy disabled the active copy'}
    foreach($hostExe in @("$env:Windir\System32\WindowsPowerShell\v1.0\powershell.exe","$env:Windir\SysWOW64\WindowsPowerShell\v1.0\powershell.exe")) {
        & $hostExe -NoProfile -Command '$ErrorActionPreference="Stop"; $obj=New-Object -ComObject MailPilot.Outlook; if($null -eq $obj){exit 1}; [Environment]::Is64BitProcess'
        if($LASTEXITCODE){throw 'COM activation failed'}
    }
    Deploy $temp disable
    if(Test-Path $path){throw 'Class remains registered'}
    if(Test-Path 'HKCU:\Software\Classes\mailpilot'){throw 'URL handler remains registered'}
    foreach($base in @('HKCU:\Software','HKLM:\Software','HKLM:\Software\WOW6432Node')) {
        $uninstall=Join-Path $base 'Microsoft\Windows\CurrentVersion\Uninstall\*'
        if(Get-ItemProperty $uninstall -ErrorAction SilentlyContinue | Where-Object DisplayName -like 'MailPilot*'){throw 'Unexpected uninstall entry'}
    }
    'PASS stale CLR path repair, both COM views, Unicode/space paths, version ownership and clean disable'
} finally {Deploy $production enable}
