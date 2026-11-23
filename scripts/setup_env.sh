#!/usr/bin/env bash
# Prepare the environment for the Nuskha DWBI pipeline. Safe to run any number of times.
#
#   bash scripts/setup_env.sh          # auto: colab inside Google Colab, otherwise local
#   bash scripts/setup_env.sh local    # engines already installed by the person; config/.env present
#   bash scripts/setup_env.sh colab    # Google Colab (Ubuntu): apt-install MySQL + PostgreSQL, users, .env
#
# local: no sudo, no installs of database engines. Python packages that are missing are
#        pip-installed into .venv; then the four server databases are created if missing,
#        using the users in config/.env, and every connection is checked.
# colab: installs and starts MySQL and PostgreSQL, creates the 'nuskha' users and databases,
#        writes config/.env, pip-installs requirements.txt. (Tested only in Colab; see DECISIONS.md.)
set -uo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-auto}"
if [ "$MODE" = "auto" ]; then
  if [ -d /content ] && [ -n "${COLAB_RELEASE_TAG:-}${COLAB_GPU:-}" ]; then MODE=colab; else MODE=local; fi
fi
echo "setup_env: mode $MODE"

if [ "$MODE" = "colab" ]; then
  # ---- Google Colab only: install, start and configure both engines -------------------
  export DEBIAN_FRONTEND=noninteractive
  apt-get -qq update >/dev/null
  apt-get -qq install -y mysql-server postgresql >/dev/null || apt-get -qq install -y mariadb-server postgresql >/dev/null
  service mysql start >/dev/null 2>&1 || service mariadb start >/dev/null 2>&1
  service postgresql start >/dev/null
  mysql -uroot -e "CREATE USER IF NOT EXISTS 'nuskha'@'localhost' IDENTIFIED BY 'nuskha';
    GRANT ALL PRIVILEGES ON *.* TO 'nuskha'@'localhost'; FLUSH PRIVILEGES;"
  su postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='nuskha'\" | grep -q 1 || psql -c \"CREATE ROLE nuskha LOGIN CREATEDB PASSWORD 'nuskha'\"" >/dev/null
  [ -f config/.env ] || cp config/.env.example config/.env
  pip install -q -r requirements.txt
  PY=python
else
  # ---- Local (Windows Git Bash, WSL, macOS): engines are the person's Windows/OS services ---
  if [ ! -d .venv ]; then
    # --system-site-packages reuses packages already installed on the machine (slow networks).
    python -m venv --system-site-packages .venv 2>/dev/null || python3 -m venv --system-site-packages .venv
  fi
  PY=.venv/Scripts/python; [ -x "$PY" ] || PY=.venv/bin/python
  # Install only the requirements that are not importable yet (fast when nothing is missing).
  MISSING=$("$PY" - <<'EOF'
import importlib.util
names = {"pandas": "pandas", "numpy": "numpy", "SQLAlchemy": "sqlalchemy", "PyMySQL": "pymysql",
         "psycopg2-binary": "psycopg2", "scikit-learn": "sklearn", "matplotlib": "matplotlib",
         "graphviz": "graphviz", "jupyter": "jupyter_core", "nbconvert": "nbconvert", "python-docx": "docx"}
print(" ".join(p for p, m in names.items() if importlib.util.find_spec(m) is None))
EOF
)
  if [ -n "$MISSING" ]; then
    echo "setup_env: installing missing packages: $MISSING"
    "$PY" -m pip install -q --default-timeout=120 $MISSING || echo "setup_env: WARNING pip install failed; continuing"
  fi
  if [ ! -f config/.env ]; then
    echo "setup_env: config/.env is missing. Copy config/.env.example to config/.env (see docs/BLOCKERS.md)."
    exit 1
  fi
fi

# ---- Both modes: create missing databases with the .env users, then check every connection --
"$PY" scripts/check_env.py --create
