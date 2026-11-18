param([switch]$Assistant,[ValidateSet('classic','graph')][string]$Source='classic',[string]$Bundle)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
if(!$Bundle){$Bundle=Join-Path $root 'dist/MailPilot'}
$env:MAILPILOT_QA_BUNDLE=(Resolve-Path -LiteralPath $Bundle).Path
$qa=Join-Path $root ('.build\desktop-qa-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qa | Out-Null
$env:MAILPILOT_HOME=$qa
$env:MAILPILOT_SOURCE=$Source
$env:MAILPILOT_TEST_AI=if($Assistant){'1'}else{'0'}
$config=@{autoRefresh=$false;theme='light';source=$Source}
if($Source -eq 'graph'){
  $config.clientId=[guid]::NewGuid().ToString()
  [IO.File]::WriteAllText((Join-Path $qa 'graph-account.json'),(@{account='test';clientId=$config.clientId}|ConvertTo-Json))
}
[IO.File]::WriteAllText((Join-Path $qa 'settings.json'),($config|ConvertTo-Json))
& (Join-Path $Bundle 'Runtime\python.exe') -B (Join-Path $PSScriptRoot 'desktop-fixture.py')
if($LASTEXITCODE){throw 'Fixture creation failed'}
$harness=Join-Path $qa 'harness'
New-Item -ItemType Directory -Path $harness | Out-Null
[IO.File]::WriteAllText((Join-Path $harness 'package.json'),'{"name":"mailpilot-test","main":"index.cjs","version":"1.20.3"}')
[IO.File]::WriteAllText((Join-Path $harness 'index.cjs'),"require('../../../tests/desktop-ui.cjs')")
$p=Start-Process -FilePath (Join-Path $Bundle 'Browser\electron.exe') -ArgumentList ('"'+$harness+'"') -PassThru -WindowStyle Hidden
if(!$p.WaitForExit(90000)){$p.Kill();throw "UI test timed out in $qa"}
Get-Content -LiteralPath (Join-Path $qa 'result.txt')
if($p.ExitCode){throw "UI test failed in $qa"}
"Verified $qa"
