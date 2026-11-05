$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Remove-Item "$root\.v_*.txt" -ErrorAction SilentlyContinue
Set-Location "$root\frontend"
& node node_modules\typescript\bin\tsc --noEmit -p tsconfig.json *> "$root\.v_ts.txt"
"tsc exit $LASTEXITCODE" | Add-Content "$root\.v_ts.txt"
Set-Location "$root\backend"
& "$root\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider tests --tb=short *> "$root\.v_py.txt"
"pytest exit $LASTEXITCODE" | Add-Content "$root\.v_py.txt"
Set-Location "$root\frontend"
& node node_modules\vite\bin\vite.js build *> "$root\.v_build.txt"
"vite exit $LASTEXITCODE" | Add-Content "$root\.v_build.txt"
"done" | Set-Content "$root\.v_done.txt"
