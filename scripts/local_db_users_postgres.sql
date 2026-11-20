-- One-time local setup (run by a person as the PostgreSQL superuser 'postgres'). Creates the
-- project role and the Purchasing source and warehouse databases. Matches config/.env.example.
-- Windows: "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f scripts\local_db_users_postgres.sql
CREATE ROLE nuskha LOGIN CREATEDB PASSWORD 'nuskha';
CREATE DATABASE purchasing_db OWNER nuskha;
CREATE DATABASE nuskha_dw OWNER nuskha;
