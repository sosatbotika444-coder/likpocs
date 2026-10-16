$ErrorActionPreference = 'Stop'

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    throw 'Railway CLI topilmadi. O‘rnating: npm install -g @railway/cli'
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Node.js va npm kerak. Node.js 24 ni o‘rnating va qayta urinib ko‘ring.'
}

railway whoami *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Avval Railway hisobiga kiring: railway login'
}

railway status *> $null
if ($LASTEXITCODE -eq 0) {
    throw 'Bu papka Railway loyihasiga ulangan. Ma’lumotlar yo‘qolishining oldini olish uchun yangi, bo‘sh Railway loyihasini tanlang; .railway/railway.ts butun loyiha infratuzilmasini boshqaradi.'
}

railway init --name DormFlow
if ($LASTEXITCODE -ne 0) { throw 'Railway loyihasini yaratib bo‘lmadi.' }

$operatorEmail = Read-Host 'Birinchi OPERATOR email manzili'
if ([string]::IsNullOrWhiteSpace($operatorEmail)) { throw 'Operator email manzili kiritilishi shart.' }
$operatorName = Read-Host 'Operator ismi (bo‘sh qoldirilsa standart nom ishlatiladi)'
if ([string]::IsNullOrWhiteSpace($operatorName)) { $operatorName = 'Yotoqxona operatori' }
$securePassword = Read-Host 'Birinchi OPERATOR paroli (kamida 12 belgi)' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$operatorPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
if ($operatorPassword.Length -lt 12) {
    $operatorPassword = $null
    $securePassword.Dispose()
    throw 'Operator paroli kamida 12 belgidan iborat bo‘lishi kerak.'
}

$secretBytes = New-Object byte[] 48
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
$random.GetBytes($secretBytes)
$jwtSecret = [Convert]::ToBase64String($secretBytes)
[Array]::Clear($secretBytes, 0, $secretBytes.Length)
$random.Dispose()

$env:DORMFLOW_RAILWAY_JWT_SECRET = $jwtSecret
$env:DORMFLOW_INITIAL_OPERATOR_EMAIL = $operatorEmail
$env:DORMFLOW_INITIAL_OPERATOR_PASSWORD = $operatorPassword
$env:DORMFLOW_INITIAL_OPERATOR_NAME = $operatorName
try {
    npm.cmd ci --prefix .railway
    if ($LASTEXITCODE -ne 0) { throw 'Railway IaC bog‘liqliklarini o‘rnatib bo‘lmadi.' }

    railway config apply --yes
    if ($LASTEXITCODE -ne 0) { throw 'Railway resurslarini sozlash yoki deploy qilish muvaffaqiyatsiz tugadi.' }

railway domain --service dormflow-api
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'API domeni hali yaratilmagan. Deploy tayyor bo‘lgach railway domain --service dormflow-api buyrug‘ini qayta bajaring.'
}
}
finally {
    Remove-Item Env:DORMFLOW_RAILWAY_JWT_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:DORMFLOW_INITIAL_OPERATOR_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:DORMFLOW_INITIAL_OPERATOR_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:DORMFLOW_INITIAL_OPERATOR_NAME -ErrorAction SilentlyContinue
    $operatorPassword = $null
    $jwtSecret = $null
    $securePassword.Dispose()
}

Write-Host ''
Write-Host 'Railway API va PostgreSQL sozlandi. Chiqqan https://...up.railway.app manzilini Netlify dagi RAILWAY_API_URL qiymati sifatida kiriting.'
