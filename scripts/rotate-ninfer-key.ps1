[CmdletBinding()]
param(
    [switch]$Yes
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$arguments = @((Join-Path $repoRoot 'ninfer.py'), 'rotate-key')
if ($Yes) {
    $arguments += '--yes'
}

& python @arguments
exit $LASTEXITCODE
