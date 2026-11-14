param(
    [Parameter(Mandatory=$true)][string]$Snapshot,
    [Parameter(Mandatory=$true)][string]$Ready,
    [Parameter(Mandatory=$true)][string]$Release
)
$ErrorActionPreference = 'Stop'
$taskStream = [System.IO.FileStream]::new($Snapshot, [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
try {
    @{ pid=$PID; timestamp=[DateTimeOffset]::Now.ToString('o'); snapshot=$Snapshot;
       share='ReadWrite; Delete intentionally excluded' } | ConvertTo-Json |
        Set-Content -LiteralPath $Ready -Encoding utf8
    $taskDeadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not (Test-Path -LiteralPath $Release)) {
        if ([DateTime]::UtcNow -ge $taskDeadline) { throw 'Snapshot lock release was not confirmed within 45 seconds' }
        Start-Sleep -Milliseconds 50
    }
} finally {
    $taskStream.Dispose()
}
