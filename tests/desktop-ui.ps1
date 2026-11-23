param([switch]$Assistant,[switch]$Legacy,[ValidateSet('classic','graph')][string]$Source='classic',[string]$Bundle)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
if(!$Bundle){$Bundle=Join-Path $root 'dist/MailPilot'}
$env:MAILPILOT_QA_BUNDLE=(Resolve-Path -LiteralPath $Bundle).Path
$qa=Join-Path $root ('.build\desktop-qa-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qa | Out-Null
$env:MAILPILOT_HOME=$qa
$env:MAILPILOT_SOURCE=$Source
$env:MAILPILOT_TEST_AI=if($Assistant){'1'}else{'0'}
$config=@{autoRefresh=$false;theme='light';source=$Source;limit=20}
if($Source -eq 'graph'){
  $config.clientId=[guid]::NewGuid().ToString()
  [IO.File]::WriteAllText((Join-Path $qa 'graph-account.json'),(@{account='test';clientId=$config.clientId}|ConvertTo-Json))
}
[IO.File]::WriteAllText((Join-Path $qa 'settings.json'),($config|ConvertTo-Json))
if($Legacy){
  $originals=Join-Path $qa 'originals'
  & (Join-Path $Bundle 'Runtime/python.exe') -B (Join-Path $PSScriptRoot 'preview_fixtures.py') $originals
  if($LASTEXITCODE){throw 'Office fixtures failed'}
  $fixtureOffice=Join-Path $env:ProgramFiles 'LibreOffice/program/soffice.com'
  $profileUri=([uri](Join-Path $qa 'converter')).AbsoluteUri
  foreach($pair in @(@('交付说明.docx','doc:MS Word 97'),@('报价单.xlsx','xls:MS Excel 97'),@('进度汇报.pptx','ppt:MS PowerPoint 97'))){
    & $fixtureOffice "-env:UserInstallation=$profileUri" --headless --convert-to $pair[1] --outdir $originals (Join-Path $originals $pair[0])
    if(!(Test-Path (Join-Path $originals ([IO.Path]::ChangeExtension($pair[0],$pair[1].Split(':')[0]))))){throw 'Legacy fixture conversion failed'}
  }
}
& (Join-Path $Bundle 'Runtime\python.exe') -B (Join-Path $PSScriptRoot 'desktop-fixture.py')
if($LASTEXITCODE){throw 'Fixture creation failed'}
$harness=Join-Path $qa 'harness'
New-Item -ItemType Directory -Path $harness | Out-Null
[IO.File]::WriteAllText((Join-Path $harness 'package.json'),'{"name":"mailpilot-test","main":"index.cjs","version":"1.20.3"}')
[IO.File]::WriteAllText((Join-Path $harness 'index.cjs'),"require('../../../tests/desktop-ui.cjs')")
$p=Start-Process -FilePath (Join-Path $Bundle 'Browser\electron.exe') -ArgumentList ('"'+$harness+'"') -PassThru -WindowStyle Hidden
if(!$p.WaitForExit(150000)){$p.Kill();throw "UI test timed out in $qa"}
$result=Join-Path $qa 'result.txt'
if(!(Test-Path -LiteralPath $result)){throw "Electron exited with code $($p.ExitCode) before producing a UI test result in $qa"}
Get-Content -LiteralPath $result
if($p.ExitCode){throw "UI test failed in $qa"}
"Verified $qa"
