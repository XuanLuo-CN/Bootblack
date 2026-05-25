@echo off
set SCRIPT=D:\Git\Bootblack\scripts\schedule.bat

schtasks /create ^
  /tn "Bootblack-A股" ^
  /tr "%SCRIPT%" ^
  /sc WEEKLY ^
  /d MON,TUE,WED,THU,FRI ^
  /st 15:35 ^
  /ru %USERNAME% ^
  /f
if %errorlevel%==0 (
    echo [OK] Bootblack-A股 已注册：工作日 15:35
) else (
    echo [ERROR] Bootblack-A股 注册失败
)

schtasks /create ^
  /tn "Bootblack-美股" ^
  /tr "%SCRIPT%" ^
  /sc WEEKLY ^
  /d MON,TUE,WED,THU,FRI ^
  /st 05:05 ^
  /ru %USERNAME% ^
  /f
if %errorlevel%==0 (
    echo [OK] Bootblack-美股 已注册：工作日 05:05
) else (
    echo [ERROR] Bootblack-美股 注册失败
)

echo.
echo 注册完成。可在「任务计划程序」中查看和管理这两个任务。
pause
