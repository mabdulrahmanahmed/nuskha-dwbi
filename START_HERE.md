# Start here (local terminal)

Claude Code builds the whole project on your own computer, from a terminal: 5 phases, 49 work units, about 10.5 hours of processing. You are needed only for a setup at the start and a checklist at the end.

Progress is saved after every unit (`progress/PROGRESS.md` plus a git commit), so if your laptop switches off, nothing finished is lost: switch it back on and run one command to resume.

## The risk you are accepting

To run without stopping for approvals, the runner starts Claude Code with permission prompts turned off. Claude Code can then run any command your user account can. Contain it:

- **Windows:** run everything inside WSL (Ubuntu), with the project in your WSL home folder (`~/nuskha-dwbi`), not under `/mnt/c`. Keep nothing personal in that Ubuntu installation.
- **macOS:** create a separate macOS user account for the build, or accept that it runs with your normal account's access.

## 1. Setup (about 30 minutes, once)

### Windows (recommended path: WSL)

1. Open PowerShell **as Administrator** and run `wsl --install -d Ubuntu`. Restart when asked, open "Ubuntu" from the Start menu, and create a Linux username and password.
2. In the Ubuntu terminal, allow the build to install and start databases without asking for your password (replace nothing; `$USER` fills itself in):

```bash
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/nuskha-build
sudo apt-get update -qq && sudo apt-get install -y -qq git unzip tmux python3-pip python3-venv curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y -qq nodejs
```

3. Copy `nuskha-dwbi-kit.zip` into Ubuntu. In File Explorer open `\\wsl$\Ubuntu\home\<your-linux-username>\` and paste the zip there. Then in the Ubuntu terminal:

```bash
cd ~ && unzip -q nuskha-dwbi-kit.zip && cd nuskha-dwbi
git init -q && git add -A && git commit -q -m "Project kit"
```

4. Install Claude Code and sign in:

```bash
sudo npm install -g @anthropic-ai/claude-code
claude          # sign in once, then type /exit
```

### macOS

1. Install Homebrew (https://brew.sh) if you don't have it, then: `brew install git tmux python node`.
2. Unzip `nuskha-dwbi-kit.zip` into your home folder, then:

```bash
cd ~/nuskha-dwbi && git init -q && git add -A && git commit -q -m "Project kit"
npm install -g @anthropic-ai/claude-code
claude          # sign in once, then type /exit
```

### Both: optional backup to GitHub

Create an empty private repository `nuskha-dwbi` on GitHub, then run the two commands GitHub shows under "push an existing repository". From then on, every finished unit is also pushed there, so `progress/PROGRESS.md` can be read from your phone.

### Both: keep the laptop awake

- **Windows:** Settings → System → Power → Screen and sleep → "When plugged in, put my device to sleep after" → Never. Keep the charger in.
- **macOS:** System Settings → Battery/Energy → prevent automatic sleeping when the display is off, or run the build with `caffeinate -i bash scripts/resume.sh` instead of the command below.

## 2. Start the build

From the project folder (`~/nuskha-dwbi`):

```bash
bash scripts/resume.sh
```

When you see `[Phase 1] starting unit 1.01`, you can leave. Keep the terminal window open; minimise it rather than closing it. After each unit it prints:

`[Phase 2] 2.04 done in 13 min · 4/9 units · ~58 min of processing left in this phase`

The time is Claude Code's processing time, rescaled by how fast the finished units went. A unit that fails three times is marked BLOCKED, the units that need it are SKIPPED, and the run carries on; you deal with them at the end. If your Claude plan's usage limit is reached, the run waits 30 minutes and retries by itself.

## 3. If the laptop switched off, slept or the terminal closed

Open the terminal (Ubuntu on Windows), then:

```bash
cd ~/nuskha-dwbi && bash scripts/resume.sh
```

Finished units are skipped. A unit that was cut off mid-way is picked up and completed, and the databases are restarted (and rebuilt from the seed if needed) before it continues. To see where things stand without resuming: open `progress/PROGRESS.md`, or run `python3 scripts/progress.py summary`.

## 4. End-of-run checklist (about 30–60 minutes)

Do these after the run prints "Automated build finished", in this order.

1. **Blocked units, if any.** Read the summary and `docs/BLOCKERS.md`. Each entry says exactly what a person must do. Do it, mark the entry resolved, then run `python3 scripts/progress.py retry && bash scripts/resume.sh` (only the unfinished units run).
2. **Google Colab (about 10 min).** The brief requires extraction through Colab. Upload `pipeline.ipynb` to Colab, keep `MODE = "FULL_REBUILD"` in the first cell, run Runtime → Run all, then File → Download → .ipynb. Save it in the project as `evidence/colab_run.ipynb`.
3. **Power BI (about 10 min; about 45 with the fallback).** On Windows with Power BI Desktop: open `powerbi/nuskha.pbip` (in File Explorer under `\\wsl$\Ubuntu\home\<you>\nuskha-dwbi\powerbi\`), set the `DataFolder` parameter to the full path of the `powerbi\data` folder, click Refresh, check the three totals against `powerbi/reconciliation.csv`, save as `powerbi/nuskha.pbix`, and export File → Export → PDF to `powerbi/nuskha.pdf`. If the project will not open, build it from `powerbi/BUILD_GUIDE.md`.
4. **Finish:** in the terminal, from the project folder, run `bash scripts/finalize.sh`. It checks the Colab run, adds the Power BI pages to the report, rebuilds the report and reruns the final audit, with no input.
5. **People only:** fill in the contribution statement in `report/report.docx` truthfully; each member reads their guide in `docs/viva/` and runs their part of `docs/demo.md` once; check your course's policy on AI-assisted work before submitting.
