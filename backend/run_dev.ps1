# run_dev.ps1 — Start uvicorn without watching .venv (prevents restart loops)
# Usage: .\run_dev.ps1

Set-Location $PSScriptRoot

uvicorn main:app `
    --reload `
    --reload-dir routers `
    --reload-dir utils `
    --host 127.0.0.1 `
    --port 8000
