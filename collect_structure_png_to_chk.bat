@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem 将各 {图号}_output\714-stage2\*-structure_graph_with_facilities.png 复制到根目录 chk\
rem 用法：在代码根目录双击或运行 collect_structure_png_to_chk.bat

set "ROOT=%~dp0"
set "CHK=%ROOT%chk"

if not exist "%CHK%\" mkdir "%CHK%"

set "COUNT=0"
for /d %%D in ("%ROOT%*_output") do (
  if exist "%%~fD\714-stage2\" (
    for %%F in ("%%~fD\714-stage2\*-structure_graph_with_facilities.png") do (
      if exist "%%~fF" (
        copy /Y "%%~fF" "%CHK%\%%~nxF" >nul
        if not errorlevel 1 (
          echo OK  %%~nxF
          set /a COUNT+=1
        ) else (
          echo FAIL %%~fF
        )
      )
    )
  )
)

echo.
echo Copied %COUNT% file(s) → %CHK%
endlocal
exit /b 0
