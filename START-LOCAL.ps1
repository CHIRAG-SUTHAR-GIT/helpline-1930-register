$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Helpline 1930 - local SQLite test mode' -ForegroundColor Cyan
Write-Host 'This test stores records on this computer, not in GitHub.'
$operatorName = Read-Host 'Choose an operator username (letters/digits, 2-50 characters)'
$operatorSecurePassword = Read-Host 'Choose a password of at least 12 characters' -AsSecureString
$operatorPassword = [System.Net.NetworkCredential]::new('', $operatorSecurePassword).Password
if ($operatorPassword.Length -lt 12) { throw 'Password must be at least 12 characters.' }
$operatorAccounts = @{}
$operatorAccounts[$operatorName] = $operatorPassword
$env:USERS_JSON = ConvertTo-Json -InputObject $operatorAccounts -Compress
$secretBytes = New-Object byte[] 48
$secretGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$secretGenerator.GetBytes($secretBytes)
$secretGenerator.Dispose()
$env:SESSION_SECRET = [Convert]::ToBase64String($secretBytes)
$env:STORAGE_MODE = 'local'
$env:HOST = '127.0.0.1'
$env:PORT = '8000'
$env:ALLOWED_ORIGINS = 'http://localhost:8000,http://127.0.0.1:8000'
Write-Host 'Open http://localhost:8000 and sign in using the account you just chose.' -ForegroundColor Green
try {
    python backend/server.py
} finally {
    Remove-Item Env:USERS_JSON -ErrorAction SilentlyContinue
    Remove-Item Env:SESSION_SECRET -ErrorAction SilentlyContinue
    $operatorPassword = $null
    $operatorAccounts = $null
}
