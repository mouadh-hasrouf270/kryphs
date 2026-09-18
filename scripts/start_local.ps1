$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Follow docs/WINDOWS_LOCAL_SETUP.md first.' }
$logRoot = Join-Path $projectRoot 'local-logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Start-Process -FilePath $pythonPath -ArgumentList @('-u','manage.py','runserver','127.0.0.1:8017','--noreload') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'backend.log') -RedirectStandardError (Join-Path $logRoot 'backend-errors.log')
Start-Process -FilePath $pythonPath -ArgumentList @('-u','manage.py','run_worker') -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'worker.log') -RedirectStandardError (Join-Path $logRoot 'worker-errors.log')
Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c','npm.cmd run dev') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'frontend.log') -RedirectStandardError (Join-Path $logRoot 'frontend-errors.log')
Write-Output 'Open http://127.0.0.1:5173. Logs are in local-logs. This helper is for local development.'
