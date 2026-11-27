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
    Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class ImportPickerForeground {
    delegate bool EnumProc(IntPtr window, IntPtr state);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback, IntPtr state);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder name, int size);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
    public static bool RaiseDialog(IntPtr owner) {
        const uint GW_OWNER = 4, SWP_NOSIZE = 1, SWP_NOMOVE = 2;
        bool raised = false;
        EnumWindows((window, state) => {
            if (!IsWindowVisible(window) || GetWindow(window, GW_OWNER) != owner)
                return true;
            var name = new StringBuilder(64);
            GetClassName(window, name, name.Capacity);
            if (name.ToString() != "#32770")
                return true;
            raised = SetWindowPos(window, new IntPtr(-1), 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE);
            if (raised) SetForegroundWindow(window);
            return !raised;
        }, IntPtr.Zero);
        return raised;
    }
}
'@
    $picker=New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title='选择外观模组（按 Ctrl 或 Shift 可多选）'
    $picker.Filter='模组文件 (*.zip;*.7z;*.rar;*.bundle;*.carra2;*.bank)|*.zip;*.7z;*.rar;*.bundle;*.carra2;*.bank|所有文件 (*.*)|*.*'
    $picker.Multiselect=$true
    $picker.InitialDirectory=$addon
    $picker.RestoreDirectory=$true
    $owner=New-Object System.Windows.Forms.Form
    $owner.StartPosition='Manual'
    $area=[System.Windows.Forms.Screen]::FromPoint([System.Windows.Forms.Cursor]::Position).WorkingArea
    $owner.Location=[System.Drawing.Point]::new([int]($area.Left+$area.Width/2),[int]($area.Top+$area.Height/2))
    $owner.FormBorderStyle='None'
    $owner.Opacity=0
    $owner.Size=New-Object System.Drawing.Size(1,1)
    $owner.ShowInTaskbar=$false
    $owner.TopMost=$true
    $raiseTimer=New-Object System.Windows.Forms.Timer
    $raiseTimer.Interval=50
    $raiseTimer.Add_Tick({ if ([ImportPickerForeground]::RaiseDialog($owner.Handle)) { $raiseTimer.Stop() } })
    try {
        $owner.Show()
        $owner.Activate()
        $raiseTimer.Start()
        if ($picker.ShowDialog($owner) -ne 'OK') { exit 0 }
        $Archives=$picker.FileNames
    } finally { $raiseTimer.Stop(); $raiseTimer.Dispose(); $picker.Dispose(); $owner.Dispose() }
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
