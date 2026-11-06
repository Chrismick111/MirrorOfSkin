$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$root=$PSScriptRoot
$path=Join-Path $root '自定义人格池.json'
$customStamp=(Get-FileHash -LiteralPath $path).Hash
$config=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
$pools=Get-Content -LiteralPath (Join-Path $root 'Assets/runtime/all_sinners_pools.json') -Raw -Encoding UTF8|ConvertFrom-Json
$form=New-Object Windows.Forms.Form
$form.Text='跨角色自定义人格池';$form.Size=New-Object Drawing.Size(960,720);$form.StartPosition='CenterScreen'
$target=New-Object Windows.Forms.ComboBox;$target.DropDownStyle='DropDownList';$target.SetBounds(20,15,230,30)
$names=@('李箱','浮士德','堂吉诃德','良秀','默尔索','鸿璐','希斯克利夫','以实玛利','罗佳','辛克莱','奥提斯','格里高尔')
for($i=0;$i -lt 12;$i++){[void]$target.Items.Add(('{0} {1}' -f (101+$i),$names[$i]))}
$form.Controls.Add($target)
$enabled=New-Object Windows.Forms.CheckBox;$enabled.Text='此角色使用自定义池';$enabled.SetBounds(280,15,230,30);$form.Controls.Add($enabled)
$hint=New-Object Windows.Forms.Label;$hint.Text='权重0不抽取；保存当前角色后再切换角色。保存后完全重启游戏和启动器生效。跨角色特写兼容性尚待实测。';$hint.SetBounds(20,52,900,40);$form.Controls.Add($hint)
$grid=New-Object Windows.Forms.DataGridView;$grid.SetBounds(20,95,900,515);$grid.AllowUserToAddRows=$false;$grid.AllowUserToDeleteRows=$false;$grid.AutoSizeColumnsMode='Fill';$grid.RowHeadersVisible=$false
foreach($c in @('ID','人格名称','来源角色','权重')){[void]$grid.Columns.Add($c,$c)}
for($i=0;$i -lt 3;$i++){$grid.Columns[$i].ReadOnly=$true}
$catalog=@();foreach($prop in $pools.PSObject.Properties){foreach($e in $prop.Value.entries){$catalog+=@{entry=$e;source=$prop.Name}}}
$form.Controls.Add($grid)
$load={
 $key=[string](101+$target.SelectedIndex);$profile=$config.characters.PSObject.Properties[$key];$selected=@{}
 if($profile){$enabled.Checked=[bool]$profile.Value.enabled;foreach($e in $profile.Value.entries){$selected[[string]$e.identity_id]=$e.weight}}else{$enabled.Checked=$false}
 $grid.Rows.Clear();foreach($item in $catalog){$e=$item.entry;$w=0;if($selected.ContainsKey([string]$e.identity_id)){$w=$selected[[string]$e.identity_id]};[void]$grid.Rows.Add([string]$e.identity_id,[string]$e.name,[string]$item.source,$w)}
}
$target.Add_SelectedIndexChanged($load)
$save=New-Object Windows.Forms.Button;$save.Text='保存当前角色';$save.SetBounds(700,625,220,36);$form.Controls.Add($save)
$save.Add_Click({try{
 if((Get-FileHash -LiteralPath $path).Hash -ne $customStamp){throw '概率窗口已修改了自定义池，请重新打开此窗口后编辑。'}
 $grid.EndEdit();$entries=@();foreach($row in $grid.Rows){$w=0.0;if(-not [double]::TryParse([string]$row.Cells[3].Value,[ref]$w) -or [double]::IsNaN($w) -or [double]::IsInfinity($w) -or $w -lt 0 -or $w -gt 1000000){throw '权重必须为0到1000000的有限数字'};if($w -gt 0){$entries+=@{identity_id=[string]$row.Cells[0].Value;weight=$w}}}
 if($enabled.Checked -and $entries.Count -eq 0){throw '请至少给一个人格设置正权重'}
 if($entries.Count -gt 256){throw '每个池最多256个人格'}
 $key=[string](101+$target.SelectedIndex);$config.characters|Add-Member -MemberType NoteProperty -Name $key -Value @{enabled=$enabled.Checked;entries=$entries} -Force
 $json=$config|ConvertTo-Json -Depth 12;[IO.File]::WriteAllText($path+'.tmp',$json,(New-Object Text.UTF8Encoding($false)));Move-Item -LiteralPath ($path+'.tmp') -Destination $path -Force
 $script:customStamp=(Get-FileHash -LiteralPath $path).Hash
 [void][Windows.Forms.MessageBox]::Show('已保存。完全重启游戏和启动器后生效。','自定义池')
}catch{[void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'保存失败')}})
$target.SelectedIndex=0
[void]$form.ShowDialog()
