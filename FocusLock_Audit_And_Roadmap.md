# FocusLock — Master Project Audit & Evolution Plan (v3.0.0 → v4.0)

> Audit performed directly against `github.com/AhmedAl-Bahrawy/WorkPower` (product name in-repo: **FocusLock**, v3.0.0). This document reflects the actual codebase, not a generic template — see the Correction Notice below.

---

## 0. Correction Notice (read first)

The audit brief assumes this is an early-stage, half-finished project needing an achievements system, session segmentation, day/week/month grouping, and a rename to "WorkPower." After inspecting the real repository, several of those assumptions don't hold:

- The product already has a name, brand, and README-documented identity: **FocusLock** — "Stop procrastinating. Start studying." It is not unnamed, and a rename is a strategic decision, not a fix.
- There is **no** partial "achievements" or "session segmentation" system anywhere in the code. These aren't half-built — they don't exist. They are correctly scoped in this document as **new features**, not completions.
- "Session naming" **is** already implemented (a single free-text field, cached in memory, persisted to SQLite) — it's simple but not broken. What's missing is *multiple named sessions* / history, which is a feature gap, not a bug.
- Day/week/month grouping partially exists: `get_daily_stats()` already buckets by day. Week/month rollups are the actual gap.
- The timer engine is already thread-safe (uses `threading.Lock` around all shared state) and already has long-break/cycle logic — it is not the fragile "impossible to corrupt" hazard implied by the brief, though it does have real correctness bugs detailed below (drift, a clamp bug, and a re-entrancy edge case).
- The CHANGELOG shows this project already went through one hardening pass (v3.0.0) that fixed several of the exact bug classes the brief asks about (timer drift on first tick, preset-switch cycle resets, `total_for_phase` ignoring long breaks). The team clearly already does its own bug-hunting; this audit tries not to re-litigate fixed issues and instead find what's left.

The rest of this document is written against the real code at `src/focuslock_app.py`, `src/focuslock/core/timer.py`, `src/focuslock/config.py`, `src/focuslock/blocking/*`, `src/focuslock/platform/*`, and `src/focuslock/ui/*`.

---

## 1. Executive Summary

FocusLock is a Windows-only PySide6 desktop app that enforces Pomodoro-style focus sessions by force-killing distracting processes and blocking sites via the hosts file. It's a single-developer, single-window, single-user local app with SQLite persistence via SQLAlchemy. Architecturally it's in decent shape for its size — genuine separation into `core/`, `blocking/`, `platform/`, `ui/`, `config.py` — but the **main window class (`FocusLockApp`) is a 1,300-line God Object** that owns UI construction, business logic, timer orchestration, and password policy all in one file. That's the single highest-leverage structural problem.

The timer engine is thread-safe but **uses `time.sleep(1)` in a loop as its clock**, which means every tick has scheduler jitter, and a long enough sequence of ticks will drift from wall-clock time. It is not "impossible to corrupt" as things stand — there's one clamp bug that can silently truncate a running long break, and a background-thread race window in `start()`/`skip()`/`_recreate_timer()` under rapid input.

Security-sensitive surfaces (password hashing, hosts-file writes, process killing) are implemented reasonably (salted SHA-256, no plaintext storage) but have real gaps: no login-attempt throttling, hosts-file edits aren't atomic, and the app-blocker kill-loop has no allowlist protection against a user accidentally blocking something critical like their shell.

There is no test suite anywhere in the repository. That's the second highest-leverage gap — every refactor from here on is done blind.

The product itself is coherent and has a clear identity already. The biggest product opportunity isn't fixing brokenness — it's that stats/history are currently a single flat number per day with no session-level detail, no session naming *history*, and no achievements/motivation loop, which is exactly where the brief's instincts about "unfinished" features are correct, just misdiagnosed as bugs rather than as intentionally-scoped v4 features.

---

## 2. Current Project Health Assessment

| Area | Status | Notes |
|---|---|---|
| Architecture | 🟡 Fair | Real module boundaries exist, but `focuslock_app.py` (1,322 lines) violates them by owning everything |
| Timer engine | 🟡 Fair | Thread-safe, but sleep-based (drifts), one clamp bug, no persistence of running state across app restarts |
| Data layer | 🟢 Good | Clean SQLAlchemy models, sane migration path from legacy JSON, no obvious SQL injection surface (ORM everywhere) |
| Security | 🟡 Fair | Salted hashing is correct; no rate-limiting on password dialogs; hosts-file write isn't atomic; no admin-check before attempting website block |
| Testing | 🔴 Poor | Zero automated tests found in the repo |
| UX consistency | 🟢 Good | Theme system is centralized and consistent; spacing/typography are uniform across pages |
| Error handling | 🟡 Fair | Broad `except Exception: pass` in several places swallows real failures silently (hosts file writes, notifications, startup registry) |
| Accessibility | 🔴 Poor | No keyboard navigation for the timer controls beyond default Qt tab order; no screen-reader labels; color is the only phase-change signal besides text |
| Documentation | 🟢 Good | README, CHANGELOG, BUILD docs, REFERENCE doc all exist and are current |
| Product identity | 🟢 Good | Name, tagline, color palette, and positioning already defined and consistent |

---

## 3. Complete Bug Report

Severity scale: **Critical** (data loss / security / crash) · **High** (visible incorrect behavior) · **Medium** (edge case, workaround exists) · **Low** (cosmetic / polish).

### 3.1 Timer Engine

**BUG-01 — Sleep-based clock drifts from wall-clock time**
- Severity: High
- File: `core/timer.py`, `_loop()`
- Description: The countdown uses `time.sleep(1)` per tick and decrements an integer counter. `time.sleep` is not exact — OS scheduling, GC pauses, and thread contention (the app also runs an `AppBlocker` poll loop every 2s and a website-sync) all add latency that accumulates. Over a 90-minute Deep Work session this can drift by several seconds to low tens of seconds.
- Consequence: The recorded "actual work minutes" (`_track_work_time`, which uses `time.time()` deltas) and the timer's own `remaining` counter can silently disagree, and users doing long sessions get session-length inaccuracy.
- Fix: Anchor the loop to `time.monotonic()` at start, and on each tick compute `remaining = target_end - time.monotonic()` instead of decrementing a counter. This makes the timer self-correcting instead of cumulative-error-prone.
- Difficulty: Medium (isolated to `timer.py`, but must be tested carefully against pause/resume/skip).

**BUG-02 — `set_remaining()` clamps against the wrong duration during long breaks**
- Severity: Medium
- File: `core/timer.py`, lines 91–95
```python
def set_remaining(self, seconds):
    with self._lock:
        cap = self.work_sec if self._phase == "work" else self.break_sec
        self._rem = max(0, min(seconds, cap))
```
- Description: This clamps to `break_sec` even when the current phase is actually a **long break**. `_recreate_timer()` in `focuslock_app.py` calls this when the user changes durations mid-session. If a long break (e.g. 20 minutes) is running and the user tweaks the work-duration spinbox, `remaining` silently gets clamped down to the *short* break length (e.g. 5–10 minutes), cutting the long break short without warning.
- Consequence: Silent, incorrect truncation of a running long break.
- Fix: `set_remaining` needs to know whether the current break is a long break (it already has `cycles` and `cycles_per_set` available) and clamp against `long_break_sec` in that case — reuse the same logic already written correctly in `phase_total`.
- Difficulty: Low.

**BUG-03 — Race window between `skip()` and a concurrent `_recreate_timer()`**
- Severity: Medium
- File: `core/timer.py` + `focuslock_app.py::_recreate_timer`
- Description: `skip()` sets `_rem = 0` to force the background loop to exit and call `_switch()`. If the user simultaneously changes a spinbox (triggering `_recreate_timer`, which calls `self.timer.pause()` and constructs a **brand-new** `PomodoroTimer` object), the old loop's thread is still alive and holds a reference to the old timer object; it can call the old object's `on_phase` callback *after* the new timer has already been installed as `self.timer`. Because `on_phase` is a lambda bound to `self.timer_sig.tick.emit`, the UI could receive a phase-transition signal for a timer that's no longer active.
- Consequence: Rare, hard-to-reproduce UI desync — e.g. a stray "Phase complete" notification or sound firing right after a mid-session settings change.
- Fix: Give each `PomodoroTimer` instance a monotonically increasing generation id; have `FocusLockApp` ignore signals from any generation other than the current one, or have `_recreate_timer` join/cancel the old thread before starting the new one (requires adding a cancellation flag since threads are daemon but not currently interruptible).
- Difficulty: Medium.

**BUG-04 — `start()` has no reentrancy guard against double-invocation from rapid clicks**
- Severity: Low
- File: `core/timer.py`, lines 63–68
```python
def start(self):
    if self.is_running:
        return
    with self._lock:
        self._running = True
    threading.Thread(target=self._loop, daemon=True).start()
```
- Description: The `is_running` check and the `_running = True` write are not atomic as a pair (the check happens outside the lock that protects the write). Two near-simultaneous calls to `start()` (e.g. a double-click on "Start Session" before the button visually disables, or a signal misfire) can both pass the `if self.is_running` check before either sets `_running = True`, spawning two `_loop` threads.
- Consequence: Two competing decrement loops running against the same `_rem`, causing the timer to count down roughly twice as fast, and duplicate phase-switch callbacks.
- Fix: Move the check inside the lock:
```python
def start(self):
    with self._lock:
        if self._running:
            return
        self._running = True
    threading.Thread(target=self._loop, daemon=True).start()
```
- Difficulty: Trivial — this is a one-line, safe fix and should be in the very first patch.

**BUG-05 — No persistence of timer state across app close/reopen**
- Severity: Medium
- File: `focuslock_app.py`, `_quit()`
- Description: On quit, the timer is paused but its remaining time/phase/cycle count is never written to storage. Reopening the app always starts fresh at the configured preset's full duration, silently discarding an in-progress session.
- Consequence: Closing (not minimizing — actually quitting) the app mid-session loses progress with no warning.
- Fix: Persist `{remaining, phase, cycles, timestamp}` to the `settings` table on pause/quit; on next launch, if a saved state exists and its timestamp is recent (e.g. same day), offer to resume.
- Difficulty: Medium.

### 3.2 Data & Storage

**BUG-06 — `Storage.set()` is not thread-safe against concurrent writers**
- Severity: Medium
- File: `config.py`
- Description: `Storage` uses a single long-lived `Session` object (`self._session_factory`) shared across the whole app, accessed from the Qt main thread (UI callbacks) *and* implicitly reachable from background threads if any future code calls into it from `AppBlocker`/`PomodoroTimer` callbacks (they don't today, but nothing prevents it, and `on_tick`/`on_phase` already fire from a background thread before being marshaled to Qt signals). SQLAlchemy `Session` objects are explicitly documented as not thread-safe.
- Consequence: Currently likely safe in practice because DB writes only happen from Qt-thread-marshaled slots, but this is fragile-by-convention, not fragile-by-design — a future contributor calling `self.storage.set(...)` directly from inside a timer callback (a natural-looking thing to do) would introduce silent corruption.
- Fix: Either (a) enforce via a code comment + a thin assertion that `Storage` methods are only called from the main thread, or (b) switch to a scoped-session-per-call pattern (`sessionmaker` + `with Session(engine) as s:`) which is safe to call from any thread since SQLite is opened with `check_same_thread=False` already.
- Difficulty: Medium (b) / Low (a, but weaker guarantee).

**BUG-07 — `record_session()` always attributes work minutes to "today," even for late-night sessions**
- Severity: Low
- File: `config.py`, `record_session()`
- Description: Uses `date.today()` at the moment the session ends. A work session that starts at 11:50 PM and ends at 12:10 AM the next day is entirely attributed to the end date, not split, not attributed to when the focus actually happened.
- Consequence: Minor stats/streak inaccuracy for late-night users; could affect streak calculations near midnight.
- Fix: Low priority — document as known behavior, or optionally attribute to session *start* date instead if that's judged more intuitive.
- Difficulty: Low.

### 3.3 Blocking Subsystems

**BUG-08 — Hosts-file write is not atomic; a crash mid-write can corrupt the system hosts file**
- Severity: Critical
- File: `blocking/website_blocker.py`, `block_sites()` / `unblock_sites()`
```python
HOSTS.write_text(content + block, encoding="utf-8")
```
- Description: This does a direct, non-atomic overwrite of `C:\Windows\System32\drivers\etc\hosts`. If the process is killed (crash, forced shutdown, antivirus intervention, power loss) between opening the file for write and completing the write, the hosts file can be left truncated or empty — a real system-level side effect that has nothing to do with FocusLock's own data and affects the user's entire machine's DNS resolution.
- Consequence: Worst case, a partially-written hosts file breaks the user's internet name resolution system-wide until manually repaired.
- Fix: Write to a temp file in the same directory, then `os.replace()` (atomic rename on Windows for same-volume moves) onto the real hosts file. This is a standard atomic-write pattern.
- Difficulty: Low, and should be treated as the single highest-priority fix in this entire report given the blast radius.

**BUG-09 — No verification that the app is running elevated before attempting to write the hosts file**
- Severity: Medium
- File: `blocking/website_blocker.py`
- Description: `block_sites()` catches `PermissionError` and returns `False`, but nothing upstream in `focuslock_app.py` surfaces this failure to the user — `WebsiteBlocker.start()` calls `block_sites(self._active)` and ignores the return value entirely.
- Consequence: A non-admin user enables "Block Websites," believes it's active (toggle shows on, no error), and it silently does nothing.
- Fix: Check `ctypes.windll.shell32.IsUserAnAdmin()` at startup; if not elevated, either disable the website-blocking toggle with an explanatory tooltip, or surface a one-time dialog offering to relaunch elevated.
- Difficulty: Low–Medium.

**BUG-10 — `AppBlocker` has no protection against blocking critical system processes**
- Severity: High
- File: `blocking/app_blocker.py`
- Description: `_kill()` force-kills any process whose name matches an entry in the user-configured blocklist, with zero allowlist/denylist safety net. Because apps are added via free text or a "Browse .exe" file picker (`dialogs.py`), a user (or a mis-click, or a malicious import of a shared blocklist) could add something like `explorer.exe`, `dwm.exe`, or their IDE/terminal process, and the app will forcibly and repeatedly kill it every 2 seconds during focus sessions.
- Consequence: Potential for the user to lock themselves out of their own desktop shell, or repeatedly lose unsaved work in any accidentally-blocklisted application.
- Fix: Maintain a small hardcoded denylist of Windows-critical process names (`explorer.exe`, `dwm.exe`, `csrss.exe`, `winlogon.exe`, `svchost.exe`, etc.) that can never be added to the blocklist regardless of user input, enforced both in the "Add App" dialog and defensively again in `AppBlocker.set_enabled_apps()`.
- Difficulty: Low.

**BUG-11 — `AppPickerDialog` excludes `python.exe`/`pythonw.exe` from the running-apps list but not from manual "Browse .exe" add**
- Severity: Low
- File: `ui/dialogs.py`
- Description: The running-process picker filters out the app's own interpreter, but "Browse .exe" lets a user manually navigate to and add `python.exe` (or the packaged `focuslock.exe` itself) as a blocked target.
- Consequence: A user could self-block the app that is doing the blocking, if run from source; less relevant for the Nuitka-compiled distributable but still an inconsistency in the safety net.
- Fix: Apply the same exclusion list in the "Browse .exe" handler.
- Difficulty: Trivial.

### 3.4 Security

**BUG-12 — No throttling or lockout on password dialogs**
- Severity: Medium
- File: `focuslock_app.py`, `_require_password` / `_require_parent_password`
- Description: `PasswordDialog` can be resubmitted unlimited times with no delay, no attempt counter, no lockout. Given the hash is salted SHA-256 (fast by design, not a slow KDF), and the dialog is local (not networked), the realistic risk is limited to another local user on the machine guessing a short password — but the parent-password use case (parents restricting a child's ability to disable locks) is exactly the scenario where a determined child brute-forcing a 4-character minimum password locally is a real threat model.
- Consequence: A 4-character password (the enforced minimum, see BUG-13) is guessable in a short local brute-force loop if someone scripted it, though the UI itself requires manual entry so this is a soft risk today.
- Fix: Add an increasing delay after repeated failures (e.g. 1s, 2s, 5s...) and/or switch minimum password length up (see BUG-13). A full lockout isn't appropriate for a local single-user recovery-sensitive tool, but friction is.
- Difficulty: Low.

**BUG-13 — Minimum password length of 4 characters is too weak for a parental-control feature**
- Severity: Medium
- File: `focuslock_app.py`, `SetPasswordDialog._submit()`
```python
if len(new) < 4:
    self.error_lbl.setText("Password must be at least 4 characters.")
```
- Description: For a feature explicitly marketed to restrict access (including the "parent password" concept), 4 characters is weak, especially combined with BUG-12's lack of throttling.
- Fix: Raise minimum to 6–8 characters for the parent password specifically; the session password (self-imposed friction, not adversarial) can reasonably stay lower.
- Difficulty: Trivial.

**BUG-14 — Legacy unsalted-hash verification path has no forced migration**
- Severity: Low
- File: `core/security.py`, `verify_password()`
- Description: If a stored hash has no `:` separator, it's treated as a legacy unsalted SHA-256 hash and compared directly forever — there's no code path that re-hashes it with a salt after a successful legacy verification, so a user who set their password under v1/v2 stays on the weaker scheme indefinitely.
- Fix: On successful legacy verification, immediately call `hash_password()` fresh and write the new salted hash back to storage.
- Difficulty: Low.

**BUG-15 — Broad exception swallowing hides real failures**
- Severity: Low–Medium (varies by call site)
- Files: `blocking/website_blocker.py::unblock_sites`, `platform/startup.py`, `platform/notifications.py`, `config.py::_migrate`
- Description: Multiple `except Exception: pass` blocks silently discard errors including permission failures, malformed legacy JSON, and registry access failures. This is defensible for non-critical paths (a failed toast notification shouldn't crash the app) but currently applies uniformly even to security/data-relevant paths like hosts-file unblocking, where a silent failure means the user believes blocking has stopped when it hasn't.
- Fix: Differentiate — keep silent fallback for cosmetic paths (notifications), but log (even just to a local rotating log file — see Architecture section) and surface user-visible failure for anything that changes real system state (hosts file, registry).
- Difficulty: Low, but touches several files.

### 3.5 UI / State Sync

**BUG-16 — `_on_spin_changed` fires on programmatic value changes if `_spin_lock` isn't set in every code path**
- Severity: Low
- File: `focuslock_app.py`
- Description: `_spin_lock` is correctly used in `_set_preset()` to suppress signal storms, but `_toggle_theme()`'s theme-rebuild path (`_build_ui()` reconstructs all spinboxes from scratch) re-creates spinboxes with `setValue(pc["work"])` etc. **without** setting `_spin_lock`, because the new spinbox's `valueChanged` signal is connected *after* `setValue` is called in the constructor flow. This currently happens to be safe by construction-order accident, not by design — a future edit that changes connect-then-set-value ordering would silently reintroduce a preset-switch-to-Custom bug on every theme toggle.
- Fix: Add an explicit comment or, better, restructure so `_spin_lock` is always set during any programmatic spinbox update regardless of code path, rather than relying on connection ordering.
- Difficulty: Low (defensive fix, not an active bug today).

**BUG-17 — Tray tooltip and window title can go stale if the OS throttles a hidden/minimized window's Qt event loop**
- Severity: Low
- Description: Not observed directly in code but is a known PySide6/Windows behavior class — background timer ticks continue (separate thread), but UI-thread-marshaled label updates can lag when the main window is minimized to tray under aggressive OS power-saving. Flagging as a testing item rather than a confirmed bug.
- Fix: Verify empirically on a real Windows 11 machine with balanced/power-saver profiles; if confirmed, the tray tooltip update should not depend on the main window being visible.
- Difficulty: Low to test, unknown to fix until confirmed.

### 3.6 Dead Code / Cleanup

**BUG-18 — Stray file `tatus` (4.0K) at repo root**
- Severity: Low (hygiene)
- Description: A file literally named `tatus` sits at the project root — almost certainly an accidental `git add` of a truncated/misnamed file (possibly a stray `git status` redirect or a typo'd filename). It should be inspected and removed or `.gitignore`'d.
- Fix: Delete if confirmed unintentional; add to `.gitignore` if it's a recurring build artifact.
- Difficulty: Trivial.

**BUG-19 — `nuitka-crash-report.xml` (1.1MB) is committed to the repository**
- Severity: Low (hygiene)
- Description: A Nuitka build-crash report is checked into version control. This is a debugging artifact from a failed build, not source code, and bloats the repo.
- Fix: Remove from the repo and add `nuitka-crash-report.xml` to `.gitignore`.
- Difficulty: Trivial.

---

## 4. Missing Features Report

This section separates **genuinely half-built** items from **net-new features that don't exist yet** (correcting the brief's framing per the Correction Notice).

### 4.1 Session Naming — Currently: single field, works correctly, but limited
**Current state:** One free-text `session_name` setting, cached in memory, shown next to the timer and in tray tooltips/notifications. Persists correctly across restarts.
**Gap:** It's a single global label, not tied to individual sessions in history — you can't look back and see "Tuesday's 6pm session was called 'Thesis Ch. 3'." Renaming it just overwrites the one value going forward.
**Design for v4:**
- Add a `session_name` column to a new `Session` table (see §4.2) so each completed work interval stores the name that was active at the time.
- Keep the current single input as "current session name," but surface historical names in the stats/history view.

### 4.2 Session Segmentation — Currently: does not exist
**Current state:** Only aggregate daily totals (`sessions`, `minutes` per day) are stored. There is no record of individual work intervals — start time, end time, which preset was used, whether it was completed or abandoned.
**Design for v4:**
```
Session
├── id (pk)
├── date (str, ISO)
├── start_time (datetime)
├── end_time (datetime, nullable — null if abandoned)
├── planned_minutes (int)
├── actual_minutes (float)
├── preset_name (str)
├── session_name (str, nullable)
├── completed (bool)  # false if reset/abandoned mid-session
└── phase_breakdown (JSON: list of {phase, seconds} for future analytics)
```
`record_session()` in `config.py` becomes an insert into this table instead of (or in addition to) the daily rollup; `get_daily_stats()` becomes a `GROUP BY date` query over `Session` instead of a separately-maintained table, eliminating a class of double-bookkeeping bugs.

### 4.3 Daily/Weekly/Monthly Organization — Partially exists
**Current state:** `get_daily_stats(days=7)` exists and works. There is no week or month rollup, and the Stats page only ever shows a fixed 7-day bar chart.
**Design for v4:**
- Add `get_weekly_stats(weeks=8)` and `get_monthly_stats(months=6)` to `Storage`, implemented as `GROUP BY strftime('%Y-%W', date)` / `strftime('%Y-%m', date)` SQL, both trivial once §4.2's `Session` table exists.
- Add a view-toggle (Day / Week / Month) above the existing `BarChart` widget — the widget itself already accepts arbitrary `(data, labels)` so this is mostly a data-layer + toggle-button change, not a new chart component.

### 4.4 Achievements — Currently: does not exist
**Design for v4:**
- **Architecture:** a static `ACHIEVEMENTS` registry (like the existing `PRESETS`/`THEMES` dicts in `constants.py`) defining `{id, name, description, icon, condition_fn_key}`.
- **Progress tracking:** a new `Achievement` table storing `{achievement_id, unlocked_at}` — presence of a row means unlocked; no partial-progress state needed for a v1 (streaks/totals are already queryable from `Session`/`DailyStat`, so progress can be computed on demand rather than stored redundantly).
- **Unlock logic:** evaluated once per completed session (`_record_session()` already runs at the moment a work phase ends — call `check_achievements()` there) against simple predicates: total sessions ≥ N, streak ≥ N days, total focus hours ≥ N, "completed a Deep Work preset session," "used the app before 7am," etc.
- **Rewards:** for a local single-user productivity tool, keep rewards cosmetic and low-friction — a toast notification + a badge in a new "Achievements" panel on the Stats page. Avoid anything that gates functionality (that would conflict with the app's core promise of removing friction, not adding it).
- **Statistics integration:** achievements panel reads from the same `Session`/`DailyStat` queries already built for §4.2/4.3 — no parallel stats pipeline.

### 4.5 Statistics — Accuracy/reliability review
Current implementation is accurate for what it tracks (verified by reading `get_total_stats`, `get_streak`, `get_daily_stats` — the streak logic correctly handles "haven't recorded today yet" vs. "streak broken"). The main reliability risk is the double-bookkeeping described in §4.2: once individual `Session` rows exist, `DailyStat` should be either derived from them or removed entirely rather than maintained as a second source of truth (this directly serves the brief's Phase 4 "single source of truth" goal).

### 4.6 Settings — Persistence/validation audit
- **Persistence:** ✅ Confirmed correct — every setting round-trips through the `Setting` ORM table with JSON serialization.
- **Validation:** 🟡 Partial — spinboxes are range-clamped by Qt (`setRange`), but nothing validates that, e.g., `long_break < break` (a long break shorter than a short break is logically odd but currently allowed).
- **Synchronization:** 🟡 One real gap — `block_websites` setting is read fresh from storage on every toggle callsite (`self.storage.get("block_websites", True)`) rather than cached, which is inconsistent with how `session_name` is deliberately cached; this is a minor but real inconsistency in the data-flow pattern used across the file.
- **UI behavior:** ✅ Reasonable — toggles animate, settings apply live without restart (theme excepted, which rebuilds the UI, which is a heavier but correct approach).

---

## 5. Architecture Review

### 5.1 Current structure
```
FocusLock/
├── src/
│   ├── focuslock_app.py        # 1,322 lines — UI + business logic + orchestration, all in one QMainWindow subclass
│   └── focuslock/
│       ├── config.py            # Storage (SQLAlchemy) — clean, single responsibility
│       ├── constants.py         # Static data — clean
│       ├── core/
│       │   ├── timer.py         # PomodoroTimer — clean, focused, thread-safe
│       │   └── security.py      # hashing — clean, focused
│       ├── blocking/
│       │   ├── app_blocker.py   # clean, focused
│       │   └── website_blocker.py  # clean, focused
│       ├── platform/            # OS integration — clean, focused
│       └── ui/
│           ├── widgets.py       # reusable components — clean
│           └── dialogs.py       # picker dialogs — clean
```

**The pattern is clear: every module *except* `focuslock_app.py` follows single-responsibility well.** The one and only structural problem is that the main window class never delegates to a service/controller layer — it *is* the controller, the view-builder, and the password-policy enforcer simultaneously.

### 5.2 Recommended restructuring

Introduce a thin **application service layer** between the UI and the lower modules, without over-engineering a project this size:

```
focuslock/
├── services/
│   ├── session_service.py     # start/pause/skip/reset orchestration + work-time tracking
│   │                           # (currently: _toggle_timer, _skip_timer, _reset_timer, _track_work_time)
│   ├── blocklist_service.py   # app/site add/remove/toggle + sync to blockers
│   │                           # (currently: _add_app, _remove_app, _toggle_app, _add_site, ...)
│   ├── auth_service.py        # password set/verify/clear policy
│   │                           # (currently: _set_password, _require_password, _require_parent_password, ...)
│   └── achievement_service.py # (new, see §4.4)
├── ui/
│   ├── pages/
│   │   ├── session_page.py    # extracted from _build_session_page
│   │   ├── apps_page.py
│   │   ├── sites_page.py
│   │   ├── stats_page.py
│   │   └── settings_page.py
│   ├── widgets.py
│   └── dialogs.py
```

`FocusLockApp` becomes a thin shell: it constructs the services, constructs the pages (passing services in), wires signals, and owns the tray/window lifecycle — nothing else. This is the single highest-value structural change for maintainability, and it can be done **incrementally, page by page**, without a big-bang rewrite (each `_build_X_page` method is already reasonably self-contained, which makes this extraction lower-risk than it might sound).

### 5.3 Configuration system
Already good — `_DEFAULTS` dict + typed `get`/`set` is a sound pattern. Recommendation: add a lightweight schema/validation layer (even just a dict of `{key: (type, validator_fn)}`) so a corrupted or hand-edited DB value can't silently produce a wrong-typed value deep in the UI (currently `get()` will happily return whatever JSON-decodes, with no type check against `_DEFAULTS`).

### 5.4 Resource management
No test suite, no CI test job (CI currently only builds — confirmed via README's mention of `.github/workflows/build.yml` for build/release, no test workflow mentioned). Recommend:
- `pytest` for `core/timer.py` (fully unit-testable in isolation, no Qt dependency) and `config.py` (SQLite in-memory for tests) — these two modules are the highest-value, lowest-effort test targets since they have zero UI coupling.
- A GitHub Actions job that runs the test suite on every PR before the existing build job runs.

### 5.5 Logging
No structured logging anywhere — errors are either swallowed (`except: pass`) or never raised. Recommend a simple rotating file logger (`logging.handlers.RotatingFileHandler`) writing to `%APPDATA%\FocusLock\focuslock.log`, with the swallowed exceptions in §3.4/BUG-15 at minimum logged at `WARNING` level even where the UI stays silent.

---

## 6. Data Flow Review

Mapped against the brief's Phase 4 concern about multiple sources of truth:

| Data | Sources today | Verdict |
|---|---|---|
| Timer remaining/phase | Single source: `PomodoroTimer._rem`/`_phase`, read via locked properties | ✅ Single source of truth |
| Session name (current) | `self._cached_session_name` (in-memory) + `storage.get("session_name")` (persisted) | 🟡 Two representations, but the cache is correctly the read path and storage is only the write-through target — not fighting, but worth documenting explicitly as "cache + persistence," not "two sources" |
| Daily stats | `DailyStat` table only | ✅ Single source, but see §4.5 — will need to become derived once `Session` table exists in v4 |
| `block_websites` setting | Read fresh from storage at every call site (5+ places in `focuslock_app.py`) | 🟡 Not conflicting, but redundant DB reads where a cached value (invalidated on the Settings page toggle) would be both faster and more consistent with the `session_name` pattern already used elsewhere in the same file |
| Preset config | `self.preset` (in-memory) + `storage.get("preset")` (persisted) + spinbox widget values (UI state) | 🟡 Three representations kept in sync manually via `_spin_lock` and explicit `setValue()` calls throughout — this is the one place in the app that most resembles the brief's described "multiple sources fighting" problem, though the current manual-sync approach does work correctly as verified by tracing `_set_preset`/`_on_spin_changed`/`_apply_custom`/`_recreate_timer` |

**Recommendation:** Formalize the preset/spinbox relationship as a small `PresetController` (part of the `services/session_service.py` extraction in §5.2) that owns "current effective config" as one dict, with the spinboxes and preset cards as pure view reflections of it — removing the need for `_spin_lock` as a manual signal-suppression hack.

---

## 7. UX & UI Review

**Strengths (keep these):**
- Centralized `Theme` class with a single `apply_to_app` stylesheet — genuinely well done, avoids the scattered-inline-style anti-pattern common in Qt apps.
- Consistent card/button/toggle vocabulary across all five pages.
- Circular timer with phase-based color (purple=work, green=break) is a nice, legible, non-text-dependent status signal — though see the accessibility note below.

**Gaps:**
- **No keyboard shortcuts.** Start/pause, skip, and reset are mouse-only. A focus tool used by people who are, definitionally, sitting at a keyboard for extended periods should have global or in-window hotkeys (e.g. `Space` to start/pause).
- **No empty states designed.** The Apps/Sites pages when a user removes everything just show an empty scroll area with a "0 apps blocked" label — functional but not designed as a deliberate empty state with a call-to-action.
- **No loading state needed currently** (everything is local/synchronous), but this will matter the moment any network feature (e.g. optional cloud sync, mentioned as a future idea below) is added.
- **Error dialogs are inconsistent** — some failures (wrong password) show inline red label text in the dialog itself; others (hosts-file permission failure) show nothing at all (BUG-09). Standardize on one pattern: inline for form-validation-style errors, a toast/notification for background/system-level failures.
- **Accessibility:** color is the primary phase-change signal (purple/green ring + colored label text) with no alternative channel (shape change, icon, or explicit ARIA-equivalent for screen readers — Qt supports accessible names via `setAccessibleName`, currently unused anywhere). Recommend adding accessible names to interactive widgets and not relying solely on color for phase state.

---

## 8. Product Identity Recommendations

**On the proposed rename to "WorkPower":** the project already has a name — FocusLock — with a working tagline, a defined color system (`#8b5cf6` purple / `#34d399` green), a GitHub presence, and a README that markets it as a study/distraction-blocking tool specifically. "WorkPower" is a generic, unrelated name that would discard existing brand equity (however small) for no stated reason. **Recommendation: keep FocusLock** unless there's a business reason (trademark conflict, planned pivot away from the study/blocking use case) not visible in the repository. If a rename is truly desired, it should come from a positioning decision, not a code audit.

**Existing identity (already well-defined, documented for reference):**
- **Vision:** a lightweight, honest distraction-blocker for people (the README's tone — "Stop procrastinating" — reads student-focused) who need external enforcement, not just a timer.
- **Philosophy:** friction should point at distractions, not at the user — hence password-locking the *pause* button rather than the whole app.
- **Target audience:** students and self-directed workers who've already tried willpower-only Pomodoro apps and need enforcement.
- **Color psychology:** purple (focus/premium/calm) for work phases, green (positive/permission) for breaks — already a sound, conventional choice.
- **Tone of voice:** direct, low-fluff (confirmed by README copy and in-app label choices like "FOCUS TIME" / "BREAK TIME" in caps, no cutesy copy).

This is a coherent identity already. The task for v4 branding isn't inventing one — it's applying it more consistently (e.g., the app icon is currently the generic Qt `SP_ComputerIcon` standard icon, not a custom FocusLock mark — that's the one real identity gap worth fixing).

---

## 9. Future Feature Proposals

Prioritized by (productivity/focus impact) × (implementation cost given current architecture):

1. **Session history view** (depends on §4.2's `Session` table) — a scrollable list of past sessions with name, duration, completed/abandoned status. High impact, medium cost.
2. **Global hotkey to start/pause** even when the window isn't focused (Windows global hotkey via `ctypes`/`keyboard` lib) — directly serves the "reduce friction to start" goal. Medium impact, low cost.
3. **Achievements** (§4.4) — motivation/retention loop. Medium impact, medium cost.
4. **Week/Month stats views** (§4.3) — medium impact, low cost once `Session` table exists.
5. **"Strict mode"**: once a session starts, require parent password not just to pause but to *quit the app entirely* — closes a current gap where a determined user can bypass the pause-lock by just closing the app outright (worth flagging: right now `_quit()` doesn't check the session lock at all).
6. **Custom app icon + tray icon** replacing the default Qt icon — closes the one real identity gap noted in §8.
7. **Focus session notes**: a short text field per completed session ("what did you work on") — pairs naturally with §4.1/§4.2.
8. **Do Not Disturb integration**: toggle Windows Focus Assist on automatically during work phases, complementing app/site blocking. Novel, on-brand, low cost via existing `winreg`/`ctypes` patterns already used in `platform/`.
9. **Optional cloud backup of the SQLite file** (explicitly opt-in, given this is currently a fully local/offline tool by design) — larger effort, only worth it if user research shows demand for cross-device stats.

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Non-atomic hosts-file write corrupts system DNS resolution (BUG-08) | Low (needs a crash at exactly the wrong moment) | Severe (system-wide, outside the app's own data) | Atomic write via temp-file + `os.replace()` — should ship before any other change |
| User accidentally blocklists a critical system process (BUG-10) | Low-medium (manual "Browse .exe" is unrestricted) | High (can lock user out of their own shell) | Hardcoded denylist, cheap to add |
| Zero test coverage means every future refactor (including this roadmap's own §5.2 restructuring) risks silent regressions | High (inherent to current state) | Medium-high, compounding | Add `core`/`config` unit tests *before* starting the architecture refactor in Phase 1 of the execution plan below |
| Timer drift (BUG-01) undermines the core value proposition (accurate focus tracking) | Medium (worsens with longer sessions — Deep Work preset is 90 minutes) | Medium | Monotonic-clock fix is low effort relative to impact — prioritize |

---

## 11. Prioritized Roadmap

### Critical
| Task | Why it matters | Dependencies | Complexity | Impact |
|---|---|---|---|---|
| Atomic hosts-file write (BUG-08) | System-level corruption risk outside the app's own sandbox | None | Low | Prevents a severe, if rare, failure mode |
| `start()` reentrancy fix (BUG-04) | Can double the timer's countdown rate | None | Trivial | Correctness |
| AppBlocker critical-process denylist (BUG-10) | Can lock a user out of their own desktop | None | Low | Prevents severe user-facing harm |

### High Priority
| Task | Why it matters | Dependencies | Complexity | Impact |
|---|---|---|---|---|
| Monotonic-clock timer rewrite (BUG-01) | Timer accuracy is the core value proposition | None (isolated to `timer.py`) | Medium | High — trust in the core feature |
| `set_remaining` long-break clamp fix (BUG-02) | Silently truncates running long breaks | None | Low | Medium-high |
| Surface website-blocker permission failures to the user (BUG-09) | Currently fails silently, undermining the core promise | None | Low-medium | High — users currently *believe* they're blocked when they aren't |
| Unit tests for `core/` and `config.py` | Enables every subsequent refactor safely | None | Medium | Foundational |
| "Strict mode" quit-bypass closure (Future Feature #5) | Closes a real enforcement gap in the app's core promise | Auth service extraction (helps, not required) | Low-medium | High — directly on-brand |

### Medium Priority
| Task | Why it matters | Dependencies | Complexity | Impact |
|---|---|---|---|---|
| `services/` layer extraction (§5.2) | Long-term maintainability; unblocks parallel feature work | Tests in place first | High (but incremental) | High, long-term |
| `Session` table + session history (§4.2, Future #1) | Foundation for achievements, week/month stats, notes | Services extraction (helps) | Medium | High |
| Week/Month stats views (§4.3) | Rounds out the existing daily view | `Session` table | Low-medium | Medium |
| Password throttling + stronger parent-password minimum (BUG-12, BUG-13) | Closes a real, if soft, security gap | None | Low | Medium |
| Structured logging | Currently debugging silent failures is guesswork | None | Low-medium | Medium (developer-facing) |

### Low Priority
| Task | Why it matters | Dependencies | Complexity | Impact |
|---|---|---|---|---|
| Achievements system (§4.4) | Motivation/retention, not core function | `Session` table | Medium | Medium |
| Custom app/tray icon | Polish, closes identity gap | None | Low | Low-medium |
| Global hotkeys | Convenience | None | Low-medium | Medium |
| Keyboard accessibility pass | Inclusivity, polish | None | Low-medium | Low-medium |
| Repo hygiene (`tatus`, crash report file) (BUG-18, BUG-19) | Cleanliness | None | Trivial | Low |

---

## 12. Development Milestones (Execution Order)

**Milestone 0 — Safety net (before touching anything else)**
- Add `pytest` + unit tests for `core/timer.py` and `config.py`.
- Fix BUG-04 (`start()` reentrancy) — trivial, safe, and now test-covered.

**Milestone 1 — Stop the bleeding (Critical items)**
- BUG-08 atomic hosts-file write.
- BUG-10 critical-process denylist.
- Ship as a patch release; this milestone alone justifies a version bump given the severity of BUG-08.

**Milestone 2 — Fix what's currently silently wrong (High priority correctness)**
- BUG-01 monotonic timer rewrite.
- BUG-02 long-break clamp fix.
- BUG-09 surface blocking failures to the user.
- All covered by tests added in Milestone 0/expanded here.

**Milestone 3 — Close the core-promise gap**
- "Strict mode" quit-bypass (Future #5) — this is arguably the most on-brand, highest-leverage feature gap: right now the app's entire value proposition (external enforcement) has a one-click bypass (just quit the app).

**Milestone 4 — Architecture groundwork**
- Extract `services/session_service.py`, `auth_service.py`, `blocklist_service.py` from `focuslock_app.py` one at a time, keeping the app fully functional and tested after each extraction.

**Milestone 5 — Data model expansion**
- Introduce the `Session` table (§4.2), migrate `record_session()` to write to it, derive `DailyStat`-equivalent queries from it instead of maintaining both.
- Session history UI.

**Milestone 6 — v4 feature layer**
- Week/Month stats.
- Achievements.
- Session notes.

**Milestone 7 — Polish**
- Custom icon, global hotkeys, keyboard accessibility, repo hygiene cleanup.

Each milestone should ship independently and remain stable — this mirrors the brief's own Phase 10 instruction, and is achievable here because the existing module boundaries (outside the one God Object) are already clean enough to support incremental work.
