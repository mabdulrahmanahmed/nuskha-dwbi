-- One-time local setup (run by a person as the MySQL root user). Creates the project user
-- and the two Sales/Finance databases. Matches config/.env.example (user nuskha, password nuskha).
-- Windows: "C:\Program Files\MySQL\MySQL Server 9.3\bin\mysql.exe" -u root -p < scripts\local_db_users_mysql.sql
CREATE USER IF NOT EXISTS 'nuskha'@'localhost' IDENTIFIED BY 'nuskha';
CREATE DATABASE IF NOT EXISTS sales_db CHARACTER SET utf8mb4;
CREATE DATABASE IF NOT EXISTS finance_db CHARACTER SET utf8mb4;
GRANT ALL PRIVILEGES ON sales_db.* TO 'nuskha'@'localhost';
GRANT ALL PRIVILEGES ON finance_db.* TO 'nuskha'@'localhost';
FLUSH PRIVILEGES;
