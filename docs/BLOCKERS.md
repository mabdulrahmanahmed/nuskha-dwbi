# Blockers

Units marked BLOCKED, with what was tried and what a person would need to do.

| Unit | Problem | Tried | Needs |
| --- | --- | --- | --- |
| 1.01 | The MySQL 9.3 and PostgreSQL 18 services are running (ports 3306 and 5432 open), but the project user `nuskha` does not exist on either server: MySQL "Access denied for user 'nuskha'@'localhost'", PostgreSQL "password authentication failed for user nuskha". `config/.env` is also missing. Creating users needs the root/postgres admin passwords, which only the person has. | `scripts/setup_env.sh` (local and colab modes) and `scripts/check_env.py` are written and tested up to the connection step. The `.env.example` credentials were tried against both servers and failed as above. | 1) Copy the env file: `cp config/.env.example config/.env`. 2) MySQL as root: `"C:\Program Files\MySQL\MySQL Server 9.3\bin\mysql.exe" -u root -p < scripts\local_db_users_mysql.sql`. 3) PostgreSQL as postgres: `"C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f scripts\local_db_users_postgres.sql`. 4) Check: `bash scripts/setup_env.sh` must print OK five times. 5) Mark this row resolved and run `.venv/Scripts/python scripts/progress.py retry`; then units 1.01, 1.08 and Phases 2–5 can run. If you prefer other passwords, put them in `config/.env` instead. |

**Update 2026-11-22 (1.01):** `config/.env` now exists. The person does not know the MySQL root or PostgreSQL postgres passwords, so `scripts/reset_db_access.ps1` was added. Run it once in PowerShell opened as Administrator: `powershell -ExecutionPolicy Bypass -File scripts\reset_db_access.ps1`. It creates nuskha/nuskha on both servers plus the four databases, and sets the admin logins to root/root and postgres/postgres (local only).
