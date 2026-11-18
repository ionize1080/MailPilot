param([Parameter(Mandatory=$true)][string]$KeyFile)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$env:MAILPILOT_QA_KEY_FILE=(Resolve-Path -LiteralPath $KeyFile).Path
$env:MAILPILOT_HOME=Join-Path $root '.build\qa-mailbox'
$env:MAILPILOT_CHAT_DIR=Join-Path $root ('.build\qa-chat-'+[guid]::NewGuid().ToString('N'))
$env:MAILPILOT_SOURCE='classic'
$harness=Join-Path $root '.build\qa-harness'
New-Item $harness -ItemType Directory -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $harness 'package.json'),'{"name":"xyz.chatboxapp.ce","productName":"Chatbox","version":"1.20.3","main":"index.cjs"}')
[IO.File]::WriteAllText((Join-Path $harness 'index.cjs'),"require('../../tests/live-chatbox.cjs')")
$p=Start-Process -FilePath (Join-Path $root 'dist\MailPilot\Browser\electron.exe') -ArgumentList ('"'+$harness+'"') -PassThru -WindowStyle Hidden
if (!$p.WaitForExit(240000)) { $p.Kill(); throw 'Chatbox QA timed out' }
exit $p.ExitCode
