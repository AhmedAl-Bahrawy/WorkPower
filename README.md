<div align="center">

# FocusLock

### Stop procrastinating. Start studying.

A Windows desktop app that blocks distracting apps and websites during Pomodoro focus sessions.

[![Stars](https://img.shields.io/github/stars/zadwen/FocusLock?style=flat-square&color=8b5cf6)](https://github.com/zadwen/FocusLock/stargazers)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-0078d4?style=flat-square&logo=windows)](https://github.com/zadwen/FocusLock/releases)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-43e97b?style=flat-square)](LICENSE)

</div>

---

## Features

| | |
|---|---|
| Pomodoro Timer | Circular countdown with work/break/long-break phases, 5 presets + custom durations |
| Cycle Counter | Tracks "Pomodoro N of M" with configurable cycles before long break |
| App Blocker | Force-kills distracting apps every 2 seconds during work phases |
| Website Blocker | Blocks sites via hosts file modification (requires admin) |
| Custom Durations | Set work/break/long-break/cycles via spinboxes on the session page |
| Sound Alerts | Beep on phase change (toggle in Settings) |
| Skip Button | Jump to the next phase without waiting |
| Password Lock | Session password prevents pausing/stopping |
| Parent Password | Second password that overrides session lock |
| Auto-Start | Toggle whether phases auto-continue or pause between them |
| Start with Windows | Registry startup entry |
| System Tray | Minimizes to tray instead of closing |
| Session Stats | Total sessions, focus time, streak, 7-day chart |
| Dark / Light Theme | Toggle instantly without restarting |

---

## Download

Grab `FocusLock.exe` from the [Releases](https://github.com/zadwen/FocusLock/releases) page and run it. No Python needed.

> Right-click > Run as Administrator if you want the website blocker to work.

---

## Run from source

```bash
git clone https://github.com/zadwen/FocusLock.git
cd FocusLock
pip install -r requirements.txt
python ./src/focuslock_app.py
```

Requires Python 3.10+ on Windows.

---

## Build a .exe

```bash
pip install nuitka ordered-set zstandard
python scripts/build.py --release
python scripts/release.py --zip
```

Output goes to `dist/FocusLock-3.0.0/`. See [docs/BUILD.md](docs/BUILD.md) for full build details.

---

## Default Blocklist

```
steam.exe            steamwebhelper.exe
discord.exe          EpicGamesLauncher.exe
Battle.net.exe       LeagueClient.exe
TwitchUI.exe         Spotify.exe
```

Fully editable from the UI.

---

## Project Layout

```
FocusLock/
├── src/
│   ├── focuslock_app.py              # Main entry point
│   └── focuslock/                    # Core package
│       ├── constants.py              # Name, version, themes, presets
│       ├── config.py                 # SQLAlchemy ORM (SQLite)
│       ├── core/
│       │   ├── timer.py              # Thread-safe PomodoroTimer
│       │   └── security.py           # Password hashing
│       ├── blocking/
│       │   ├── app_blocker.py        # Process blocking
│       │   └── website_blocker.py    # Hosts file blocking
│       ├── platform/
│       │   ├── startup.py            # Windows registry
│       │   ├── notifications.py      # Toast notifications
│       │   └── subprocess_patch.py   # Hidden console windows
│       └── ui/
│           ├── widgets.py            # Theme, CircularTimer, charts
│           └── dialogs.py            # App/site picker dialogs
├── scripts/
│   ├── version.py                    # Single source of truth for version
│   ├── build.py                      # Nuitka build orchestrator
│   ├── clean.py                      # Build artifact cleanup
│   └── release.py                    # Release packaging
├── installer/
│   └── focuslock.iss                 # Inno Setup installer script
├── workflows/build.yml               # GitHub Actions CI/CD
├── requirements.txt                  # Python dependencies
├── docs/
│   ├── BUILD.md                      # Technical build docs
│   ├── REFERENCE.md                  # Technical reference
│   └── CHANGELOG.md                  # Version history
└── LICENSE                           # MIT
```

---

## License

MIT

---

<div align="center">
Made by <a href="https://github.com/zadwen">zadwen</a>
</div>
