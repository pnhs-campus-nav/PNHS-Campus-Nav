param(
    [string] $Output = "build/offline-map/pnhs-offline-map-package.zip",
    [string] $InputOsmJson = "",
    [switch] $KeepWorkDir
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$pythonScript = Join-Path $scriptDir "build_pnhs_package.py"

Push-Location $repoRoot
try {
    $argsList = @($pythonScript, "--output", $Output)
    if ($InputOsmJson) {
        $argsList += @("--input-osm-json", $InputOsmJson)
    }
    if ($KeepWorkDir) {
        $argsList += "--keep-work-dir"
    }
    python @argsList
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
