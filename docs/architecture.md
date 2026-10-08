# Authority and persistence

## Runtime boundaries

`client/main.gd` composes the Godot presentation. `network.gd` manages WebSocket lifecycle and sends intents; `state.gd` applies snapshots/deltas and reconciles local movement prediction. `movement.gd` mirrors the authoritative movement model. `landscape.gd` renders the visible world, layered scenery, particles, and explorers; `art.gd` generates and caches original 32-pixel item textures. `audio.gd` synthesizes interaction sounds.

`ui.gd` owns the HUD and shared styling. `front_menu.gd` provides the starting menu, account forms, saved-session continuation, and actual connection phases. `account_menu.gd` provides password/session settings and recovery-code handling. Gameplay interfaces are split between `panels.gd`, `world_catalogue.gd`, `social_panel.gd`, `gameplay_panel.gd`, `admin_panel.gd`, and drag/drop `slot.gd`.

`server/main.py` is the bounded network gateway and fixed 60 Hz simulation loop. `game.py` validates gameplay, owns player/world caches, and routes world-scoped events. `physics.py` implements collision clipping, variable jump height, coyote time, jump buffering, and sprint movement. `world.py` owns seeded generation, collision, and safe-spawn search. `inventory.py` provides copy-based stack operations and transfers. `shared/definitions.json` supplies stable item IDs, recipes, and movement configuration to both runtimes.

Feature components are `trading.py` for atomic exchanges, `admin.py` for role-checked grants/moderation, `accounts.py` for authenticated account security, `social.py` for durable friendships/blocks/favorites and personalized catalogues, and `mechanics.py` for timestamped processing, equipment, fishing, portals, and milestone rewards. `storage.py` persists accounts, worlds, inventories, sessions, crops, containers, drops, replay IDs, roles, moderation, and audit records.

Normal intents cannot supply a player position, set inventory, select drop rewards, accelerate mining/crops, override another world's permissions, or award progression rewards. Movement packets contain axis, jump-edge, jump-held, sprint, sequence, and movement-epoch information. The server consumes at most one queued frame per simulation step, ignores stale sequences and old world/connection epochs, bounds the queue, and stops stale controls. Client prediction responds immediately while authoritative acknowledgements correct its state.

Mining completion uses the server clock, selected tool, current tile, permission, and reach. Placement removes an item only after bounds, occupancy, support, overlap, permission, and quantity checks. Spawns choose a nearby clear, supported position in both axes. Sprint energy is authoritative; the client predicts its movement effect and reconciles it alongside position.

## Accounts and sessions

Password hashes use scrypt. Hashing runs outside the event loop, bounded to four concurrent gateway authentication operations; SQLite finalization stays on the authority thread and rechecks account state. Explorer names are validated and unique without case sensitivity. Registration grants a starter kit exactly once. The gateway validates authentication packet types, bounds their size, and rate-limits attempts. A successful same-account connection replaces its previous connection.

Sessions store a hash of a random bearer token and expire after 30 days. Remembering a device stores the token, explorer name, and server endpoint in native Godot user data or browser storage, never the password. Browser writes are synchronous so immediate reload retains the session; a logout marker prevents an older asynchronous save from restoring a revoked session. Logout revokes the token and clears the client's saved session. Password changes require the current password and revoke other saved sessions. Session cleanup and recovery-code rotation also require current-password proof.

Recovery uses a high-entropy, one-use code rather than email. The raw code is shown when issued; the server stores its digest and expiry. Codes last one year. Valid recovery changes the password, revokes every existing session, and creates a replacement code atomically. Issuing a new code invalidates the previous one. Credential revisions and rechecks after hashing prevent stale concurrent security requests from overwriting a newer update. Existing saves can add recovery through authenticated account settings.

The menu distinguishes transport connection, authentication, and world preparation without inventing download progress. Failed validation returns to usable forms, and invalid saved sessions can fall back to password sign-in. Account identity and recovery belong to one authority database; an unrelated server has separate accounts.

## Transactions and economy

WebSocket handlers invoke synchronous authority operations with no suspension inside a gameplay transaction. One process serializes SQLite `BEGIN IMMEDIATE` transactions. Transfers/crafting work on copied inventories; failed validation discards them. Valuable requests carry persistent per-account replay IDs. Rollback restores mutable cache state and pending events alongside SQL. Drops are consumed once, and container operations read current server contents rather than a stale client view.

A trade freezes inventory mutation/pickup and requires both explorers to lock and confirm the current offer revision. Offers, locks, confirmations, and active cancellation name a unique trade ID, so delayed packets cannot act on a replacement trade. Edits reset acknowledgements. The server rechecks quantities, range, participants, and capacity before committing both inventories and an audit entry together. Failed final validation cancels both sides without exchange. Disconnect, travel, panel closure, account takeover, blocked contact, and leaving range also cancel safely.

Autonomous mining and pickup commit tile/drop/inventory changes before publishing cache changes and events. A SQL failure leaves the tile or collectible available for retry. Mining an empty chest removes its obsolete container row. Crops use planted timestamps and registry growth/reward definitions; grain remains compatible with saved crops.

Processing jobs pay ingredients up front and save output, quantity, owner, station coordinates, and a wall-clock ready time. Jobs queue serially per station, with eight total and four per owner; a request can schedule 1–20 batches. Only the owner can collect a ready job. Full capacity rejects collection without losing output; collection deletes the job in the same transaction as the inventory reward. Stations with outstanding jobs cannot be mined. Offline time and restarts require no background simulation to finish processing.

Fishing checks the selected rod, nearby water, reach, persisted cooldown, energy, and inventory capacity before awarding a server-chosen catch. Equipment moves an item between inventory and a saved appearance slot; wearing/taking off cannot duplicate it. Milestone counters and distinct-world visits are server-recorded; each reward claim commits once with capacity validation. Portal configuration requires build permission and an existing world. Removal clears the saved link; travel resolves a safe spawn.

## Social catalogue

Friendships, pending requests, durable blocks, and personal favorites persist in SQLite. Friendship pairs use canonical order, and crossed requests can resolve into one accepted pair. Request/friend counts are bounded. Presence notifications follow joins, departures, and world changes rather than every simulation step.

Accepted online friends can exchange bounded text messages, invite each other to a world, or join a friend's actual server-known world. Clients cannot submit a friend's position as a travel destination. Messages and invitations are transient; there is no offline inbox. Blocks prevent contact and cancel active/pending trades. Chat and messaging respect administrator mutes.

New worlds are saved before their catalogue entry is broadcast. Rows combine stored metadata with current online counts and each viewer's favorites. Client filters and unfinished creation forms survive live row changes. Joining a friend's world does not grant edit permission; World Core ownership and builder/guest rules remain authoritative.

## Administrator access

`/addomen` requests the interface without granting a role. The server checks the persisted role on every action. Grants validate full capacity and reject active trades. Moderation and grants are audited; bans invalidate sessions and prevent sign-in/resume. Kicking or banning saves the online explorer's state, cancels their trade, and closes the connection. Administrators cannot kick, ban, or mute themselves or another administrator through this menu.

On the default loopback listener, the oldest account becomes owner when no administrator is configured; for a new save, the first account becomes owner. Public listeners require explicit `--admin NAME` and never appoint the first visitor automatically. Named roles persist. Create and secure the intended account locally before exposing a named administrator publicly.

## Save compatibility and performance

Schema 2 uses SQLite WAL and foreign keys. Its migration from schema 1 added roles/moderation; Stage 2 adds security, social, and mechanics tables without deleting progress. The version is checked rather than silently rewriting an incompatible database. Seed, biome, dimensions, and generation version describe initial terrain; only edited tile rows are stored. Generation-1 worlds preserve their original **144 × 56** terrain. New generation-2 worlds use **256 × 80** terrain with additional resources and ponds.

Crops store planted timestamps. Drops, containers, processing jobs, portals, equipment, milestones, friendships, and favorites persist. Inventories commit immediately. Movement and energy checkpoint periodically and on clean disconnect/shutdown; a crash can roll movement back to its last checkpoint while committed items/edits remain. Back up live saves through SQLite's backup API.

Only active worlds remain cached. Clients receive an entry snapshot and world-scoped entity snapshots at 20 Hz, then tile/drop/storage/metadata events after mutations. Rendering visits visible tiles and reuses generated textures. Rollback copies player/trade state and only terrain an action can mutate; selection/trading does not copy every cached world. Bounded connection writers prevent slow sockets from blocking simulation. World creation has a 100-world development cap. `/version` reports the release/protocol separately from the stable `/health` check so the launcher can recognize an older running build.

Chunk streaming, distributed simulation, measured player capacity, production telemetry, guilds, combat, shops, and a marketplace are future work. Stable definitions and separate components provide extension points. Remote hosting still needs TLS termination, backups, and operational testing.
