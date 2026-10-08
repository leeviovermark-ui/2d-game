extends SceneTree
## Real UI validation and connection state checks without exposing credentials.
var failures: Array = []
var checks := 0
var submits: Array = []

func _initialize() -> void:
	run.call_deferred()

func verify(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)

func run() -> void:
	var ui = load("res://client/ui.gd").new()
	ui.state = ForgeState.new()
	ui.art = ForgeArt.new()
	ui.login.connect(func(endpoint,credentials): submits.append({"endpoint":endpoint,"credentials":credentials}))
	root.add_child(ui)
	await process_frame
	var menu = ui.front_menu
	verify(menu.mode == "title","A starting menu opens before account entry")
	verify(menu.buttons.has("play"),"The starting menu has a real Play button")
	verify(menu.server_location.text.begins_with("THIS COMPUTER"),"A local starting menu identifies the server as this computer")
	verify("Friends need" in menu.server_hint.text,"Local play explains that friends need a reachable server")
	verify(menu.initial_endpoint(true,"http:","shared.example:8765","ws://127.0.0.1:8765") == "ws://shared.example:8765","HTTP browser defaults use the page host rather than stale local preferences")
	verify(menu.initial_endpoint(true,"https:","play.example","ws://192.168.1.20:8765") == "wss://play.example","HTTPS browser defaults use secure sockets on the page host")
	verify(menu.initial_endpoint(false,"","","wss://play.example") == "wss://play.example","Native client retains a valid manually chosen server")
	verify(menu.initial_endpoint(false,"","","not-a-server") == "ws://127.0.0.1:8765","Malformed native preferences fall back to a usable local address")
	for local_page in ["127.0.0.1:8770","localhost:8770","[::1]:8770"]:
		verify(menu.initial_endpoint(true,"http:",local_page,"ws://127.0.0.1:8765","ws://192.168.1.10:8765") == "ws://192.168.1.10:8765","An explicit private LAN join overrides stale preferences only on a loopback client page")
	for private_server in ["ws://10.1.2.3:8765","ws://172.16.2.3:8765","ws://172.31.2.3:8765","ws://192.168.1.10:8765"]:
		verify(menu.validated_lan_join(true,"http:","127.0.0.1:8770",private_server) == private_server,"Explicit loopback joins allow only valid RFC1918 IPv4 authorities")
	for rejected_join in ["ws://8.8.8.8:8765","ws://127.0.0.1:8765","ws://169.254.1.2:8765","ws://172.15.2.3:8765","ws://172.32.2.3:8765","ws://host.local:8765","ws://user@192.168.1.10:8765","ws://192.168.1.10:8765/path","ws://192.168.1.10:8765/","ws://192.168.1.10:8765?secret=bad","ws://192.168.1.10:8765#fragment","ws://192.168.1.10","ws://192.168.1.10:0","wss://192.168.1.10:8765","http://192.168.1.10:8765"]:
		verify(menu.validated_lan_join(true,"http:","127.0.0.1:8770",rejected_join).is_empty(),"A LAN join parameter cannot choose public, credential-bearing, malformed, or routed addresses")
	verify(menu.initial_endpoint(true,"http:","shared.example:8765","","ws://192.168.1.10:8765") == "ws://shared.example:8765","A public HTTP page ignores LAN join parameters")
	verify(menu.initial_endpoint(true,"https:","shared.example","","ws://192.168.1.10:8765") == "wss://shared.example","A public HTTPS page ignores LAN join parameters")
	verify(menu.initial_endpoint(true,"https:","localhost:8770","","ws://192.168.1.10:8765") == "wss://localhost:8770","Even a loopback HTTPS page preserves mixed-content protection")
	verify(menu.initial_endpoint(false,"","","wss://play.example","ws://192.168.1.10:8765") == "wss://play.example","Native clients ignore browser join parameters")
	for valid_address in ["ws://localhost:8765","wss://play.example/game","ws://[::1]:8765","wss://[2001:db8::1]:443/path?region=north"]:
		verify(menu.valid_endpoint(valid_address),"Supported hostname and IPv6 socket addresses validate")
	for invalid_address in ["ws://", "ws://:8765", "ws://host:","ws://host:0","ws://host:65536","ws://host:abc","ws://user@host","ws://bad host", "ws://127.0.0.999", "ws://[::1]junk", "ws://host#fragment"]:
		verify(not menu.valid_endpoint(invalid_address),"Malformed server addresses are rejected before connection")
	verify(menu.normalize_endpoint(" https://play.example/index.html ") == "wss://play.example","Shared HTTPS game links become secure sockets without the HTML filename")
	verify(menu.normalize_endpoint("http://192.168.1.10:8765/") == "ws://192.168.1.10:8765/","Shared HTTP LAN links become sockets")
	verify(menu.location_title("ws://192.168.1.10:8765").begins_with("LOCAL NETWORK"),"Private IPv4 addresses identify LAN play")
	verify(menu.location_title("wss://fcloud.example").begins_with("SHARED SERVER"),"Hostnames beginning with IPv6 prefixes are still shared servers")
	verify(menu.location_title("wss://127.example.org").begins_with("SHARED SERVER"),"DNS names beginning with IPv4 prefixes are still shared servers")
	menu.web_client = true
	menu.page_protocol = "https:"
	menu.page_host = "play.example"
	verify("must use wss://" in menu.endpoint_error("ws://play.example"),"HTTPS games explain mixed-content rejection before connecting")
	verify(menu.endpoint_error("wss://play.example").is_empty(),"HTTPS games accept secure server addresses")
	var browser_session := {"token":"test-saved-token","name":"MenuExplorer","endpoint":"wss://play.example"}
	verify(not menu.usable_session(browser_session).is_empty(),"A browser resumes its saved session on the page's server")
	browser_session.endpoint = "wss://play.example:443"
	verify(not menu.usable_session(browser_session).is_empty(),"Explicit default TLS ports still identify the page's server")
	browser_session.endpoint = "ws://127.0.0.1:8765"
	verify(menu.usable_session(browser_session).is_empty(),"A saved local session cannot silently redirect an HTTPS game")
	browser_session.endpoint = "wss://different.example"
	verify(menu.usable_session(browser_session).is_empty(),"A browser cannot silently continue on a different server")
	menu.web_client = false
	verify(not menu.usable_session(browser_session).is_empty(),"A native client can continue on its previously selected server")
	menu.web_client = true
	menu.page_protocol = "http:"
	menu.page_host = "127.0.0.1:8770"
	menu.join_endpoint = "ws://192.168.1.10:8765"
	browser_session.endpoint = menu.join_endpoint
	verify(not menu.usable_session(browser_session).is_empty(),"A loopback client can resume the exact explicitly joined LAN server")
	browser_session.endpoint = "ws://192.168.1.11:8765"
	verify(menu.usable_session(browser_session).is_empty(),"A LAN joining client cannot resume a different host's account")
	menu.join_endpoint = ""
	browser_session.endpoint = "ws://192.168.1.10:8765"
	verify(menu.usable_session(browser_session).is_empty(),"Removing the explicit join restores strict page-origin session scope")
	menu.web_client = false
	menu.show_form("signup")
	await process_frame
	verify("Friends need" in menu.server_hint.text,"The local login form explains sharing requirements")
	ui.address.text = "http://192.168.1.10:8765"
	ui.address.text_changed.emit(ui.address.text)
	verify("same network" in menu.server_hint.text and "Join-WORLDFORGE-LAN.bat" in menu.server_hint.text,"The login form explains the secure local client for LAN play")
	ui.address.text = "https://play.example"
	ui.address.text_changed.emit(ui.address.text)
	verify("same server" in menu.server_hint.text,"A shared game link gives the same-server multiplayer instruction")
	verify(menu.fields.has("confirm"),"Creating an account requires password confirmation")
	await process_frame
	verify(menu.status_panel.size.y >= 64 and menu.status.size.y >= 20,"Login feedback has a dedicated panel with enough room for readable text")
	ui.username.text = "bad name"
	ui.password.text = "menu-test-password"
	menu.confirm_password.text = "menu-test-password"
	menu.submit()
	verify(submits.is_empty(),"Invalid explorer names cannot send authentication")
	for invalid_name in ["123Explorer","_Explorer"]:
		ui.username.text = invalid_name
		menu.submit()
		verify(submits.is_empty(),"Explorer names beginning with a digit or underscore cannot authenticate")
	ui.username.text = "MenuExplorer"
	menu.confirm_password.text = "different-password"
	menu.submit()
	verify(submits.is_empty(),"Mismatched passwords cannot send registration")
	menu.confirm_password.text = "menu-test-password"
	ui.address.text = "ws://"
	menu.submit()
	verify(submits.is_empty(),"An empty server host cannot send authentication")
	menu.web_client = true
	menu.page_protocol = "https:"
	menu.page_host = "play.example"
	ui.address.text = "ws://play.example"
	menu.submit()
	verify(submits.is_empty(),"HTTPS login never sends an insecure authentication attempt")
	verify("must use wss://" in ui.form_status.text,"The actual form shows useful mixed-content guidance")
	menu.web_client = false
	ui.address.text = "http://127.0.0.1:8765/index.html"
	menu.submit()
	verify(submits.size() == 1,"Valid registration sends exactly one authentication attempt")
	verify(submits[0].endpoint == "ws://127.0.0.1:8765","Submitting a pasted game link sends the converted socket address")
	verify(submits[0].credentials.get("register") == true,"Registration is explicitly distinct from sign in")
	verify(submits[0].credentials.get("protocol") == 2,"Registration advertises the supported multiplayer protocol")
	verify(menu.loading,"Authentication shows the loading screen")
	verify(ui.connect_button.disabled,"The pending connect button is disabled")
	verify(ui.password.text.is_empty() and menu.confirm_password.text.is_empty(),"Submitted passwords are removed from input controls")
	menu.submit()
	verify(submits.size() == 1,"A pending authentication cannot be sent twice")
	menu.auth_error("Invalid sign-in details")
	await process_frame
	verify(not menu.loading and not ui.connect_button.disabled,"An authentication error permits a retry")
	verify(ui.form_status.text == "Invalid sign-in details","The retry form shows the server failure")
	menu.auth_error("Connection timed out. Check the address or try again.")
	verify("Start Play-WORLDFORGE.bat" in ui.form_status.text,"A failed local connection explains how to start the server")
	menu.endpoint = "ws://192.168.1.10:8765"
	verify("same network" in menu.connection_feedback("Disconnected. Sign in to reconnect. Your progress is saved."),"A failed LAN connection explains shared hosting and network requirements")
	menu.endpoint = "ws://127.0.0.1:8765"
	menu.show_form("recovery")
	await process_frame
	ui.username.text = "MenuExplorer"
	ui.password.text = "new-menu-password"
	menu.confirm_password.text = "new-menu-password"
	menu.fields.recovery.text = "test-recovery-code"
	menu.submit()
	verify(submits.size() == 2,"A validated password reset sends one request")
	verify(submits[1].credentials.get("type") == "recovery_reset","Recovery uses the reset protocol rather than registering an account")
	verify(not submits[1].credentials.has("password"),"A reset sends the new password under its dedicated field")
	verify(menu.fields.recovery.text.is_empty(),"The recovery code is removed after submission")
	verify(not ui.remember_session,"An unauthenticated reset does not create a saved session")
	menu.auth_error("Try again")
	ui.show_game(true)
	verify(not menu.visible,"A ready world dismisses the starting menu")
	ui.set_loading("Preparing the destination world")
	verify(menu.visible and menu.loading,"World travel uses the same connection loading overlay")
	ui.finish_loading()
	verify(not menu.visible and not menu.loading,"A ready destination dismisses loading")
	ui.remember_session = true
	ui.state.player_name = "MenuExplorer"
	ui.save_session("test-saved-token","ws://127.0.0.1:8765")
	var saved: Dictionary = ui.load_session()
	verify(saved.get("token") == "test-saved-token","Remembered sessions save the server token")
	verify(not saved.has("password") and not saved.has("recovery_code"),"Remembered sessions exclude passwords and recovery codes")
	ui.show_game(false)
	menu.web_client = true
	menu.page_protocol = "https:"
	menu.page_host = "play.example"
	menu.endpoint = "wss://play.example"
	menu.show_title()
	verify(not menu.buttons.has("continue"),"The hosted title does not offer Continue to a remembered local server")
	var submissions_before: int = submits.size()
	menu.resume_saved()
	verify(submits.size() == submissions_before and menu.mode == "signin","An unusable browser saved session returns to sign in without sending its token")
	verify(ui.address.text == "wss://play.example","A rejected remembered server leaves the hosted page's server selected")
	menu.web_client = false
	menu.resume_saved()
	verify(submits.back().credentials.keys() == ["token","protocol"],"Continuing sends a saved token and protocol without account passwords")
	ui.clear_session()
	verify(ui.load_session().is_empty(),"Forgetting this device removes its saved session")
	ui.show_game(true)
	verify(not "CONNECTED" in ui.connection.text or "DISCONNECTED" in ui.connection.text,"The HUD never claims a connection before a welcome arrives")
	ui.set_connection_status("Connected")
	verify("ONLINE" in ui.connection.text and "MEASURING" in ui.connection.text,"A real welcome marks the HUD online while waiting for a latency sample")
	ui.state.latency = 47
	ui.refresh_connection_status()
	verify("47 MS RTT" in ui.connection.text,"The HUD shows the actual server round-trip latency")
	verify("127.0.0.1:8765" in ui.connection.tooltip_text,"The connection tooltip identifies the server")
	ui.set_connection_status("Reconnecting… attempt 1 of 4")
	verify(not "ONLINE" in ui.connection.text and "Reconnecting" in ui.connection.text,"Reconnection never leaves a stale online indicator")
	ui.set_connection_status("Connected")
	verify(ui.state.latency == -1,"A new connection clears the previous connection's latency sample")
	ui.state.latency = 0
	ui.refresh_connection_status()
	verify("0 MS RTT" in ui.connection.text,"A genuine zero-millisecond latency sample is shown")
	ui.open_settings()
	verify(ui.modal_body.get_node_or_null("SettingsScroll/SettingsContents/CurrentServerLocation") != null,"Settings identifies the selected game server")
	verify(ui.modal_body.get_node_or_null("SettingsScroll/SettingsContents/CurrentServerHelp") != null,"Settings retains multiplayer hosting guidance during play")
	await process_frame
	verify(ui.modal_body.get_node("SettingsScroll").get_global_rect().end.y <= ui.modal.get_global_rect().end.y,"Expanded settings stay inside their scrollable panel")
	root.size = Vector2i(1280,720)
	await process_frame
	await process_frame
	verify(ui.modal_body.get_node("SettingsScroll").get_global_rect().end.y <= ui.modal.get_global_rect().end.y,"Settings remain contained at 720p")
	ui.close_modal()
	ui.open_account()
	await process_frame
	verify(ui.modal_kind == "account","Account security controls can be opened from the game")
	ui.close_modal()
	ui.show_recovery_code("test-recovery-code")
	await process_frame
	verify(ui.modal_kind == "recovery_code","Recovery codes are shown in an explicit save or copy screen")
	ui.close_modal()
	ui.remember_session = true
	ui.state.player_name = "MenuExplorer"
	ui.save_session("test-lan-token","ws://192.168.1.10:8765")
	menu.web_client = true
	menu.page_protocol = "http:"
	menu.page_host = "127.0.0.1:8770"
	menu.join_endpoint = "ws://192.168.1.10:8765"
	menu.endpoint = menu.join_endpoint
	ui.show_game(false)
	verify(menu.buttons.has("continue") and "LOCAL NETWORK" in menu.server_location.text,"The real LAN title identifies and offers the explicitly joined server's saved account")
	menu.resume_saved()
	verify(submits.back().endpoint == "ws://192.168.1.10:8765" and submits.back().credentials.get("token") == "test-lan-token","The real Continue button sends its token to the joined shared authority instead of the static local client")
	ui.clear_session()
	menu.join_endpoint = ""
	menu.web_client = false
	ui.queue_free()
	await process_frame
	print(JSON.stringify({"menu_checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
