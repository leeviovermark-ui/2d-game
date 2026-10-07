# Authority and persistence

## Boundaries

`client/main.gd` composes the Godot presentation. `network.gd` handles WebSocket lifecycle and sends only intents. `state.gd` reads server snapshots/deltas; `landscape.gd` renders visible tiles, interpolated players and parallax; `ui.gd` owns the HUD/login and `panels.gd` owns gameplay panels; `slot.gd` implements drag/drop; `art.gd` and `audio.gd` produce original assets.

`server/main.py` is the bounded network gateway and fixed 30 Hz simulation loop. `game.py` validates gameplay and routes world-scoped events; `trading.py` owns the exchange state machine. `world.py` owns generation, collision, and validated spawn search. `inventory.py` provides pure copy-based stack operations. `storage.py` persists accounts, inventories, tile deltas, crops, containers, drops, sessions, replay IDs, and audit records. `shared/definitions.json` supplies item/recipe/movement definitions to both runtimes.

The client cannot set positions, create items, choose drop rewards, set inventory, accelerate mining, mature crops, change another owner's permissions, or exchange assets directly. Movement packets contain only axis/jump intents. Mining completion uses the server clock, the selected tool, current tile, permission, and reach. Placement removes one item only after bounds, occupancy, support, player overlap, ownership, and quantity checks.

## Transactions

WebSocket handlers call synchronous authority operations with no suspension inside a transaction. One process serializes SQLite `BEGIN IMMEDIATE` transactions. Inventory transfers/crafting work on copies; validation failure discards them. Valuable requests have persistent per-account replay IDs. The cache and pending events roll back with a failed request. Drops are consumed once, and chest transfers re-read the current container instead of trusting a client's stale slots.

A trade freezes inventory mutation and pickup, then requires two locks and two confirmations on the current offer revision. Any offer change resets all acknowledgements. The server rechecks item quantities, range, both players and capacity before writing both inventories and an audit record in the same transaction. No assets are removed just to form an offer. Disconnect, world travel, closing the panel, account takeover, and leaving range cancel safely.

## Persistence and performance

Schema 1 uses SQLite WAL and foreign keys. Initial terrain is reconstructed from a saved generation seed/biome; only changed tile rows are written. Crops store planted timestamps and need no unloaded-world tick. Drops and chest contents persist. Changed inventories commit immediately; movement checkpoints occur every two seconds and on a clean disconnect/shutdown. An abrupt crash can roll position back by up to two seconds; committed items and tile changes survive. The schema version is checked rather than silently rewriting an incompatible database.

Active worlds alone live in the authority cache. Clients receive an initial bounded-world snapshot on entry, world-scoped entity snapshots at 15 Hz, and tile/drop/storage/metadata deltas after mutations. Rendering visits only the viewport's visible tile region. World requests snapshot the current small cache for rollback correctness; this should become a mutation journal before increasing world/player limits. The 100-world creation cap is an explicit development limit.

## Extension paths

Stable item IDs, central recipes, and item categories can add new blocks and stations without duplicating registries. Timestamped crops illustrate the offline-processing model for future machines. Delta tables and world routing can evolve toward chunk snapshots/interest regions. Economic audit and atomic inventory operations can support shops and market transactions, but neither system exists yet. Logic objects and combat should be separate authoritative components, never client-awarded effects.

Do not add an unrestricted admin packet to the normal gateway. Tests may construct authority state directly inside an isolated database; those helpers are not exposed to players. Remote deployment needs TLS termination, backups, account recovery, moderation, operational metrics, and load testing beyond this local vertical slice.
