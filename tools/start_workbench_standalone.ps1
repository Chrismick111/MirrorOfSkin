param([string]$Addon)
$ErrorActionPreference = 'Stop'

function Find-Python([IO.DirectoryInfo]$directory, [bool]$sourceCheckout) {
    $embedded = 'resources\mod_loader\_internal\venv\Bins\python.exe'
    function Test-Python([string]$path) {
        if (-not $path -or -not [IO.File]::Exists($path)) { return $false }
        try {
            # A Store placeholder or broken interpreter cannot print the probe.
            $reply = & $path -I -c "import sys; print('MOS_PYTHON_OK' if sys.version_info >= (3,9) else '')" 2>$null
            return ($LASTEXITCODE -eq 0 -and $reply -ceq 'MOS_PYTHON_OK')
        } catch { return $false }
    }
    for ($parent = $directory; $parent; $parent = $parent.Parent) {
        $candidate = Join-Path $parent.FullName $embedded
        if (Test-Python $candidate) { return $candidate }
    }
    if ($env:FAUST_LAUNCHER_ROOT) {
        $candidate = Join-Path $env:FAUST_LAUNCHER_ROOT $embedded
        if (Test-Python $candidate) { return $candidate }
    }
    $userPythons = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    foreach ($install in (Get-ChildItem -LiteralPath $userPythons -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
        $candidate = Join-Path $install.FullName 'python.exe'
        if (Test-Python $candidate) { return $candidate }
    }
    foreach ($command in (Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
        if (Test-Python $command.Source) { return $command.Source }
    }
    $manager = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($manager) {
        try {
            $candidate = & $manager.Source -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Python $candidate)) { return $candidate }
        } catch { }
    }
    # For a source checkout outside a launcher, look in common portable install
    # locations on fixed drives only, including versioned release directories.
    if ($sourceCheckout) {
        foreach ($drive in [IO.DriveInfo]::GetDrives()) {
            if ($drive.DriveType -ne 'Fixed' -or -not $drive.IsReady) { continue }
            foreach ($folder in (Get-ChildItem -LiteralPath $drive.RootDirectory.FullName -Directory -Filter 'FaustLauncher*' -ErrorAction SilentlyContinue)) {
                foreach ($root in $folder.FullName, (Join-Path $folder.FullName 'FaustLauncher')) {
                    $candidate = Join-Path $root $embedded
                    if ([IO.File]::Exists((Join-Path $root 'FaustLauncher.exe')) -and (Test-Python $candidate)) { return $candidate }
                }
            }
        }
    }
}

try {
    $sourceCheckout = -not $Addon
    if ($sourceCheckout) { $Addon = Join-Path $PSScriptRoot '..\MirrorOfSkin' }
    $directory = Get-Item -LiteralPath $Addon
    if (-not $directory.PSIsContainer) { throw "Expected a plugin directory: $Addon" }
    $script = Join-Path $directory.FullName 'Workbench\workbench.py'
    if (-not [IO.File]::Exists($script)) { throw "Workbench script missing: $script" }
    $python = Find-Python $directory $sourceCheckout
    if (-not $python) { throw 'No working Python 3.9+ found. Set FAUST_LAUNCHER_ROOT or add Python to PATH.' }
    Write-Host "Python: $python"
    Write-Host "Workbench: $script"
    & $python $script --addon $directory.FullName
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("Workbench exited with code $LASTEXITCODE.")
        exit $LASTEXITCODE
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
