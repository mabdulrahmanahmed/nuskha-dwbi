# One-time local setup for people who do not know the MySQL root / PostgreSQL postgres passwords.
# Run in PowerShell opened "As Administrator":
#   powershell -ExecutionPolicy Bypass -File scripts\reset_db_access.ps1
#
# What it does (official recovery methods, local machine only):
#   MySQL      : stops the MySQL93 service, starts mysqld once with --init-file that sets
#                root password = root and creates user nuskha/nuskha + sales_db, finance_db,
#                shuts it down, starts the service again.
#   PostgreSQL : backs up pg_hba.conf, switches local logins to "trust", restarts, sets
#                postgres password = postgres, creates role nuskha/nuskha + purchasing_db,
#                nuskha_dw, then restores the original pg_hba.conf and restarts.
# Safe to run twice.

#Requires -RunAsAdministrator
$ErrorActionPreference = 'Continue'

$mysqlBin = 'C:\Program Files\MySQL\MySQL Server 9.3\bin'
$myIni    = 'C:\ProgramData\MySQL\MySQL Server 9.3\my.ini'
$mysqlSvc = 'MySQL93'
$pgBin    = 'C:\Program Files\PostgreSQL\18\bin'
$pgData   = 'C:\Program Files\PostgreSQL\18\data'
$pgSvc    = 'postgresql-x64-18'
$results  = @()

# ---------------------------------------------------------------- MySQL
Write-Host "`n=== MySQL ===" -ForegroundColor Cyan
$init = Join-Path $env:TEMP 'nuskha_mysql_init.sql'
@'
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
CREATE USER IF NOT EXISTS 'nuskha'@'localhost' IDENTIFIED BY 'nuskha';
ALTER USER 'nuskha'@'localhost' IDENTIFIED BY 'nuskha';
CREATE DATABASE IF NOT EXISTS sales_db CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS finance_db CHARACTER SET utf8mb4;
GRANT ALL PRIVILEGES ON sales_db.* TO 'nuskha'@'localhost';
GRANT ALL PRIVILEGES ON finance_db.* TO 'nuskha'@'localhost';
FLUSH PRIVILEGES;
'@ | Set-Content -Encoding ascii $init
$initArg = $init -replace '\\', '/'

$proc = $null
try {
    Write-Host "Stopping service $mysqlSvc ..."
    Stop-Service $mysqlSvc -Force
    Write-Host "Starting MySQL once with the setup file ..."
    $proc = Start-Process -FilePath "$mysqlBin\mysqld.exe" `
        -ArgumentList "--defaults-file=`"$myIni`"", "--init-file=`"$initArg`"" `
        -PassThru -WindowStyle Hidden
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 2
        & "$mysqlBin\mysql.exe" -u nuskha --password=nuskha -h 127.0.0.1 -e "SELECT 1" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        if ($proc.HasExited) { break }
    }
    if ($ok) { Write-Host "MySQL user nuskha works." -ForegroundColor Green; $results += 'MySQL: OK' }
    else     { Write-Host "MySQL setup did not succeed (see the MySQL error log in C:\ProgramData\MySQL\MySQL Server 9.3\Data\*.err)." -ForegroundColor Red; $results += 'MySQL: FAILED' }
    Write-Host "Shutting the temporary MySQL down ..."
    & "$mysqlBin\mysqladmin.exe" -u root --password=root -h 127.0.0.1 shutdown 2>$null
    if (-not $proc.HasExited) { $proc.WaitForExit(60000) | Out-Null }
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
finally {
    Remove-Item $init -ErrorAction SilentlyContinue
    Write-Host "Starting service $mysqlSvc again ..."
    Start-Service $mysqlSvc
}

# ---------------------------------------------------------------- PostgreSQL
Write-Host "`n=== PostgreSQL ===" -ForegroundColor Cyan
$hba = Join-Path $pgData 'pg_hba.conf'
$bak = "$hba.nuskha-backup"
$sql = Join-Path $env:TEMP 'nuskha_pg_setup.sql'
@'
DO $$BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nuskha') THEN
    CREATE ROLE nuskha LOGIN CREATEDB PASSWORD 'nuskha';
  ELSE
    ALTER ROLE nuskha LOGIN CREATEDB PASSWORD 'nuskha';
  END IF;
END$$;
ALTER ROLE postgres PASSWORD 'postgres';
SELECT 'CREATE DATABASE purchasing_db OWNER nuskha' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'purchasing_db')\gexec
SELECT 'CREATE DATABASE nuskha_dw OWNER nuskha' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nuskha_dw')\gexec
'@ | Set-Content -Encoding ascii $sql

try {
    Write-Host "Backing up pg_hba.conf to $bak"
    Copy-Item $hba $bak -Force
    (Get-Content $hba) | ForEach-Object {
        if ($_ -match '^\s*#') { $_ } else { $_ -replace '(scram-sha-256|md5|password)\s*$', 'trust' }
    } | Set-Content -Encoding ascii $hba
    Write-Host "Restarting $pgSvc with temporary local trust ..."
    Restart-Service $pgSvc -Force
    Start-Sleep -Seconds 3
    & "$pgBin\psql.exe" -U postgres -h localhost -w -v ON_ERROR_STOP=1 -f $sql
    if ($LASTEXITCODE -ne 0) { Write-Host "PostgreSQL setup SQL failed." -ForegroundColor Red }
}
finally {
    Write-Host "Restoring the original pg_hba.conf ..."
    if (Test-Path $bak) { Copy-Item $bak $hba -Force }
    Remove-Item $sql -ErrorAction SilentlyContinue
    Restart-Service $pgSvc -Force
    Start-Sleep -Seconds 3
}
$env:PGPASSWORD = 'nuskha'
& "$pgBin\psql.exe" -U nuskha -h localhost -w -d nuskha_dw -c "SELECT 1" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Write-Host "PostgreSQL user nuskha works." -ForegroundColor Green; $results += 'PostgreSQL: OK' }
else { Write-Host "PostgreSQL user nuskha does NOT work yet." -ForegroundColor Red; $results += 'PostgreSQL: FAILED' }
Remove-Item Env:PGPASSWORD

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$results | ForEach-Object { Write-Host $_ }
Write-Host "Admin logins are now: MySQL root/root, PostgreSQL postgres/postgres (local only)."
Write-Host "Project login (config/.env): nuskha/nuskha on both."
