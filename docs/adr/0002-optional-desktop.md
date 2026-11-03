# ADR 0002: Optional desktop with a measured resource budget

Status: proposed, 2026-11-03. This records a direction and acceptance gates; no GUI is shipped yet.

## Need and approach

A Linux Mint desktop can make capture, search, corrections, and protection status convenient. Reliability remains in the existing local catalog and recovery commands. The desktop must not create another catalog authority, duplicate the schema/mutation logic, or be required for backup and recovery.

Use Tauri with a small Svelte frontend for a measured prototype. Svelte with Vite is sufficient for a few screens; SvelteKit is also suitable when routing or a later shared web frontend warrants it. For SvelteKit, package static assets with `adapter-static` and client-side routes; no Node server or SSR runtime ships in the desktop app. Verify the current stable framework versions and lock dependencies when the experiment begins.

Tauri uses a system webview on Linux (WebKitGTK) and multiple processes. A smaller distributable does not prove smaller resident memory or lower CPU. Test the release package on the actual Mint version, including its WebKitGTK dependencies and graphics/session configuration. Prefer a native `.deb` for the first Mint acceptance run; evaluate other packaging only against concrete distribution needs. See [Tauri's process model](https://v2.tauri.app/concept/process-model/), [SvelteKit integration](https://v2.tauri.app/start/frontend/sveltekit/), [Linux prerequisites](https://v2.tauri.app/start/prerequisites/), and [Debian packaging](https://v2.tauri.app/distribute/debian/).

## Integration boundaries

- Invoke a small allowlist of domain commands through typed Rust IPC and argument arrays, with no shell interpolation or arbitrary executable access from the webview. Initially call the existing Python CLI on demand rather than rewriting transactional guarantees in Rust.
- Keep credentials and replica I/O outside the webview. Represent saved-local/backup-pending states explicitly, preserve the returned request ID across a retry, and show exactly which protection checks passed.
- Use one window, system fonts, bounded result pages, and a debounced search. No dashboard polling, animations, embedded audio engine, background file indexing, startup-at-login, or tray residence in the first slice. Refresh after an action or explicit request.
- Closing the last window exits the GUI and its workers. Existing CLI playback remains a separate user-started process. Backup can use explicitly configured systemd one-shot jobs without keeping the desktop running.
- Development tooling remains a build dependency. Python/SQLite CLI usage must not require Node, Rust, Tauri, a webview, or the GUI package.

## Proposed acceptance budget, not measurements

Measure a release build with synthetic catalogs of 100 and 10,000 tracks, no audio downloads, and the intended Mint hardware/session. Record cold/warm launch time over five runs, sum proportional set size (PSS) for the app's full process tree, and observe idle CPU over 60 seconds after settling for 30 seconds. RSS alone double-counts shared pages, and app-wide measurements must include webview/helper processes.

Initial goals: at most 100 MiB total idle PSS, less than 0.5% of one logical CPU on average at idle, warm launch within two seconds, and no remaining app process after closing the last window. These are proposed pass/fail targets; no claim is made that Tauri already meets them. Record the machine, OS, framework versions, dataset, process tree, and results before accepting the desktop. If the prototype misses the budget, simplify it or retain the CLI/TUI path before adding screens or features. No GUI is the lowest idle-cost option when it is unnecessary.

Test an offline capture, a failed backup followed by an idempotent retry, the existing correction/history invariants, and reopening the same catalog through the CLI after GUI exit. A GUI must earn its place through measured convenience and cost without changing recovery semantics.
