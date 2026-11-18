$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
python (Join-Path $PSScriptRoot 'prepare-chatbox.py')
if ($LASTEXITCODE) { throw 'Source preparation failed' }
Push-Location (Join-Path $root '.build\chatbox')
try {
    $env:ELECTRON_SKIP_BINARY_DOWNLOAD = '1'
    $env:HUSKY = '0'
    $env:NODE_OPTIONS = '--max-old-space-size=8192'
    $env:NODE_ENV = 'development'
    npx.cmd --yes --package=node@22.16.0 --package=pnpm@10.32.1 -c 'pnpm install --ignore-scripts --frozen-lockfile'
    if ($LASTEXITCODE) { throw 'Chatbox dependency installation failed' }
    $env:NODE_ENV = 'production'
    npx.cmd --yes --package=node@22.16.0 --package=pnpm@10.32.1 -c 'pnpm exec electron-vite build'
    if ($LASTEXITCODE) { throw 'Chatbox source build failed' }
} finally { Pop-Location }
