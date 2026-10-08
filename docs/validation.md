# Validation record

## Graphics, movement, content and administration upgrade — 2026-10-08

- **All 82 tests passed in the complete integration suite** in 11.300 seconds. Coverage includes the existing gameplay, persistence, live-network, crash-recovery, and Windows-startup checks; 26 administrator/authentication checks; eight movement/parity/prediction tests; six input-queue/slow-writer tests; and 16 economy/spawn/SQLite regressions.
- **Actual Godot and Python movement matched nine complete trajectories**, comparing every frame's position, velocity, grounded status, coyote timer, and jump buffer. Numeric tolerance was 0.0003 tiles and grounded status matched exactly. Scenarios included acceleration/braking, held and tapped jumps, a wall, a ceiling, terminal-speed falling, world bounds, coyote time, and a buffered landing jump.
- **The actual Godot prediction state passed 16 checks**: movement and presentation update before another server snapshot; acknowledgements remove only completed inputs and replay the rest; duplicate acknowledgements do not rewind prediction; pending history stays bounded; world changes reset input history, visual correction, and remote samples; movement epochs change with the world; and remote interpolation remains finite between snapshots.
- **Input and network regressions passed** for burst inputs, duplicate/stale sequence numbers, old movement epochs after world travel, expired controls, stalled socket writers, and bounded queue overflow. Password scrypt hashing runs outside the event loop with at most four concurrent gateway authentication operations; SQLite account/session finalization remains on the authority thread and rechecks state after hashing.
- **Economy regressions passed** for stale trade packets naming a replaced trade, missing trade IDs, boolean revisions, failed final capacity checks, missing offered items, and a partner moving away before the next tick. Failed final validation cancels both sides without exchanging items. Injected SQLite failures during mining, pickup, and partial pickup preserved both cache and database state, and successful retries created/collected items once.
- **The current registry contains 48 items and 33 recipes.** All drop, placement, recipe output/ingredient, and station references resolve to known stable IDs; stack limits are valid. Seeded terrain generation remains unchanged for save compatibility.
- **Godot native initialization and Web export passed.** The updated exported client completed the two-browser gameplay test, including the actual 90-second crop cycle, multiplayer movement/jumps, mining and pickup, synchronized placement, storage, crafting, trade confirmations, world travel/claims, chat, and saved-session reconnect without runtime errors.
- **Additional browser checks passed** for the forest, desert, snow, and underground presentations and the actual administrator interface, including granting 99 lamps through the menu. The server uses 60 Hz movement and 20 Hz entity snapshots with bounded per-client writers.

A scoped local benchmark measured the terrain-copying improvement with five authenticated players in five active seeded worlds. Thirty real SQLite-backed hotbar selection requests used the previous `Game` implementation from Git `HEAD` and the upgraded implementation with the same current registry and store. Median action time fell from **27.074 ms to 0.193 ms**, and the 95th percentile fell from **30.883 ms to 0.396 ms**. This measures selection-handler cost on this host; it is not a frame-rate or network-latency benchmark.

Checks use temporary saves. Native Windows execution, production load, public deployment, and cloud environment publication remain outside this validation. The unsupported Windows signal-handler path is covered by the existing startup regression.

## Original development slice — 2026-10-07

- **25 authority, persistence, live-network, and crash-recovery tests passed** with `.venv/bin/python -m unittest discover -v`.
- **Godot 4.6.3 native scene initialized without script/runtime errors** with `scripts/check_client.sh`; this helper checks Godot's error output as well as its exit status.
- **Godot Web release export succeeded** using the official templates after verifying their upstream SHA512 checksum.
- **Two actual exported Godot clients passed in headless Chromium** using `python3 tests/browser_smoke.py`. Both created accounts against a temporary real server and database; no players were simulated by the client.
- The browser run verified server-driven movement/jumps, visible multiplayer, mining/pickup, synchronized placement, inventory drag/split, recipe crafting, chest deposit/withdrawal, exact-offer trade locks and confirmations, world creation/travel/ownership, builder permissions, world chat, saved-session reconnect, and retained inventory.
- A crop grew for the actual **90 seconds**, including time while its world was unloaded, and was harvested through the Godot interface.
- Separate tests forcibly killed a running authority process after committed changes, restarted it, and recovered ownership, blocks, crop timestamps, inventory, and the reconnect session from SQLite WAL.
- Current-instance `/health` and browser export requests succeeded. Reusable `install_script` and `start_skill` were saved to the cloud environment draft; publication and restoration into a new task have not been tested.

The tests use isolated temporary saves. Screenshots generated by browser validation are in ignored `artifacts/`. Large-scale load testing, production TLS/operations, and the future systems listed in the README are outside this slice.

## Windows startup correction — 2026-10-08

Fixed the unsupported `asyncio.add_signal_handler` startup path on Windows using standard signal handlers that schedule graceful shutdown on the event loop. All 26 tests passed, including real server startup/authentication/shutdown with the Windows unsupported-loop behavior reproduced on the Linux test host. A native Windows host was not available for this run. The downloadable browser bundle was refreshed.
