param([string]$AddonRoot=$PSScriptRoot,[string]$OutputDirectory=$AddonRoot)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root=[IO.Path]::GetFullPath($AddonRoot)
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$zipPath=Join-Path $OutputDirectory "随机人格诊断-$stamp.zip"
$names=@('native.log','native_runtime.log','诊断日志.txt','诊断日志-上一份.txt','addon_info.json','compatibility.json','随机设置.json','自定义人格池.json','warmup_status.json','native_pools.bin','native_forms.json','auto_registry.json')
$report=New-Object 'System.Collections.Generic.List[string]'
$report.Add("生成时间：$(Get-Date -Format o)")
$report.Add('请补充：出战人格、使用的技能、异常硬币/拼点次数、是否卡顿，以及问题出现时间。')
$report.Add('本包包含插件日志、概率/自定义池设置与版本信息，不读取存档或账号信息。')
$zip=[IO.Compression.ZipFile]::Open($zipPath,[IO.Compression.ZipArchiveMode]::Create)
try {
 foreach($name in $names){
  $path=Join-Path $root $name
  if(-not (Test-Path -LiteralPath $path -PathType Leaf)){$report.Add("缺少：$name");continue}
  $inputStream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
  try {
   # Bound live log snapshots to the last 8 MiB; do not race a growing log forever.
   $length=$inputStream.Length
   $start=if($name.EndsWith('.log') -or $name.Contains('诊断日志')){[Math]::Max(0,$length-8MB)}else{0}
   $null=$inputStream.Seek($start,[IO.SeekOrigin]::Begin)
   $entry=$zip.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal)
   $output=$entry.Open()
   try {
    $remaining=$length-$start;$buffer=New-Object byte[] 65536
    while($remaining -gt 0){$n=$inputStream.Read($buffer,0,[int][Math]::Min($remaining,$buffer.Length));if($n -eq 0){break};$output.Write($buffer,0,$n);$remaining-=$n}
   }finally{$output.Dispose()}
   $report.Add("已收集：$name 原始字节=$length 起始偏移=$start")
  }finally{$inputStream.Dispose()}
 }
 $compat=Get-Content -LiteralPath (Join-Path $root 'compatibility.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 $report.Add("安装版本=$($compat.version) 协议=$($compat.protocol) DLL=$($compat.dll)")
 foreach($name in @('scr.py',$compat.dll)){
  $path=Join-Path $root $name
  if(Test-Path -LiteralPath $path){$report.Add("SHA256 $name $((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash)")}
 }
 $entry=$zip.CreateEntry('反馈说明与文件校验.txt')
 $writer=New-Object IO.StreamWriter($entry.Open(),(New-Object Text.UTF8Encoding($true)))
 try{$writer.Write(($report -join "`r`n"))}finally{$writer.Dispose()}
}finally{$zip.Dispose()}
Write-Output "诊断包已生成：$zipPath"
