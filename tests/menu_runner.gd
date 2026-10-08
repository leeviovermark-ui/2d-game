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
	menu.show_form("signup")
	await process_frame
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
	ui.address.text = "ws://127.0.0.1:8765"
	menu.submit()
	verify(submits.size() == 1,"Valid registration sends exactly one authentication attempt")
	verify(submits[0].credentials.get("register") == true,"Registration is explicitly distinct from sign in")
	verify(menu.loading,"Authentication shows the loading screen")
	verify(ui.connect_button.disabled,"The pending connect button is disabled")
	verify(ui.password.text.is_empty() and menu.confirm_password.text.is_empty(),"Submitted passwords are removed from input controls")
	menu.submit()
	verify(submits.size() == 1,"A pending authentication cannot be sent twice")
	menu.auth_error("Invalid sign-in details")
	await process_frame
	verify(not menu.loading and not ui.connect_button.disabled,"An authentication error permits a retry")
	verify(ui.form_status.text == "Invalid sign-in details","The retry form shows the server failure")
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
	menu.resume_saved()
	verify(submits.back().credentials.keys() == ["token"],"Continuing uses only the saved session token")
	ui.clear_session()
	verify(ui.load_session().is_empty(),"Forgetting this device removes its saved session")
	ui.show_game(true)
	ui.open_account()
	await process_frame
	verify(ui.modal_kind == "account","Account security controls can be opened from the game")
	ui.close_modal()
	ui.show_recovery_code("test-recovery-code")
	await process_frame
	verify(ui.modal_kind == "recovery_code","Recovery codes are shown in an explicit save or copy screen")
	ui.close_modal()
	ui.queue_free()
	await process_frame
	print(JSON.stringify({"menu_checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
