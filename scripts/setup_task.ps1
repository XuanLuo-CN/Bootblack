$root = 'D:\Git\Bootblack'
$py   = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }

$cfg    = "$root\config.yaml"
$aTime  = & $py -c "import yaml; c=yaml.safe_load(open(r'$cfg',encoding='utf-8')); print(c['schedule']['a_shares'])"
$usTime = & $py -c "import yaml; c=yaml.safe_load(open(r'$cfg',encoding='utf-8')); print(c['schedule']['us_stocks'])"

Write-Host "A股任务时间:  $aTime"
Write-Host "美股任务时间: $usTime"

function Register-BB($name, $time) {
    $script   = "$root\scripts\schedule.bat"
    $action   = New-ScheduledTaskAction -Execute $script
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $time
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "[OK] $name registered at $time"
}

Register-BB 'Bootblack-A股'  $aTime
Register-BB 'Bootblack-美股' $usTime

Write-Host ''
Write-Host 'Done. Check Task Scheduler Library for the two tasks.'