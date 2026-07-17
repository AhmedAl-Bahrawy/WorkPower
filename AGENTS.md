# AGENTS.md — Development Workflow

## Run Before Every Commit

```bash
& "C:\Users\Ahmed AL-Bahrawy\OneDrive\Documents\GitHub\FocusLock\.venv\Scripts\python.exe" -m pytest tests/ -v --tb=short
```

> **Note:** Windows PowerShell does not activate venv persistently. Use the full path with `&`.

## Test-After-Feature Rule

**Every new feature, service extraction, or bug fix MUST include tests before merging.** Specifically:

1. **New service/class/function** — create a corresponding `tests/test_<module>.py` with unit tests covering:
   - Happy path (basic CRUD, normal operation)
   - Edge cases (empty inputs, missing data, idempotent calls)
   - Error paths (invalid state, throttling, permission errors)
   - State transitions (start/stop, toggle, phase changes)

2. **Modified method** — add or update tests for the changed behavior. Verify existing tests still pass.

3. **Bug fix** — add a regression test that would have caught the bug.

4. **Run full suite** — `pytest tests/ -v` must show all green before any commit.

## Test File Structure

Follow the existing conventions in this repo:

- **Fixtures:** Use `tmp_path` + `monkeypatch` for isolated Storage instances. Use stubs/fakes for OS-level blockers (AppBlocker, WebsiteBlocker).
- **Class grouping:** Group tests by feature area in classes (`TestCRUD`, `TestLifecycle`, `TestThrottling`, etc.).
- **Parametrize** where multiple inputs share the same assertion logic.
- **No UI tests** unless `pytest-qt` is installed. Use service-layer unit tests instead.

## Current Test Inventory

| File | Module | Tests |
|------|--------|-------|
| `test_config.py` | `focuslock.config` (Storage) | 50 |
| `test_security.py` | `focuslock.core.security` | 27 |
| `test_timer.py` | `focuslock.core.timer` | 46 |
| `test_app_blocker.py` | `focuslock.blocking.app_blocker` | 21 |
| `test_website_blocker.py` | `focuslock.blocking.website_blocker` | 35 |
| `test_auth_service.py` | `focuslock.services.auth_service` | 29 |
| `test_blocklist_service.py` | `focuslock.services.blocklist_service` | 22 |
| `test_session_service.py` | `focuslock.services.session_service` | 14 |
| **Total** | | **244** |

> Count after Milestone 4 (services extraction): 244 + 120 existing = 364 tests.

## Architecture

```
src/focuslock/
├── config.py              # Storage (SQLAlchemy + SQLite)
├── constants.py           # PRESETS, THEMES, defaults
├── core/
│   ├── timer.py           # PomodoroTimer (threaded, monotonic)
│   └── security.py        # hash_password, verify_password
├── blocking/
│   ├── app_blocker.py     # AppBlocker (process kill loop)
│   └── website_blocker.py # hosts-file block/unblock
├── platform/
│   ├── startup.py         # Windows registry auto-start
│   ├── notifications.py   # Toast notifications
│   ├── elevate.py         # UAC elevation
│   └── subprocess_patch.py # Creationflags for Nuitka
├── services/              # Business logic layer
│   ├── auth_service.py    # Password CRUD, throttling, verification
│   ├── blocklist_service.py # App/site CRUD + blocker sync
│   └── session_service.py # Timer lifecycle, work-time tracking
├── ui/
│   ├── widgets.py         # Theme, ToggleButton, CircularTimer, etc.
│   └── dialogs.py         # AppPickerDialog, SitePickerDialog
└── focuslock_app.py       # QMainWindow (God Object, ~1570 lines)
```

## Key Conventions

- **Python 3.12**, PySide6, SQLAlchemy 2.x, pytest
- **DB:** `%APPDATA%\FocusLock\focuslock.db` (real), `tmp_path/test.db` (tests)
- **No comments** in source code unless explicitly requested
- **Password hashing:** SHA-256 with salt (`hash_password`/`verify_password`)
- **Throttling:** Exponential backoff, max 30s, shared counter for session + parent passwords
- **Strict mode:** Blocks quit/skip when `strict_mode` setting + password set + timer running
