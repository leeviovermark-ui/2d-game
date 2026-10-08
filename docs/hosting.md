# Playing together and persistent hosting

WORLDFORGE has one authoritative multiplayer server. To play together, everyone must connect to **the same server**, and each player needs a different account. Starting a separate local server on each computer creates separate accounts and worlds. Signing in twice with the same account replaces its previous connection.

`127.0.0.1` and `localhost` always mean the computer opening the address. A local game authority and a local client page are different: the LAN join launcher serves the browser client locally while connecting it to the host's remote authority. A localhost URL is never an internet invitation address. The container setup below is a persistent self-host deployment configuration. It does not create a cloud account, provision a machine or hostname, or establish that your server is already reachable from another network.

| Arrangement | Who can join? | Address friends open |
| --- | --- | --- |
| Local launcher | Browsers on the same computer | `http://127.0.0.1:8765` |
| Trusted LAN host | Computers on the same reachable local network | Join launcher, using the host's LAN address |
| Temporary HTTPS tunnel | Internet players while the tunnel and authority run | The tunnel's current HTTPS URL |
| Persistent self-host server | Internet players while the deployed host runs | Your stable `https://game.example.com` address |

## A trusted LAN game

Everyone extracts the current playable ZIP. One person hosts the authority; friends run the client join launcher. On Windows:

1. The host opens **Host-WORLDFORGE-LAN.bat**, then shares the LAN server address printed in its window, such as `http://192.168.1.50:8765`. Keep the host window open.
2. Friends open **Join-WORLDFORGE-LAN.bat** and paste that host address when prompted. Keep the join window open too. Each friend creates or signs into a separate account, then chooses the same world as the host.

On Linux/macOS, the host starts:

```sh
python3 scripts/play.py --host 0.0.0.0
```

Friends start:

```sh
python3 scripts/join_lan.py --server http://HOST_LAN_ADDRESS:8765
```

The join launcher opens a browser page at `http://127.0.0.1:8770` on the friend's computer and connects it to `ws://HOST_LAN_ADDRESS:8765`. It serves only the local client files; it does **not** create another authority, account database, or separate world. `--port` can change the local page port if 8770 is occupied. The join launcher accepts a private RFC1918 IPv4 address; use the public HTTPS URL directly for internet play.

This distinction fixes a real browser requirement: the Godot 4.6.3 Web client uses APIs that require a secure context, even with its threaded export disabled. Opening an ordinary `http://192.168.x.x:8765` page directly can leave the game unable to start. Loopback client pages are browser-trusted contexts; a valid public HTTPS page also works. The host launcher opens its own localhost page. Do not install test certificates, disable browser security, or treat a direct private-IP HTTP page as the normal playable invitation.

Allow TCP port 8765 through the **host's** firewall for the trusted local network. The supplied address must be the host's LAN address, not a friend's address or `127.0.0.1`. If the browser asks for permission to reach devices on the local network, allow the connection to your trusted host. Hotel/public Wi-Fi, guest networks, or router client isolation may prevent devices from reaching one another. LAN WebSocket traffic is unencrypted, so use this flow only on a trusted local network. Use the HTTPS/WSS deployment below for internet play.

## A permanent HTTPS server

Use a Linux host with Docker Engine and the Docker Compose plugin, a stable public IP address, and a hostname you control. Point that hostname's DNS A record to the host; add an AAAA record only if the host is actually reachable over IPv6. Allow incoming TCP ports **80 and 443** in the host/cloud firewall. UDP 443 enables optional HTTP/3; TCP HTTPS/WSS still works without it. Keep the game authority's port 8765 unpublished.

The example uses one authority process and a persistent SQLite volume. Do not horizontally scale the game service or let multiple authority processes write the same save. Start with a small group: large public-server population capacity has not been established.

1. Put the current source or extracted playable bundle on the host. A source checkout needs its Godot Web export first: `bash scripts/export_web.sh`. The playable bundle already includes `build/web`. Docker does not build or install Godot.
2. From the WORLDFORGE repository/bundle root, set your hostname and optional certificate-contact email. Supply a plain hostname, without `https://` or a path:

   ```sh
   export WORLDFORGE_DOMAIN=game.example.com
   export WORLDFORGE_ACME_EMAIL=you@example.com
   docker compose -f deploy/compose.yaml config --quiet
   docker compose -f deploy/compose.yaml up -d --build
   ```

3. Check startup and the public endpoint:

   ```sh
   docker compose -f deploy/compose.yaml ps
   docker compose -f deploy/compose.yaml logs --tail=80 game proxy
   curl --fail https://game.example.com/health
   curl --fail https://game.example.com/version
   ```

4. Open `https://game.example.com` from another device, preferably through cellular data rather than the host's Wi-Fi. Share that exact URL. Each player creates their own account on this server, then travels to the same world. New accounts receive a recovery code; save it privately.

Caddy terminates HTTPS, automatically obtains/renews certificates for the configured hostname, serves the game through the authority, and forwards WebSocket upgrades. Certificate issuance depends on working DNS, public reachability, certificate-authority limits, and persistent Caddy state; configuration alone cannot guarantee it.

The authority runs as UID/GID **10001**, with a read-only application filesystem and a writable `/data` volume. Personal saves never enter the Docker build context. The image checks that the exported HTML, WebAssembly, and game data are present and retains the bundled font and Godot engine notices in `/app/licenses`. A local `/health` probe controls service startup; it is not proof that a friend can reach your public hostname or sign in.

The private Docker network uses `172.30.86.0/24`; Caddy is `172.30.86.2` and the authority is `.3`. The authority trusts **only Caddy's exact address** for forwarded client IPs, and Caddy replaces incoming `X-Forwarded-For` with its connecting client's address. This preserves per-client rate limits and prevents visitors from selecting arbitrary rate-limit identities. If this subnet conflicts with your host, change the subnet, both static addresses, and the authority's `--trusted-proxy` value together. Do not publish 8765 or trust all proxy addresses to work around a conflict. Putting another reverse proxy/CDN in front requires a deliberate matching trusted-proxy/header configuration and another test of actual client identity.

The Compose project name is **worldforge**. Keep that name stable across updates: it identifies the persistent save and certificate volumes. The Docker image tag may be replaced by a new build without replacing the data volume. For a repeatable release rollout, keep a copy of the deployed source/commit and the backup used for that upgrade.

## Import an existing save

Stop the old server cleanly. Import its stopped `data/worldforge.sqlite3` into the new volume **before accepting new accounts**. Importing an old save replaces the new server's account/world database; do not merge two live databases or copy a database over a running authority.

For a newly created Compose save volume, this command uses the same image in a temporary import process. Run it from the bundle root, with the old stopped save at `data/worldforge.sqlite3`:

```sh
docker compose -f deploy/compose.yaml stop game
docker compose -f deploy/compose.yaml run -T --rm --no-deps --user 0:0 \
  --cap-add DAC_OVERRIDE --cap-add CHOWN \
  --entrypoint python -v "$PWD/data:/import:ro" game - <<'PY'
from pathlib import Path
import os, shutil, sqlite3, tempfile

original = Path('/import/worldforge.sqlite3')
assert original.is_file(), 'The stopped source save is missing.'
# Stage the stopped main file and any WAL in a writable temporary directory.
# Read-only mounted WAL databases may need to recreate a shared-memory file.
with tempfile.TemporaryDirectory(prefix='.import-', dir='/data') as staging:
    saved = Path(staging) / 'worldforge.sqlite3'
    for suffix in ('', '-wal'):
        source_file = Path(str(original) + suffix)
        if source_file.is_file():
            shutil.copyfile(source_file, Path(str(saved) + suffix))
    source = sqlite3.connect(str(saved))
    target = sqlite3.connect('/data/worldforge.sqlite3')
    source.backup(target)
    target.close()
    source.close()
for suffix in ('', '-wal', '-shm'):
    target_file = Path('/data/worldforge.sqlite3' + suffix)
    if target_file.exists():
        os.chown(target_file, 10001, 10001)
PY
docker compose -f deploy/compose.yaml up -d
```

The staged copy and backup API respect any remaining WAL pages from the stopped source. This one-off import runs with permission to read private host files and restores ownership to UID 10001; the normal authority still runs without those capabilities. The import uses temporary space on the data volume and leaves the original read-only. Keep the original save intact until the deployed accounts, inventory, edits, and worlds have been verified. Administrator roles in the imported save persist.

## Choose an administrator

Public mode disables automatic local administrator bootstrap, even behind a loopback tunnel. Do not appoint the first internet visitor or reserve an unregistered administrator name on a public server.

For a new save, start the authority privately, create your intended account, and stop it before enabling public access. Then grant that existing account with the administrative CLI, using the same save volume. For an already deployed server, stop public access briefly so no user can claim the intended name during setup. Confirm that the intended account already exists. For example, with the proxy and authority stopped:

```sh
docker compose -f deploy/compose.yaml stop proxy game
docker compose -f deploy/compose.yaml run --rm --no-deps game \
  --host 0.0.0.0 --public --database /data/worldforge.sqlite3 --admin YourExplorerName
```

Wait for startup, then press **Ctrl+C** to stop the one-off authority cleanly. The role is persisted; the usual `docker compose -f deploy/compose.yaml up -d` can resume hosting. Administrators open the menu with `/addomen`; ordinary accounts do not receive privileges by typing it. Imported local-owner saves may already contain an administrator, so verify roles before granting another one.

## Back up and update

SQLite WAL databases need a consistent backup. Copying only a live `.sqlite3` file can omit committed WAL changes. Use SQLite's backup API or stop the authority before copying the complete save state. The live backup below writes a new database into the data volume without blocking normal play for the entire copy:

```sh
docker compose -f deploy/compose.yaml exec -T game python -c \
  'import datetime,sqlite3; stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"); source=sqlite3.connect("/data/worldforge.sqlite3"); target=sqlite3.connect("/data/backup-"+stamp+".sqlite3"); source.backup(target); target.close(); source.close(); print("Backup saved in /data/backup-"+stamp+".sqlite3")'
```

Copy the resulting named backup from the container to a private location outside the host, and test restoring it to a temporary server before relying on it. Backups contain account hashes and player information; keep them private. The Caddy `/data` and `/config` volumes retain certificate/renewal state and should also survive upgrades.

Before each upgrade, make a backup, stop the authority cleanly, install the new source/bundle and Web export, then rebuild/start:

```sh
docker compose -f deploy/compose.yaml stop game
docker compose -f deploy/compose.yaml up -d --build
```

`docker compose down` retains named volumes unless explicitly told to remove them. **Do not use `down -v` during an update**: it removes the save and Caddy volumes. After an upgrade, verify `/version`, sign in from a second network, confirm a saved world edit, and check that another account joins the same world. If an upgrade fails, stop the authority and restore the consistent backup into its volume before restarting the matching previous release.

## What proves online multiplayer

A working public game needs more than `/health`. Use two separate devices/networks and different accounts through the public HTTPS URL. Confirm both explorers are visible in one world, chat and build together, create a world and see it in the other catalogue, send/accept a friend invitation, and complete a trade. Disconnect during a trade and verify cancellation without item loss. Restart the authority and verify saved accounts, inventories, tiles, and automatic reconnect. The browser must use **WSS**, and no passwords/session/recovery codes belong in screenshots or logs.

If only the host can connect, investigate DNS, firewall/router forwarding, IPv6 configuration, and the proxy logs. If both players connect but cannot see each other, compare server URLs and world names and confirm they use different accounts. If an HTTPS page reports a WebSocket failure, check that the client selected WSS and that the proxy forwards upgrades. If many unrelated players share a sign-in rate limit, verify trusted proxy/header configuration instead of disabling the limit.

This deployment pack supplies a persistent hosting path. Actual public deployment, certificate issuance, separate-network play, and population limits must be verified on the chosen host; they cannot be certified merely by including these files.
