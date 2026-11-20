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
