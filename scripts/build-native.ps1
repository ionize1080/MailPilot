$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot
$out=Join-Path $root 'dist\MailPilot'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
$office=Get-ChildItem "$env:WINDIR\assembly\GAC_MSIL\office\*\office.dll" | Sort-Object FullName | Select-Object -First 1
$ext=Get-ChildItem "$env:WINDIR\assembly\GAC\Extensibility\*\Extensibility.dll" | Select-Object -First 1
if (!$office -or !$ext) { throw 'The Office primary interop and Extensibility build references are required.' }
& $csc /nologo /optimize+ /codepage:65001 /target:library /platform:anycpu "/link:$($office.FullName)" "/link:$($ext.FullName)" "/out:$out\MailPilot.Outlook.dll" "$root\native\Addin.cs"
if ($LASTEXITCODE) {throw 'Outlook add-in compilation failed'}
& $csc /nologo /optimize+ /codepage:65001 /target:winexe /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll "/out:$out\MailPilot.exe" "$root\native\App.cs" "$root\native\Deployment.cs" "$root\native\Options.cs" "$root\native\SearchForm.cs"
if ($LASTEXITCODE) {throw 'Desktop application compilation failed'}
