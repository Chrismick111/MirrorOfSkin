param([switch]$OpenWorkbench,[switch]$PickOnly,[Parameter(Position=0,ValueFromRemainingArguments=$true)][string[]]$Archives)
$ErrorActionPreference='Stop'
$addon=Split-Path $PSScriptRoot -Parent
$launcher=Split-Path (Split-Path $addon -Parent) -Parent
$relative='resources\mod_loader\_internal\venv\Bins\python.exe'
$python=Join-Path $launcher $relative
if (-not (Test-Path -LiteralPath $python)) {
    $python=(Get-Command python.exe -ErrorAction Stop).Source
}
if ($OpenWorkbench) {
    & (Join-Path $PSScriptRoot 'ui/open_workbench.ps1')
    exit $LASTEXITCODE
}
if (-not $Archives) {
    Add-Type -AssemblyName System.Windows.Forms
    $picker=New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title='选择要加入本地工作台的外观模组'
    $picker.Filter='模组文件 (*.zip;*.7z;*.rar;*.carra2;*.bank)|*.zip;*.7z;*.rar;*.carra2;*.bank|所有文件 (*.*)|*.*'
    $picker.Multiselect=$true
    $picker.InitialDirectory=$addon
    $picker.RestoreDirectory=$true
    $owner=New-Object System.Windows.Forms.Form
    $owner.StartPosition='Manual'
    $owner.Location=New-Object System.Drawing.Point(-32000,-32000)
    $owner.Size=New-Object System.Drawing.Size(1,1)
    $owner.ShowInTaskbar=$false
    $owner.TopMost=$true
    try {
        $owner.Show()
        $owner.Activate()
        if ($picker.ShowDialog($owner) -ne 'OK') { exit 0 }
        $Archives=$picker.FileNames
    } finally { $picker.Dispose(); $owner.Dispose() }
}
if ($PickOnly) {
    [Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
    ConvertTo-Json -InputObject @($Archives) -Compress
    exit 0
}
$failures=0
foreach ($archive in $Archives) {
    Write-Host ('正在读取 '+[IO.Path]::GetFileName($archive)+'，较大的模型可能需要几分钟。')
    & $python -B -X utf8 (Join-Path $PSScriptRoot 'skin_import.py') --addon $addon $archive
    if ($LASTEXITCODE -ne 0) { $failures++ }
}
if ($failures) { exit 1 }
