$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    & ./scripts/build-native.ps1
    & ./scripts/build-chatbox.ps1
    python ./scripts/runtime.py
    if($LASTEXITCODE){throw 'Runtime preparation failed'}
    python ./scripts/stage-chatbox.py
    if($LASTEXITCODE){throw 'Chatbox staging failed'}
    python ./scripts/package.py
    if($LASTEXITCODE){throw 'Packaging failed'}
} finally {Pop-Location}
