# Stage 3: The Living Loom

This is the proposed Stage 3 design, not a record of shipped features. The direction is a connected sandbox in which players build a world that responds to them: copper pulse networks animate workshops, gardens attract little creatures, and replaying light echoes turn a settlement into a cooperative playground. The distinctive part is the combination of building, visible world logic, habitat design, and playful shared performances. It should earn its identity through play; it does not depend on claiming that no other game has ever used an individual mechanic.

The existing game is the foundation: authoritative Python simulation, Godot presentation, stable item IDs, SQLite saves, predicted 60 Hz movement, friends, workshops, and world permissions. Stage 3 keeps those strengths and ships as several complete playable slices. A permanent internet connection comes first.

## 3.0 — Actually play together

**Release gate:** two players on separate devices and separate networks can open the same reachable URL, create separate accounts, see and interact with each other, reconnect, and retain their progress after an authority restart. Two tabs on one computer are useful regression coverage but do not satisfy this gate.

The launcher and starting menu must distinguish **Play locally**, **Join a server**, and **Host for friends**. A local authority at `127.0.0.1` is a local game, even when its simulation supports multiplayer. A friend's local static client page may instead connect to a remote LAN authority; that is one shared game. Host instructions should explain the endpoint friends select, the required shared authority, and whether the arrangement is LAN-only or internet reachable. Avoid presenting a local authority address as an internet invitation.

Godot 4.6.3 needs a browser secure context even with its threaded Web export disabled. Direct HTTP pages at private LAN IPs can fail before the game starts. The supported LAN route is therefore the host launcher plus a friend-side join launcher that serves current client files on localhost and connects to the trusted host's private WebSocket address. It creates no additional authority or save database. Public play uses a valid HTTPS page and WSS. Do not solve this by disabling browser security or asking players to install test certificates.

For regular internet play, use one persistent authority instance behind an HTTPS/WSS reverse proxy, a stable hostname, a durable save volume, and a tested backup/restore procedure. Do not silently create public administrator privileges. A temporary tunnel can help a short test, but an expiring tunnel URL is not a permanent release deployment. If durable hosting credentials or a domain are unavailable, finish the deployable configuration and report that exact remaining dependency rather than asserting the game is online.

The connection screen should identify the selected server, show genuine connection phases, retain useful errors, and offer a working retry. Joining a shareable server link preselects that endpoint; the link contains no session token, password, or recovery code. Accounts remain specific to that server. Publish the selected server's release/protocol and reject incompatible builds with an upgrade instruction before account creation.

Acceptance includes shared placement/mining, world catalogue updates, friends/invitations, storage and a completed trade; disconnect during a trade; same-account takeover; brief packet loss; authority restart; and another client joining through the public HTTPS address. Test actual browser WSS traffic through the proxy. Record what was tested externally and what was only simulated. Expose aggregate readiness, tick delay, online counts, queue pressure, and recent failure counts without exposing credentials or private messages.

## The first hour

1. Arrive at a colorful refuge and choose a solo or shared world. The field guide teaches movement, gathering, building, and the existing workshop without a wall of text.
2. Craft an **Attunement lens** from attainable cedar, copper, and glass. It reveals the pulse sockets of placed machines and nearby habitats.
3. Build a switch, copper thread, and pulse lamp. Press the switch: a clearly visible wave runs along the thread and lights the lamp. This is the first unmistakable new mechanic.
4. Add a pressure pad and harmonic gate to build a small jumping challenge. A friend can operate the pad; an Echo lantern can repeat the pad press when playing alone.
5. Plant a lantern garden beside a pond. Its shelter, plant variety, and light attract a glowfin. The journal explains why it appeared and which improvement would attract another species.
6. Start a settlement project with friends: build a **Sky bell**, supply its materials, and connect its three inputs. Coordinated pulses trigger a brief sky bloom, a shared celebration with an individual, once-only reward.

Each milestone works through the actual interface and supplies a reason to use the next system. Starter resources and recipe dependencies must make this route possible in every biome without administrator grants.

## 3.1 — Visible pulse building

The central system is a small, deterministic circuit simulation. Ordinary building stays fast; an explicit **Connect** mode adds an overlay above the existing terrain rather than replacing it with a new block layer. Builders connect neighboring sockets or lay copper thread. Surface connections may coexist with background scenery, but traversal and collision remain governed by real tiles.

| Component | Behavior | First use |
| --- | --- | --- |
| Hand switch | Emits one pulse on interaction, with a short authoritative cooldown | Light a path |
| Pressure pad | Emits on a real player's transition onto the pad | Cooperative jump puzzle |
| Copper thread | Passes a pulse to adjacent connected sockets | Visible wiring |
| Delay bead | Holds a pulse for a chosen 0.2–3 seconds | Stagger lights or gates |
| Splitter | Forwards to two chosen outputs | Garden/workshop branch |
| Harmony junction | Emits when both inputs arrive within a generous server-timed window | Duo puzzle |
| Pulse lamp | Lights briefly and shows the circuit's accent color | Immediate feedback |
| Harmonic gate | Opens for a bounded interval; safely defers closing over a player | Traversable puzzles |
| Clockwork valve | Lets a workshop use one admitted pulse per interval | Bounded automation |

Use integer simulation epochs at 5 Hz for pulse timing; do not trust a client's timestamp. Same-tick arrivals at a junction are ordered deterministically. A pulse carries a server ID and hop budget. Each node accepts a particular pulse once, so loops cannot multiply events indefinitely. Circuit inspection shows **Disconnected**, **Waiting**, **Blocked**, or **Running**, with the reason and a highlighted path.

Only owners/builders can configure circuits. Guest use of switches and pads is a separate owner-controlled permission; it never grants editing or item access. A gate cannot close over any explorer's collision box. After a bounded waiting interval it remains open with an obstruction indicator rather than crushing or trapping players. World travel and safe spawns account for the authoritative current gate state. Gate changes carry a geometry revision so prediction can reconcile against the same collision state.

Start with no more than 128 functional nodes and 512 thread cells per world. Limit a connected component to 128 nodes, each pulse to 64 hops, and admitted activity to 100 node visits per world per 5 Hz tick. Reach the limit gracefully with a clear inspector message, never a frozen server. These are initial development limits to measure and revise, not advertised capacity guarantees.

**Playable acceptance:** two real clients build a switch/lamp circuit, a delayed gate, and a two-pad junction. Both see matching effects. Guests cannot rewire it. Loops, rapid switching, removal during a pulse, failed SQL writes, restart, and occupied gate closure stay safe. Existing jump, mining, trade, and inventory regressions still pass.

## 3.2 — Echo lanterns and kinetic playgrounds

An **Echo lantern** records a deliberately started, short performance near it: up to six seconds of movement and emotes, sampled by the authority at 10 Hz. Recording does not capture chat, credentials, item commands, or other players' inputs. A preview appears before the builder chooses **Keep loop**. The lantern replays a translucent, animated light explorer with a visible start/end marker.

An echo is not a second player. It cannot mine, place, trade, collect, fish, operate containers, supply resources, or satisfy rewards that require a real explorer. It can activate specially marked **Echo pads** along its validated recorded path, allowing one player to build repeatable performances or solve a puzzle with their past movement. Ordinary pressure pads continue to require a real player. Recordings stay in the current world and cannot impersonate another account.

Cap each world at three active echoes, 60 samples per recording, and 30 seconds between recording requests. Playback has no full actor physics or general pathfinding: it reads compact samples, checks the associated pad's current existence and path validity, and emits a bounded circuit input. Editing the route pauses its affected pad activation until the owner previews and accepts it again. Removal deletes the recording. Time and cursor state are explicit in snapshots so late joiners see the same loop phase.

Add a small movement expansion that supports these playgrounds: a stamina-limited ledge mantle and decorative rope bridges. Mantling must have mirrored Python/Godot prediction, clearance checks, a short cooldown, and parity tests. Begin with rope bridges as ordinary supported platforms with convincing visual motion; swinging ropes and moving collision platforms are a later slice because they require substantially more reconciliation work.

**Playable acceptance:** a solo explorer records a pad route, combines it with a live jump, and opens a junction gate. A remote friend sees the loop and can complete the other input. Late join, restart, route editing, blocked geometry, deleted pads, and replayed requests cannot create items or escape world permissions.

## 3.3 — Habitats that reward building

Worlds should become more interesting because players build thoughtfully, not because a hidden global simulation runs forever. The lens reads bounded **8 × 8 habitat patches**: water, shelter, plant diversity, open floor, and light. These derive from actual tiles and cached changes; only dirty patches are rescored. The habitat panel says, for example, **Glowfin: pond ready · shelter ready · add one more plant type**, rather than exposing an opaque numerical grind.

Start with four gentle species: **glowfin** near lit water, **mossmoles** near sheltered earth, **dune kites** in open desert gardens, and **aurora wisps** around snowy crystal groves. Their silhouettes and movement differ. A creature's authoritative behavior uses a small finite-state machine: idle, wander, approach food, react to a pulse, return home. Keep behavior local to its home patch; no full-world pathfinding and no combat in the first habitat slice.

Feeding consumes a real held food item through an exact-once transaction. Species-specific cooldowns prevent item farming. Repeated care unlocks a cosmetic journal sketch or a decorative recipe rather than a permanent resource printer. Players can name a settled creature, choose a perch, and make it briefly respond to a circuit. Creatures do not attack visitors, eat saved construction, despawn treasured pets during absence, or block safe spawn.

Allow a world owner to disable wildlife. Default to at most 12 persistent creatures per world and four actively updated creatures near each explorer, deduplicated across nearby viewers. Simulate active creatures at 5 Hz and interpolate render animation. Unseen creatures sleep. Offline time preserves homes and care records; it does not replay every missed simulation step or punish the owner with starvation.

**Playable acceptance:** two clients build an eligible habitat and see the same arrival, movement, care state, and circuit reaction. Restart preserves a named creature. Invalid feeding, full inventory rewards, SQL failure, changing habitat tiles, and world permission changes cannot duplicate items or corrupt the home.

## 3.4 — Workshops and settlement projects

Expand existing timestamped jobs into a readable workshop, then add deliberately limited automation. A **Supply crate** holds materials assigned to a station. A **Collector tray** receives only that station's finished public automation jobs. Owners explicitly configure the recipe, batch cap, and permitted operators. Private Stage 2 jobs stay private and can still be collected only by their owner; importing a station does not silently redistribute somebody's paid output.

One clockwork valve pulse can start at most one batch after validating supply, output capacity, the configured cooldown, and permissions. Item movement from supply to job and job to tray is atomic and replay-safe. A full tray pauses the pipeline with visible **Output full** feedback; it never discards items. Wires carry signals, not arbitrary inventory access. Removing a station with outstanding work stays prohibited until safe collection or explicit owner cancellation/refund.

Pulse automation advances only while its world is active. Existing paid workshop jobs and crops retain their timestamp-based offline completion. The interface explains that distinction. This keeps offline outcomes bounded and avoids adding an expensive catch-up simulation to every server restart.

Settlement projects give groups shared goals with visible construction stages. The first three are **Sky bell**, **Lumen conservatory**, and **Wayfarer pavilion**. Each combines a bounded material depot, ordinary editable construction, and one small pulse challenge. Contributions debit inventory and credit the depot in the same transaction; a player sees their actual contribution before confirmation. Project removal/cancellation has one documented refund destination and cannot mint materials through repeated creation.

A completed Sky bell can trigger a 60-second sky bloom at most once per 30 minutes. Completion stores a world-specific achievement, and each eligible contributor claims its individual reward once. The challenge must work solo with echoes and become easier or more expressive with friends; arbitrary simultaneous-online counts must not block progress. Shared celebrations change light, particles, and music, never the durability of existing structures.

**Playable acceptance:** two accounts deposit materials, configure a one-recipe workshop, handle a full tray, and complete a Sky bell. Disconnect, concurrent collection, repeated request IDs, cancellation, and restart preserve exact totals. Performance remains acceptable during simultaneous circuits, workshop completions, and sky bloom effects.

## Presentation and interface

The new interface should make world systems understandable while leaving room to play. Use a compact context ribbon for the current tool and target, a persistent party strip showing invited friends and connection state, and a single dock with Backpack, Craft, World, Friends, and Journal. Keep existing keyboard shortcuts and offer rebinding. The lens overlay uses symbols and labels alongside color; a pulse never relies on color alone.

Crafting gains **pin recipe**, short dependency chains, and a **missing materials** list based on real inventory. Building gains a ghost preview with explicit rejection reasons, rotate/variant controls only for supported items, and an eyedropper that selects an owned item rather than granting it. A rectangular blueprint preview may place at most 8 × 8 ordinary decorative tiles, only after cost/permission/collision validation; exclude cores, chests, stations, portals, creatures, and circuit devices initially. Show total cost before commit. Multi-placement is atomic and a failed tile rejects the batch with its precise reason.

The journal becomes a map of discoveries and projects, showing short practical next steps. A local photo mode hides the HUD, pauses input, and captures a screenshot without altering simulation or revealing private conversations. Parties are temporary social groups, not a second account or a permission override: one joinable invitation, ready state, shared waypoint, and host-controlled puzzle restart. Keep notifications grouped and avoid opening modal panels over a moving player.

Visual direction: readable luminous pixels, richer terrain edge variants, plants that sway locally, warm interior light, gentle weather, and biome-specific ambient audio. Preserve clear avatar silhouettes and target highlights. Light sources and particles receive explicit quality budgets. Add reduced motion, particle density, UI scale, high-contrast labels, independent music/effects volume, and mouse/keyboard accessibility. Small-screen layouts collapse the dock and avoid covering the hotbar. Larger downloads should contain useful original art and audio, not filler to approach the 5 GB allowance.

## Persistence and implementation boundaries

Introduce an explicit, transactional **schema 3 migration** before these features, with a pre-migration backup and a startup version check. Keep all 177 existing item IDs and 150 recipes valid. Generation-1/2 world terrain must remain byte-for-byte compatible; new ruins and habitat starting patches belong only to new generation-3 worlds. Existing owners may place new items but their worlds are not regenerated or silently overwritten.

Suggested components are `server/circuits.py`, `server/echoes.py`, `server/ecology.py`, and `server/projects.py`, with corresponding focused client overlays/panels. Additive tables hold circuit devices/links/configuration/revisions, echo samples, habitat homes/creatures/care, automation configuration, project depots/contributions, and individual reward claims. Stable world/entity IDs and foreign keys support deletion and permission checks. Durable item-changing commands keep request IDs; autonomous station transitions also use unique job/state revisions. Feature code must extend rollback to every cache it mutates and publish events only after commit.

Handshake capability negotiation should advertise the supported content/protocol. Entry snapshots add bounded circuit, creature, echo, and project state; subsequent revisions carry only changed entities. Preserve 20 Hz explorer snapshots and separate slow feature updates. Do not put account data, private messages, or full recipes into every world entity snapshot. Interest filtering can be added for creatures/effects before attempting larger terrain or distributed simulation.

## Release order and measurable gates

| Slice | Deliverable | Required evidence |
| --- | --- | --- |
| 3.0 | Reachable shared internet game and clear hosting/join flow | Separate devices/networks; real HTTPS/WSS; restart and save retention |
| 3.1 | Switch-to-lamp, safe gates, two-input puzzles, circuit inspector | Two real clients; malicious loops; occupied gates; rollback and migration |
| 3.2 | Saved Echo lanterns and one complete solo/cooperative puzzle | Late join, restart, edited route, collision/prediction parity |
| 3.3 | Four habitat species, clear eligibility, persistent care | Shared authoritative creatures; bounded CPU; permission/economy regressions |
| 3.4 | Supply/tray automation, three projects, first sky bloom | Exact item conservation; restarts; full outputs; public play session |
| 3.5 | Presentation, access settings, pinned crafting, safe blueprints | 720p and 1080p UI; real control flows; performance and save regression |

For initial development, benchmark a modest target of **16 explorers across four active worlds** on a documented host, including 100–250 ms simulated round-trip delay and short packet loss. Keep movement simulation at 60 Hz: a proposed acceptance target is p95 authority tick work below 8 ms and p99 below 16.7 ms during the scripted load, with bounded queues and no growing memory after a 30-minute soak. Measure clean join time and bytes, client frame time on a documented reference device, and gate/creature corrections under latency. These are targets to validate, not current measured results. Reduce feature/entity limits if the measurements fail.

Each slice must pass the full existing integration suite, the actual Godot initialization/export checks, and its focused two-client browser scenario. Run old-save migration, forced restart, fault-injected writes, simultaneous actions, duplicate/stale requests, and inventory conservation tests when a slice changes those boundaries. Re-run the internet acceptance gate on the final frozen export. An attractive local demo is not sufficient proof of usable online multiplayer.

Combat, large bosses, a player marketplace, monetization, unrestricted logic programming, unlimited offline factories, moving physics platforms, cross-server accounts, and distributed world servers should follow only after these playable slices justify them. Stage 3 succeeds when a small group can reliably join, build a recognizable living settlement, invent a clever circuit, and leave with a story they created together.
