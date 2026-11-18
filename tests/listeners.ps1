param([int]$RootProcess)
$ErrorActionPreference='Stop'
$processes=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId
$ids=@($RootProcess)
do {
    $before=$ids.Count
    $ids+=@($processes | Where-Object {$_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids} | Select-Object -ExpandProperty ProcessId)
} while ($before -ne $ids.Count)
$open=Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object OwningProcess -In $ids
if($open){throw ('Unexpected listening ports: '+(($open.LocalPort | Sort-Object -Unique) -join ', '))}
'PASS no listening TCP ports in application process tree'
