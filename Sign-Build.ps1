<#
.SYNOPSIS
    Code-sign Claude-Migrate.exe with a self-signed "hemantrulz" certificate.

.DESCRIPTION
    Creates (or reuses) a self-signed code-signing certificate with subject CN=hemantrulz in
    the current user's certificate store, signs the exe with SHA-256 + a trusted timestamp,
    and exports the public cert (.cer) and a password-protected backup (.pfx) to .\signing.

    NOTE: a self-signed certificate is trusted only on machines where hemantrulz.cer has been
    imported into Trusted Root + Trusted Publishers. Other machines will still show
    "unknown publisher" and SmartScreen may still warn. For trust everywhere with no per-machine
    setup, buy a certificate from a public CA (the publisher name would be your validated identity).

.PARAMETER Exe         Path to the exe to sign (default: dist\Claude-Migrate.exe)
.PARAMETER Publisher   Publisher / signer name (default: hemantrulz)
.PARAMETER PfxPassword Password for the exported .pfx backup
#>
param(
    [string] $Exe = (Join-Path $PSScriptRoot 'dist\Claude-Migrate.exe'),
    [string] $Publisher = 'hemantrulz',
    [string] $PfxPassword,
    [string] $TimestampServer = 'http://timestamp.digicert.com'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Exe)) { Write-Host "Exe not found: $Exe" -ForegroundColor Red; exit 1 }
$subject = "CN=$Publisher"

# find or create the self-signed code-signing cert
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -eq $subject } | Select-Object -First 1
if (-not $cert) {
    Write-Host "Creating self-signed code-signing certificate '$subject' ..." -ForegroundColor Cyan
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject `
        -FriendlyName "$Publisher code signing" -CertStoreLocation Cert:\CurrentUser\My `
        -KeyExportPolicy Exportable -KeyAlgorithm RSA -KeyLength 2048 `
        -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5)
    Write-Host "  created: thumbprint $($cert.Thumbprint)" -ForegroundColor Green
} else {
    Write-Host "Reusing existing certificate: thumbprint $($cert.Thumbprint)" -ForegroundColor Green
}

# sign (with timestamp; fall back to no-timestamp if the server is unreachable)
Write-Host "Signing $Exe ..." -ForegroundColor Cyan
$sig = Set-AuthenticodeSignature -FilePath $Exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampServer
if (-not $sig.TimeStamperCertificate) {
    Write-Host "  (no timestamp applied -- server unreachable; signature valid only while cert is valid)" -ForegroundColor Yellow
} else {
    Write-Host "  timestamped OK" -ForegroundColor Green
}

# report
$v = Get-AuthenticodeSignature -FilePath $Exe
Write-Host ""
Write-Host "Signer  : $($v.SignerCertificate.Subject)" -ForegroundColor White
Write-Host "Status  : $($v.Status)  ($($v.StatusMessage))" -ForegroundColor White
Write-Host "(Status 'UnknownError/NotTrusted' is normal for self-signed until the cert is trusted on the machine.)" -ForegroundColor DarkGray

# export public cert + pfx backup
$dir = Join-Path $PSScriptRoot 'signing'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Export-Certificate -Cert $cert -FilePath (Join-Path $dir "$Publisher.cer") | Out-Null
if ($PfxPassword) { $pfxSec = ConvertTo-SecureString $PfxPassword -AsPlainText -Force }
else { $pfxSec = Read-Host "Enter a password to protect the .pfx private-key backup" -AsSecureString }
Export-PfxCertificate -Cert $cert -FilePath (Join-Path $dir "$Publisher.pfx") -Password $pfxSec | Out-Null
Write-Host ""
Write-Host "Exported:" -ForegroundColor Cyan
Write-Host "  $dir\$Publisher.cer   (public cert -- import on target machines to trust)"
Write-Host "  $dir\$Publisher.pfx   (private key backup -- keep it and its password safe; never commit)"
Write-Host ""
Write-Host "To trust on a target machine (run as admin):" -ForegroundColor Cyan
Write-Host "  Import-Certificate -FilePath $Publisher.cer -CertStoreLocation Cert:\LocalMachine\Root"
Write-Host "  Import-Certificate -FilePath $Publisher.cer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher"
