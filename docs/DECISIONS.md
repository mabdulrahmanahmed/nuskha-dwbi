# Decisions and deviations from the blueprint

| Unit | Decision | Reason |
| --- | --- | --- |
| plan | The warehouse PostgreSQL runs in the build environment (and in Colab), not on a hosted service. | A hosted service needs a person to create an account and share credentials; the plan must run without human input. |
| plan | Power BI reads CSV exports of the saved views (`powerbi/data/`) instead of a live database connection. | Power BI Desktop cannot reach a database inside a container; the three reconciled totals are checked against SQL totals from the same batch. |
| plan | Evidence is committed to the git repo after every unit instead of a Google Drive folder. | Removes the Drive mount, which needs a person to sign in. |
| plan | The notebook is executed headlessly on Ubuntu first; the Google Colab run is the last human step. | Colab cannot be driven without a person; Ubuntu matches Colab's environment. |
| plan | All human steps are moved after the automated build, except the setup that starts it; a closing automated step runs after them. | Requested by the user: no human input during the run. |
| plan | A unit that fails 3 times is BLOCKED and its dependents SKIPPED instead of stopping the run. | The run never waits for a person; blocked units are fixed at the end. |
| plan | The build runs locally in a terminal (Ubuntu on WSL, or macOS) instead of a Codespace. | Requested by the user. Progress is committed after every unit so a laptop shutdown loses nothing; `scripts/resume.sh` continues. |
| plan | Evidence is committed to the local git repository after every unit; pushing to GitHub is optional backup. | No account is needed for the run itself. |
| setup | `scripts/run_all.sh`, `run_phase.sh` and `finalize.sh` pick the interpreter as `.venv/Scripts/python`, then `.venv/bin/python`, then `python3`/`python`, instead of a hard-coded `python3`. | The build machine is native Windows (Git Bash), where `python3` does not exist; the same scripts still work on WSL, macOS and Colab. |
| setup | The git repository was initialised in the project folder with a "Project kit" commit before unit 1.02. | CLAUDE.md requires a commit after every unit; the kit had no repository yet. |
| setup | The venv is created with `--system-site-packages` and reuses the machine's global numpy, pandas, matplotlib, scikit-learn and psycopg2-binary; only the missing small packages are pip-installed into it. | The network on the build machine downloads at about 10 KB/s, so a full `pip install -r requirements.txt` would take hours. `requirements.txt` is unchanged, and Colab installs it normally. |
| 1.04 | Generator randomness uses `numpy.random.default_rng([472, part])`, with one part number per generator part (1 reference, 2 transactions, 3 defects, 4 stage-2 changes). | Still seed 472, but changing a later part never shifts the random numbers of an earlier part, so earlier evidence stays valid. |
| 1.04 | Prices and costs rise 8% every 1 July (2024, 2025, 2026). Diabetes Care cost rises a further 12% on 1 Mar 2026, and its shelf price is frozen (no July 2026 rise). | Implements the blueprint's "price inflation" and the Diabetes Care margin story; ASP stays flat while cost rises. |
| 1.04 | Ramadan dates (approximate, synthetic) are 2024-03-12..04-10, 2025-03-02..03-30 and 2026-02-19..03-20 (`data/generated/reference/ramadan.csv`, also in `src/gen/catalogue.py`). | Needed for the Vitamins season and for `dim_date.is_ramadan` (unit 3.02). |
