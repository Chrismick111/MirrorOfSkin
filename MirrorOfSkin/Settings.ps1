param([switch]$ValidateOnly)
if($ValidateOnly){
 $root=$PSScriptRoot
 $data=Get-Content -LiteralPath (Join-Path $root 'Assets/runtime/all_sinners_pools.json') -Raw -Encoding UTF8|ConvertFrom-Json
 $count=0;$stories=0
 foreach($pool in $data.PSObject.Properties){foreach($e in $pool.Value.entries){$count++;if($e.story_metadata){$stories++}}}
 Write-Output "Native settings data valid: entries=$count storyEntries=$stories";return
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$root=$PSScriptRoot
$poolPath=Join-Path $root 'Assets/runtime/all_sinners_pools.json'
$settingsPath=Join-Path $root '随机设置.json'
$formNotes=@{};$formNotice='理智、体力和守备次数取当前出战角色；只改变外观。守备包括闪避、防御和反击。'
$notePath=Join-Path $root 'Assets/runtime/form_annotations.json'
if(Test-Path -LiteralPath $notePath){
 try{
  $notes=Get-Content -LiteralPath $notePath -Raw -Encoding UTF8|ConvertFrom-Json
  foreach($item in $notes.entries.PSObject.Properties){$formNotes[$item.Name]=$item.Value}
  $formNotice=$notes.notice
 }catch{}
}
$pools=Get-Content -LiteralPath $poolPath -Raw -Encoding UTF8 | ConvertFrom-Json
$customPath=Join-Path $root '自定义人格池.json'
$custom=Get-Content -LiteralPath $customPath -Raw -Encoding UTF8|ConvertFrom-Json
$customStamp=(Get-FileHash -LiteralPath $customPath).Hash
$catalog=@{};foreach($p in $pools.PSObject.Properties){foreach($e in $p.Value.entries){$catalog[[string]$e.identity_id]=$e}}
foreach($p in $custom.characters.PSObject.Properties){if($p.Value.enabled){
 $entries=@();foreach($selected in $p.Value.entries){$id=[string]$selected.identity_id;if(-not $catalog.ContainsKey($id)){throw ('自定义池含未知人格：'+$id)};$entry=$catalog[$id]|ConvertTo-Json -Depth 20|ConvertFrom-Json;$entry.weight=$selected.weight;$entries+=$entry}
 $pools.($p.Name).entries=$entries
}}

$settings=if(Test-Path -LiteralPath $settingsPath){Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8|ConvertFrom-Json}else{[pscustomobject]@{enabled=$true;characters=[pscustomobject]@{}}}
$autoNotePath=Join-Path $root 'auto_form_annotations.json'
if(Test-Path -LiteralPath $autoNotePath){
 try{
  $autoNotes=Get-Content -LiteralPath $autoNotePath -Raw -Encoding UTF8|ConvertFrom-Json
  foreach($item in $autoNotes.entries.PSObject.Properties){if(-not $formNotes.ContainsKey($item.Name)){$formNotes[$item.Name]=$item.Value}}
 }catch{}
}
# Include identities already discovered by the running component, retaining its authoritative entries.
$logPath=Join-Path $root '随机动作日志.txt'
if(Test-Path -LiteralPath $logPath){
 foreach($line in [IO.File]::ReadLines($logPath)){
  if($line -notmatch '"pool-auto-added"'){continue}
  try{
   $m=($line|ConvertFrom-Json).message
   $pool=$pools.PSObject.Properties[[string]$m.sinner]
   if($pool -and $m.entry -and [string]$m.entry.identity_id -match ('^'+[regex]::Escape([string]$m.sinner)+'\d{2}$') -and $pool.Value.entries.identity_id -notcontains $m.entry.identity_id){$pool.Value.entries=@($pool.Value.entries)+@($m.entry)}
  }catch{}
 }
}
# Refresh localized names every time the window opens, without changing weights.
$nameTables=@{zh=@{};en=@{}}
function Read-IdentityNames($directory,$pattern,$target){
 if(-not (Test-Path -LiteralPath $directory)){return}
 foreach($file in Get-ChildItem -LiteralPath $directory -Filter $pattern -File){
  try{
   $data=Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8|ConvertFrom-Json
   foreach($row in $data.dataList){
    $id=[string]$row.id
    if($id -notmatch '^1(?:0[1-9]|1[0-2])\d{2}$'){continue}
    $title=([string]$row.title -replace '<[^>]+>','' -replace '\s+',' ').Trim()
    $person=([string]$row.name -replace '<[^>]+>','' -replace '\s+',' ').Trim()
    if($title -and $person){$target[$id]=($title+' '+$person)}
   }
  }catch{}
 }
}
try{
 $runtimeConfig=Get-Content -LiteralPath (Join-Path $root 'Assets/runtime/config.json') -Raw -Encoding UTF8 -ErrorAction Stop|ConvertFrom-Json
 $gameData=Join-Path $runtimeConfig.game_dir 'LimbusCompany_Data'
 Read-IdentityNames (Join-Path $gameData 'Assets/Resources_moved/Localize/en') 'EN_Personalities*.json' $nameTables.en
 Read-IdentityNames (Join-Path $gameData 'Lang/LLC_zh-CN') 'Personalities*.json' $nameTables.zh
}catch{}
foreach($property in $pools.PSObject.Properties){
 foreach($entry in $property.Value.entries){
  $id=[string]$entry.identity_id
  $display=if($nameTables.zh.ContainsKey($id)){$nameTables.zh[$id]}elseif($nameTables.en.ContainsKey($id)){$nameTables.en[$id]}else{$entry.name}
  if(-not $display -or $display -eq $id){$display=([string]$entry.appearance_name -replace '^\d+_','' -replace 'Appearance$','' -replace '_',' ')}
  $entry|Add-Member -NotePropertyName name -NotePropertyValue $display -Force
 }
}
$form=New-Object Windows.Forms.Form
$form.Text='全角色随机人格 Native · 概率与形态说明'
$form.ClientSize=New-Object Drawing.Size(900,650)
$form.MinimumSize=New-Object Drawing.Size(900,500)
$form.StartPosition='CenterScreen'; $form.AutoScaleMode='None'
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$total=New-Object Windows.Forms.CheckBox
$total.Text='启用人格随机';$total.Checked=$settings.enabled -ne $false;$total.SetBounds(18,12,220,28)
$form.Controls.Add($total)
$hint=New-Object Windows.Forms.Label
$hint.Text='0 = 不抽取。保存后约1秒更新。形态条件见右侧；守备含闪避／防御／反击，均取出战角色。新增人格重开窗口可见。'
$hint.SetBounds(18,46,860,30);$form.Controls.Add($hint)
$formHelp=New-Object Windows.Forms.Label
$formHelp.Text='形态按本场累计守备次数推进，切换人格不重置；满足条件后等待动作空闲。仅外观变化，不赋予同名状态或被动。'
$formHelp.AutoEllipsis=$true;$form.Controls.Add($formHelp)
$formHelpTip=New-Object Windows.Forms.ToolTip;$formHelpTip.SetToolTip($formHelp,$formNotice)
$preloadLabel=New-Object Windows.Forms.Label
$preloadLabel.Text='队伍外观准备：进入战斗后，请在行动前等待准备完成。';$preloadLabel.AutoEllipsis=$true
$form.Controls.Add($preloadLabel)
$preloadTimer=New-Object Windows.Forms.Timer;$preloadTimer.Interval=1000
$preloadTimer.Add_Tick({
 try{
  $saved=Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8|ConvertFrom-Json
  if($saved.enabled -eq $false){$preloadLabel.Text='队伍外观准备：随机已停用，启用并保存后开始准备。';return}
  $path=Join-Path $root 'warmup_status.json'
  if(-not (Test-Path -LiteralPath $path)){$preloadLabel.Text='队伍外观准备：等待进入战斗并读取队伍。';return}
  $warm=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
  $ids=@(Get-Process -Name LimbusCompany -ErrorAction SilentlyContinue|ForEach-Object {$_.Id})
  if($ids -notcontains [int]$warm.pid){$preloadLabel.Text='队伍外观准备：等待当前游戏。';return}
  if($warm.units -eq 0){$preloadLabel.Text=if($warm.roster -gt 0){'当前队伍无可随机的已启用角色（全部关闭或受特殊外观保护）。'}else{'队伍外观准备：等待战斗队伍出现。'};return}
  if($warm.complete){$preloadLabel.ForeColor=[Drawing.Color]::DarkGreen;$preloadLabel.Text=('已启用队员{0}人：外观{1}/{2}已准备，可以开始行动。跳过失败：{3}' -f $warm.units,$warm.ready,$warm.total,$warm.failed)}
  else{$preloadLabel.ForeColor=[Drawing.Color]::DarkBlue;$preloadLabel.Text=('已启用队员{0}人：外观准备中{1}/{2}。请先等待，以便逐硬币切换。' -f $warm.units,$warm.ready,$warm.total)}
 }catch{$preloadLabel.Text='队伍外观准备：等待状态更新。'}
})
$preloadTimer.Start();$form.Add_FormClosed({$preloadTimer.Stop();$preloadTimer.Dispose()})

$tabs=New-Object Windows.Forms.TabControl; $tabs.Multiline=$true
$tabs.SetBounds(18,80,864,492);$tabs.Anchor='Top,Bottom,Left,Right';$form.Controls.Add($tabs)
$grids=@{};$checks=@{}
function Update-Percent($grid){
 $sum=0.0
 foreach($row in $grid.Rows){$number=0.0;if(-not $row.Tag -and [double]::TryParse([string]$row.Cells['weight'].Value,[ref]$number)-and $number -ge 0){$sum+=$number}}
 foreach($row in $grid.Rows){$number=0.0;[void][double]::TryParse([string]$row.Cells['weight'].Value,[ref]$number);$row.Cells['chance'].Value=if($row.Tag){'不可用'}elseif($sum -gt 0){'{0:0.00}%' -f (100*$number/$sum)}else{'0.00%'}}
}
foreach($property in $pools.PSObject.Properties){
 $key=$property.Name;$pool=$property.Value
 $page=New-Object Windows.Forms.TabPage;$page.Text=$pool.name;[void]$tabs.TabPages.Add($page)
 $check=New-Object Windows.Forms.CheckBox;$check.Text='启用此角色随机';$check.SetBounds(12,8,220,28)
 $old=if($settings.characters){$settings.characters.PSObject.Properties[$key]}else{$null};$check.Checked=$null -eq $old -or $old.Value -ne $false
 $checks[$key]=$check;$page.Controls.Add($check)
 $grid=New-Object Windows.Forms.DataGridView;$grid.SetBounds(10,42,830,390);$grid.Anchor='Top,Bottom,Left,Right'
 $grid.AllowUserToAddRows=$false;$grid.AllowUserToDeleteRows=$false;$grid.RowHeadersVisible=$false;$grid.AutoSizeColumnsMode='Fill';$grid.BackgroundColor=[Drawing.Color]::White
 foreach($column in @(@('id','人格编号'),@('name','人格'),@('weight','权重'),@('chance','出现概率'),@('compat','Native状态'),@('form','形态与触发方法'))){[void]$grid.Columns.Add($column[0],$column[1]);$grid.Columns[$column[0]].SortMode='NotSortable'}
 $grid.Columns['id'].ReadOnly=$true;$grid.Columns['id'].Visible=$false;$grid.EditMode='EditOnEnter';$grid.MultiSelect=$false;$grid.SelectionMode='FullRowSelect';$grid.Columns['name'].ReadOnly=$true;$grid.Columns['chance'].ReadOnly=$true
 $grid.Columns['name'].FillWeight=210;$grid.Columns['name'].MinimumWidth=175
 $grid.Columns['weight'].FillWeight=55;$grid.Columns['weight'].MinimumWidth=55
 $grid.Columns['chance'].FillWeight=70;$grid.Columns['chance'].MinimumWidth=70
 $grid.Columns['compat'].FillWeight=80;$grid.Columns['compat'].MinimumWidth=80;$grid.Columns['compat'].ReadOnly=$true
 $grid.Columns['form'].FillWeight=370;$grid.Columns['form'].MinimumWidth=320;$grid.Columns['form'].ReadOnly=$true
 $grid.Columns['form'].DefaultCellStyle.WrapMode='True'
 $grid.AutoSizeRowsMode='AllCells';$grid.ShowCellToolTips=$true
 foreach($entry in $pool.entries){
  $weight=if($null -ne $entry.PSObject.Properties['weight']){$entry.weight}else{1}
  $story=[bool]$entry.story_metadata
  $note=$formNotes[[string]$entry.identity_id]
  $description=if($note){([string]$note.forms)+[Environment]::NewLine+([string]$note.method)}else{'—'}
  if($note -and $note.supported -eq $false){$description='【形态未支持】'+[Environment]::NewLine+$description}
  $rowIndex=$grid.Rows.Add([string]$entry.identity_id,[string]$entry.name,$weight,'',$(if($story){'剧情：候选支持'}else{'可参与抽取'}),$description)
  if($note){$grid.Rows[$rowIndex].Cells['form'].ToolTipText=$description+[Environment]::NewLine+$formNotice}
  $grid.Rows[$rowIndex].Tag=$false
  if($story){$grid.Rows[$rowIndex].DefaultCellStyle.ForeColor=[Drawing.Color]::DarkCyan}
 }
 $grid.Add_CellValidating({param($sender,$e)
  if($e.ColumnIndex -ne 2){return};$value=0.0
  if(-not [double]::TryParse([string]$e.FormattedValue,[ref]$value) -or [double]::IsNaN($value) -or [double]::IsInfinity($value) -or $value -lt 0 -or $value -gt 1000000){$e.Cancel=$true;$sender.Rows[$e.RowIndex].ErrorText='请输入 0 至 1000000 的数字。'}else{$sender.Rows[$e.RowIndex].ErrorText=''}
 })
 $grid.Add_CellEndEdit({param($sender,$e) Update-Percent $sender})
 $grids[$key]=$grid;$page.Controls.Add($grid);Update-Percent $grid
}
$reset=New-Object Windows.Forms.Button;$reset.Text='当前角色恢复均等';$reset.SetBounds(18,590,180,36);$reset.Anchor='Bottom,Left'
$reset.Add_Click({foreach($key in $grids.Keys){if($grids[$key].Parent -eq $tabs.SelectedTab){foreach($row in $grids[$key].Rows){if(-not $row.Tag){$row.Cells['weight'].Value=1}};Update-Percent $grids[$key]}}});$form.Controls.Add($reset)
$status=New-Object Windows.Forms.Label;$status.Text='保存后自动更新；下一次随机抽取生效。';$status.SetBounds(215,596,430,28);$status.Anchor='Bottom,Left';$form.Controls.Add($status)
$save=New-Object Windows.Forms.Button;$save.Text='保存设置';$save.SetBounds(730,590,150,36);$save.Anchor='Bottom,Right';$form.Controls.Add($save)
$saveAction={
 try{
  if(-not $form.ValidateChildren()){throw '请先修正无效的权重。'}
  if((Get-FileHash -LiteralPath $customPath).Hash -ne $customStamp){throw '自定义池已被其他窗口修改，请关闭并重新打开概率窗口。'}
  $characters=@{}
  $latestPools=Get-Content -LiteralPath $poolPath -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach($key in $grids.Keys){
   $grid=$grids[$key];[void]$grid.EndEdit();$sum=0.0;$weights=@{}
   foreach($row in $grid.Rows){$weight=[double]$row.Cells['weight'].Value;if([double]::IsNaN($weight)-or [double]::IsInfinity($weight)-or $weight -lt 0 -or $weight -gt 1000000){throw '权重超出有效范围。'};$weights[[string]$row.Cells['id'].Value]=$weight;if(-not $row.Tag){$sum+=$weight}}
   if($total.Checked -and $checks[$key].Checked -and $sum -le 0){throw ($pools.$key.name+'至少需要一个人格的权重大于 0。')}
   $profile=$custom.characters.PSObject.Properties[$key]
   if($profile -and $profile.Value.enabled){
    foreach($entry in $profile.Value.entries){if($weights.ContainsKey([string]$entry.identity_id)){$entry.weight=$weights[[string]$entry.identity_id]}}
   }else{
   foreach($entry in $latestPools.$key.entries){if($weights.ContainsKey([string]$entry.identity_id)){$entry|Add-Member -NotePropertyName weight -NotePropertyValue $weights[[string]$entry.identity_id] -Force}}
   }
   $characters[$key]=$checks[$key].Checked
  }
  $settings|Add-Member -NotePropertyName enabled -NotePropertyValue $total.Checked -Force
  $settings|Add-Member -NotePropertyName characters -NotePropertyValue $characters -Force
  $utf8=New-Object Text.UTF8Encoding($false)
  $ctemp=$customPath+'.tmp';[IO.File]::WriteAllText($ctemp,($custom|ConvertTo-Json -Depth 20),$utf8);[IO.File]::Replace($ctemp,$customPath,$customPath+'.bak')
  $script:customStamp=(Get-FileHash -LiteralPath $customPath).Hash

  $temp=$poolPath+'.weights.tmp';[IO.File]::WriteAllText($temp,($latestPools|ConvertTo-Json -Depth 20),$utf8);[IO.File]::Replace($temp,$poolPath,($poolPath+'.weights.bak'))
  $temp=$settingsPath+'.tmp';[IO.File]::WriteAllText($temp,($settings|ConvertTo-Json -Depth 20),$utf8)
  if(Test-Path -LiteralPath $settingsPath){[IO.File]::Replace($temp,$settingsPath,($settingsPath+'.bak'))}else{[IO.File]::Move($temp,$settingsPath)}
  if(-not $total.Checked){[IO.File]::WriteAllText((Join-Path $root '停止随机运行.flag'),'')}else{Remove-Item -LiteralPath (Join-Path $root '停止随机运行.flag') -ErrorAction SilentlyContinue}
  $status.Text='已保存。概率将在约1秒内更新，下一次抽取生效。'
 }catch{[void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'保存失败')}
}
$save.Add_Click($saveAction)
function Current-GridKey {
 foreach($key in $grids.Keys){if($grids[$key].Parent -eq $tabs.SelectedTab){return $key}}
}
function Select-OnlyIdentity($key,$identity){
 $grid=$grids[$key];[void]$grid.EndEdit()
 $chosen=@($grid.Rows | Where-Object {[string]$_.Cells['id'].Value -eq $identity})
 if($chosen.Count -ne 1 -or $chosen[0].Tag){throw '请选择 Native 支持的人格。'}
 foreach($row in $grid.Rows){if(-not $row.Tag){$row.Cells['weight'].Value=if([string]$row.Cells['id'].Value -eq $identity){1}else{0}}}
 $checks[$key].Checked=$true;$total.Checked=$true;Update-Percent $grid
}
$only=New-Object Windows.Forms.Button;$only.Text='仅抽选中人格'
$only.Add_Click({try{$key=Current-GridKey;$grid=$grids[$key];if(-not $grid.CurrentRow){throw '请先点选一个人格。'};Select-OnlyIdentity $key ([string]$grid.CurrentRow.Cells['id'].Value);$status.Text='已设为当前角色仅抽选中人格，尚未保存。'}catch{[void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'设置提示')}});$form.Controls.Add($only)
$onlyRole=New-Object Windows.Forms.Button;$onlyRole.Text='仅启用当前角色'
$onlyRole.Add_Click({$key=Current-GridKey;foreach($k in $checks.Keys){$checks[$k].Checked=($k -eq $key)};$total.Checked=$true;$status.Text='已仅启用当前角色，其他角色保持本体；尚未保存。'});$form.Controls.Add($onlyRole)
function Fit-SettingsLayout {
 $w=$form.ClientSize.Width;$h=$form.ClientSize.Height
 $hint.SetBounds(16,44,($w-32),42)
 $formHelp.SetBounds(16,82,($w-32),40)
 $preloadLabel.SetBounds(16,124,($w-32),26)
 $tabs.SetBounds(16,154,($w-32),($h-254))
 foreach($grid in $grids.Values){
  $page=$grid.Parent
  $grid.Anchor='Top,Left'
  $grid.SetBounds(8,40,([math]::Max(200,$page.ClientSize.Width-16)),([math]::Max(100,$page.ClientSize.Height-48)))
 }
 $reset.SetBounds(16,($h-86),180,34)
 $status.SetBounds(16,($h-43),([math]::Max(100,$w-32)),30)
 $only.SetBounds(202,($h-86),140,34)
 $onlyRole.SetBounds(348,($h-86),150,34)
 $save.SetBounds(($w-156),($h-86),140,34)
}
$area=[Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.ClientSize=New-Object Drawing.Size(([math]::Min(900,$area.Width-60)),([math]::Min(650,$area.Height-100)))
foreach($control in @($tabs,$reset,$only,$onlyRole,$status,$save)){$control.Anchor='Top,Left'}
$form.Add_Resize({Fit-SettingsLayout})
$tabs.Add_SelectedIndexChanged({Fit-SettingsLayout})
$form.Add_Shown({Fit-SettingsLayout;$form.Activate()})
[void]$form.ShowDialog();$form.Dispose()

