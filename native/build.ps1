param(
    [Parameter(Mandatory=$true)][string]$Zig,
    [Parameter(Mandatory=$true)][string]$MinHook
)
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$mhsrc = Join-Path $MinHook 'src'
$includeArgs = @('-I',(Join-Path $MinHook 'include'),'-I',$source)
foreach($dir in Get-ChildItem -LiteralPath $source -Directory){
    $includeArgs += @('-I',$dir.FullName)
}
$buildArgs = @('cc','-target','x86_64-windows-gnu','-mcpu=baseline','-shared','-O1','-s') +
    $includeArgs + @((Join-Path $source 'sinners_native.c'),
    (Join-Path $mhsrc 'buffer.c'),(Join-Path $mhsrc 'hook.c'),
    (Join-Path $mhsrc 'trampoline.c'),(Join-Path $mhsrc 'hde\hde64.c'),(Join-Path $source 'unity\wic_rgba.c'),
    '-o',(Join-Path $source 'SinnersNative.dll'),'-luser32','-lbcrypt','-lole32','-luuid')
& $Zig @buildArgs
if ($LASTEXITCODE -ne 0) { throw "Native build failed: $LASTEXITCODE" }
