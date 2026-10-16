$ErrorActionPreference = 'Stop'

if (-not (Get-Command netlify -ErrorAction SilentlyContinue)) {
    throw 'Netlify CLI topilmadi. O‘rnating: npm install -g netlify-cli'
}

netlify status *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Netlify CLI ga kiring (netlify login) va repozitoriy ildizidan netlify init bilan saytni ulang.'
}

$railwayApiUrl = Read-Host 'Railway API domeni (masalan, https://dormflow-api.up.railway.app)'
try {
    $parsedUrl = [Uri]$railwayApiUrl
    if ($parsedUrl.Scheme -ne 'https' -or $parsedUrl.AbsolutePath -ne '/' -or $parsedUrl.Query -or $parsedUrl.Fragment) {
        throw 'Faqat HTTPS domenining asosiy manzilini kiriting, /api yo‘lini qo‘shmang.'
    }
}
catch {
    throw "Railway domeni noto‘g‘ri: $($_.Exception.Message)"
}

$apiOrigin = $parsedUrl.GetLeftPart([System.UriPartial]::Authority)
netlify env:set RAILWAY_API_URL $apiOrigin
if ($LASTEXITCODE -ne 0) { throw 'RAILWAY_API_URL ni Netlify ga saqlab bo‘lmadi.' }

netlify deploy --prod --build
if ($LASTEXITCODE -ne 0) { throw 'Netlify build yoki production deploy muvaffaqiyatsiz tugadi.' }
