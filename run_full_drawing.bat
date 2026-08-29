@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem Full-drawing compute pipeline only (no DXF export, no verification PNGs).
rem Export JSON first with an explicit config, e.g.:
rem   python batch_export_test_input.py --src 2026.1-1 --cfg test_input\2016_config.json --with-legend
rem Partial drawings: run_stats.bat
rem
rem Usage:
rem   run_full_drawing.bat --src 2026.1-1
rem   run_full_drawing.bat --src 2026.1-2\2026.1-2
rem   run_full_drawing.bat --src 2026.1-2\2026.1-2 --output-root D:\out
rem
rem --src = DXF path relative to code root (with or without .dxf).
rem         Also accepts test_input\{name}.dxf as fallback.
rem Python calls use --stem=<basename> only. Default out: {stem}_output\

set "CODE_ROOT=%~dp0"
set "TEST_INPUT=%CODE_ROOT%test_input"
set "SRC="
set "OUTPUT_ROOT="

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--src" (
  if "%~2"=="" (
    echo Missing value for --src
    exit /b 1
  )
  set "SRC=%~2"
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--output-root" (
  if "%~2"=="" (
    echo Missing value for --output-root
    exit /b 1
  )
  set "OUTPUT_ROOT=%~2"
  shift
  shift
  goto parse_args
)
echo Unknown argument: %~1
echo Usage: run_full_drawing.bat --src ^<path^> [--output-root DIR]
echo Example: run_full_drawing.bat --src 2026.1-1
echo Example: run_full_drawing.bat --src 2026.1-2\2026.1-2
exit /b 1

:args_done
if not defined SRC (
  echo Usage: run_full_drawing.bat --src ^<path^> [--output-root DIR]
  echo Example: run_full_drawing.bat --src 2026.1-1
  echo Example: run_full_drawing.bat --src 2026.1-2\2026.1-2
  exit /b 1
)

if not exist "%TEST_INPUT%\" (
  echo Missing folder: %TEST_INPUT%
  exit /b 1
)

set "REL=%SRC%"
set "REL=%REL:/=\%"
if /I "%REL:~-4%"==".dxf" set "REL=%REL:~0,-4%"

set "DXF="
if exist "%CODE_ROOT%%REL%.dxf" set "DXF=%CODE_ROOT%%REL%.dxf"
if not defined DXF if exist "%CODE_ROOT%%REL%.DXF" set "DXF=%CODE_ROOT%%REL%.DXF"
if not defined DXF if exist "%TEST_INPUT%\%REL%.dxf" set "DXF=%TEST_INPUT%\%REL%.dxf"
if not defined DXF if exist "%TEST_INPUT%\%REL%.DXF" set "DXF=%TEST_INPUT%\%REL%.DXF"
if not defined DXF (
  echo Missing DXF: %CODE_ROOT%%REL%.dxf
  echo Also tried: %TEST_INPUT%\%REL%.dxf
  exit /b 1
)

for %%I in ("%DXF%") do (
  set "STEM=%%~nI"
)
if "%OUTPUT_ROOT%"=="" (
  set "OUT=%CODE_ROOT%%STEM%_output"
) else (
  set "OUT=%OUTPUT_ROOT%\%STEM%_output"
)

set "LEGEND_JSON=%TEST_INPUT%\%STEM%-图例.json"
set "GEO_JSON=%TEST_INPUT%\%STEM%-巷道.json"
set "TEXT_JSON=%TEST_INPUT%\%STEM%-文字.json"
set "FACILITY_JSON=%TEST_INPUT%\%STEM%-设施.json"

if not exist "%GEO_JSON%" (
  echo Missing %GEO_JSON%
  echo Export first: python batch_export_test_input.py --src %REL% --cfg ^<export-config.json^> --with-legend
  exit /b 1
)
if not exist "%LEGEND_JSON%" (
  echo Missing legend JSON: %LEGEND_JSON%
  echo Export first: python batch_export_test_input.py --src %REL% --cfg ^<export-config.json^> --with-legend
  exit /b 1
)

echo.
echo ========== FULL DRAWING %STEM% ^(%REL%^) -^> %OUT% ==========

set "S529_2=%OUT%\529-stage2"
set "S2A_RAW=%S529_2%\step2A\raw"
set "S2A_OUT=%S529_2%\step2A\output"
set "S2B_OUT=%S529_2%\step2B\output"
set "S529_3=%OUT%\529-stage3"
set "S3A_OUT=%S529_3%\step3A\output"
set "S3B_OUT=%S529_3%\step3B\output"
set "S529_4=%OUT%\529-stage4"
set "S714_1=%OUT%\714-stage1"
set "S714_2=%OUT%\714-stage2"
set "STRUCTURE_PKL=%S529_4%\%STEM%_structure_graph.pkl"
set "TEXTS_PKL=%S714_1%\%STEM%-structure_graph_with_texts.pkl"

mkdir "%S2A_RAW%" 2>nul
mkdir "%S2A_OUT%" 2>nul
mkdir "%S2B_OUT%" 2>nul
mkdir "%S3A_OUT%" 2>nul
mkdir "%S3B_OUT%" 2>nul
mkdir "%S529_4%" 2>nul
mkdir "%S714_1%" 2>nul
mkdir "%S714_2%" 2>nul

echo [1/2] 5.29 geometry pipeline
cd /d "%CODE_ROOT%5.29" || exit /b 1

python step2A\run_init_graph.py --geo "%GEO_JSON%" --stem=%STEM% --raw "%S2A_RAW%"
if errorlevel 1 exit /b 1
python step2A\square_bend.py --stem=%STEM% --raw "%S2A_RAW%" --output "%S2A_OUT%"
if errorlevel 1 exit /b 1
python step2A\arc_bend_detect.py --stem=%STEM% --raw "%S2A_RAW%" --output "%S2A_OUT%"
if errorlevel 1 exit /b 1
python step2A\arc_normalize.py --stem=%STEM% --raw "%S2A_RAW%" --output "%S2A_OUT%"
if errorlevel 1 exit /b 1
python step2A\merge_normalized_geometry.py --stem=%STEM% --output "%S2A_OUT%"
if errorlevel 1 exit /b 1
python step2A\build_normalized_graph.py --stem=%STEM% --output "%S2A_OUT%"
if errorlevel 1 exit /b 1
rem 整图跳过核对位图（局部图 run_stats 仍出图）

python step2B\run_straight_wall.py --stem=%STEM% --step2a "%S2A_OUT%" --output "%S2B_OUT%" --short-length-scale 5 --no-vis
if errorlevel 1 exit /b 1
python step2B\build_parallel_graph.py --stem=%STEM% --step2a "%S2A_OUT%" --output "%S2B_OUT%" --no-vis
if errorlevel 1 exit /b 1

python step3A\run_corridor_candidates.py --stem=%STEM% --step2b "%S2B_OUT%" --output "%S3A_OUT%" --no-vis
if errorlevel 1 exit /b 1
python step3A\build_centerline_graph.py --stem=%STEM% --output "%S3A_OUT%"
if errorlevel 1 exit /b 1

python step3B\build_residual_graph.py --stem=%STEM% --step2b "%S2B_OUT%" --step2a "%S2A_OUT%" --output "%S3B_OUT%" --no-vis
if errorlevel 1 exit /b 1
python step3B\pick_corridor_wall_candidates.py --stem=%STEM% --centerline-dir "%S3A_OUT%" --output "%S3B_OUT%" --no-vis
if errorlevel 1 exit /b 1
python step3B\fix_centerlines.py --stem=%STEM% --centerline-dir "%S3A_OUT%" --output "%S3B_OUT%" --no-vis
if errorlevel 1 exit /b 1

python step4A\classify_attached_regions.py --stem=%STEM% --step3b "%S3B_OUT%" --centerline "%S3A_OUT%" --output "%S529_4%" --no-vis
if errorlevel 1 exit /b 1
python step4B\build_corrected_centerlines.py --stem=%STEM% --step3b "%S3B_OUT%" --step4A "%S529_4%" --output "%S529_4%" --no-vis
if errorlevel 1 exit /b 1

echo [2/2] 7.14 annotation + facility ^(含整图专用：标注图例模板与识别规则^)
cd /d "%CODE_ROOT%7.14" || exit /b 1

python step1a\0_retrieved_elements_graph.py --stem=%STEM% --text-json "%TEXT_JSON%" --corridor-json "%GEO_JSON%" --output-dir "%S714_1%" --no-png
if errorlevel 1 exit /b 1
python step1a\1_extract_retrieval_templates.py --stem=%STEM% --legend-json "%LEGEND_JSON%" --output-dir "%S714_1%"
if errorlevel 1 exit /b 1
python step1a\2_retrieval_rules.py --stem=%STEM% --output-dir "%S714_1%"
if errorlevel 1 exit /b 1
python step1a\3_apply_retrieval_rules.py --stem=%STEM% --corridor-json "%GEO_JSON%" --output-dir "%S714_1%" --no-png
if errorlevel 1 exit /b 1
python step1a\4_final_clusters.py --stem=%STEM% --corridor-json "%GEO_JSON%" --output-dir "%S714_1%" --no-png
if errorlevel 1 exit /b 1

python step1b\0_structure_graph_with_texts.py --stem=%STEM% --structure-pkl "%STRUCTURE_PKL%" --step1a-output-dir "%S714_1%" --output-dir "%S714_1%"
if errorlevel 1 exit /b 1

python stage2\0_facility_primitives_graph.py --stem=%STEM% --facility-json "%FACILITY_JSON%" --output-dir "%S714_2%"
if errorlevel 1 exit /b 1
python stage2\2_build_facility_graph.py --stem=%STEM% --output-dir "%S714_2%"
if errorlevel 1 exit /b 1
python stage2\3_structure_graph_with_facilities.py --stem=%STEM% --structure-pkl "%TEXTS_PKL%" --output-dir "%S714_2%" --corridor-json "%GEO_JSON%" --no-png
if errorlevel 1 exit /b 1

cd /d "%CODE_ROOT%" || exit /b 1
python collect_pipeline_stats.py --stem=%STEM% --output-root "%OUT%"
if errorlevel 1 exit /b 1

echo.
echo Full drawing finished: %STEM%
echo Rules:     %S714_1%\%STEM%-retrieval_rules.json
echo Next: run_stats.bat --src %REL%
exit /b 0
