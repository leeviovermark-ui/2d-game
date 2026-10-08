extends Control
## Landing screen, account forms, and truthful connection phases.
var ui
var card: PanelContainer
var hero: VBoxContainer
var content: VBoxContainer
var mode := "title"
var last_form := "signup"
var loading := false
var phase := "Connecting to server"
var elapsed := 0.0
var spinner := 0.0
var status: Label
var status_panel: PanelContainer
var fields := {}
var buttons := {}
var confirm_password: LineEdit
var remember: CheckButton
var recovery_pending := false
var phase_label: Label
var loading_detail: Label
var loading_card: PanelContainer
var loading_bar: ProgressBar
var retry_button: Button
var loading_spinner: Control
var endpoint := ""
var name_hint := ""
var web_client := false
var page_protocol := ""
var page_host := ""
var join_endpoint := ""
var server_hint: Label
var server_location: Label

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 20
	var prefs := ConfigFile.new()
	web_client = OS.has_feature("web")
	if not web_client: prefs.load("user://preferences.cfg")
	if web_client:
		page_host = str(JavaScriptBridge.eval("window.location.host"))
		page_protocol = str(JavaScriptBridge.eval("window.location.protocol"))
		var requested_join = JavaScriptBridge.eval("(()=>{try{return new URL(window.location.href).searchParams.get('join') || '';}catch(_){return '';}})()",true)
		join_endpoint = validated_lan_join(web_client,page_protocol,page_host,str(requested_join))
	endpoint = initial_endpoint(web_client,page_protocol,page_host,str(prefs.get_value("connection","endpoint","")),join_endpoint)
	build_hero()
	build_loading()
	show_title()

func build_hero() -> void:
	hero = VBoxContainer.new()
	hero.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hero.add_theme_constant_override("separation",18)
	add_child(hero)
	hero.add_child(ui.label("A PLACE FOR YOUR NEXT GREAT ADVENTURE",12,Color("beffdc")))
	var logo: Label = ui.label("WORLDFORGE",64,Color("f7ffec"))
	logo.name = "Wordmark"
	logo.add_theme_color_override("font_shadow_color",Color("12443a"))
	logo.add_theme_constant_override("shadow_offset_y",4)
	hero.add_child(logo)
	hero.add_child(ui.label("Worlds worth\ngetting lost in.",36,Color("f3ffe4")))
	var description: Label = ui.label("Build a home. Discover a horizon.\nMake something extraordinary together.",16,Color("d7efe4"))
	description.name = "Description"
	hero.add_child(description)
	var features: Label = ui.label("EXPLORE   /   CREATE   /   CONNECT",11,Color("ffd99b"))
	features.name = "Features"
	hero.add_child(features)

func new_card() -> void:
	if card:
		remove_child(card)
		card.queue_free()
	card = PanelContainer.new()
	card.add_theme_stylebox_override("panel",ui.box(Color("173e49"),Color("69aea0"),26))
	add_child(card)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	card.add_child(scroll)
	content = ui.column(scroll,12)
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.custom_minimum_size.x = 370
	fields.clear()
	buttons.clear()
	status = null
	server_hint = null
	server_location = null
	confirm_password = null
	card.modulate.a = 0.0
	card.create_tween().tween_property(card,"modulate:a",1.0,.22).set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_OUT)

func add_button(key: String, text: String, action: Callable, primary := false) -> Button:
	var node: Button = ui.button(text,action,primary)
	node.name = key.capitalize()
	node.focus_mode = Control.FOCUS_ALL
	node.custom_minimum_size.y = 45
	content.add_child(node)
	buttons[key] = node
	return node

func text_block(text: String, font_size := 13, color := Color("b6d3cb")) -> Label:
	var node: Label = ui.label(text,font_size,color)
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(node)
	return node

func show_title() -> void:
	loading = false
	mode = "title"
	visible = true
	loading_card.hide()
	hero.show()
	new_card()
	text_block("YOUR WORLD STARTS HERE",11,ui.ACCENT)
	text_block("Welcome home, explorer.",26,ui.INK)
	text_block("Every great adventure starts with a little curiosity. Where will yours take you?")
	var gap := Control.new()
	gap.custom_minimum_size.y = 8
	content.add_child(gap)
	var remembered: Dictionary = ui.load_session()
	var saved: Dictionary = usable_session(remembered)
	if not saved.is_empty():
		var continuing := add_button("continue","Continue as " + str(saved.get("name","explorer")),resume_saved,true)
		ui.continue_button = continuing
	add_button("play","Play WORLDFORGE  →",func(): show_form("signin" if not saved.is_empty() else "signup"),saved.is_empty())
	add_button("guide","How to play",func(): ui.open_help())
	add_button("settings","Settings",func(): ui.open_settings())
	var displayed_endpoint: String = str(saved.get("endpoint",endpoint))
	server_location = text_block(location_title(displayed_endpoint),11,ui.ACCENT)
	server_location.name = "ServerLocation"
	server_hint = text_block(connection_help(displayed_endpoint),12,ui.MUTED)
	server_hint.name = "ServerConnectionHelp"
	if saved.is_empty() and not remembered.is_empty():
		text_block("Your saved sign-in belongs to another server. Sign in here to play on this server.",11,ui.MUTED)
	layout()
	focus_start.call_deferred()

func show_form(next_mode: String) -> void:
	if is_instance_valid(ui.username): name_hint = ui.username.text
	loading = false
	mode = next_mode
	last_form = next_mode
	visible = true
	loading_card.hide()
	hero.show()
	new_card()
	content.add_theme_constant_override("separation",7)
	text_block("YOUR EXPLORER ACCOUNT",11,ui.ACCENT)
	text_block("Start something wonderful." if mode == "signup" else ("Find your way back." if mode == "recovery" else "Good to see you again."),24,ui.INK)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation",8)
	content.add_child(tabs)
	for pair in [["signin","Sign in"],["signup","Create account"]]:
		var key: String = pair[0]
		var tab: Button = ui.button(pair[1],func(): show_form(key),mode == key)
		tab.focus_mode = Control.FOCUS_ALL
		tab.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		tabs.add_child(tab)
		buttons[key] = tab
	text_block("EXPLORER NAME",10,ui.MUTED)
	ui.username = ui.input("Start with a letter · 3–20 characters")
	ui.username.max_length = 20
	content.add_child(ui.username)
	fields.name = ui.username
	var saved: Dictionary = ui.load_session()
	ui.username.text = name_hint if not name_hint.is_empty() else str(saved.get("name",""))
	if mode == "recovery":
		text_block("RECOVERY CODE",10,ui.MUTED)
		var code: LineEdit = ui.input("The code you saved when creating your account",true)
		code.max_length = 96
		content.add_child(code)
		fields.recovery = code
		text_block("This server has no email reset. Your saved recovery code proves ownership.",11)
	text_block("NEW PASSWORD / CONFIRM" if mode == "recovery" else ("PASSWORD / CONFIRM" if mode == "signup" else "PASSWORD"),10,ui.MUTED)
	var password_row := HBoxContainer.new()
	password_row.add_theme_constant_override("separation",8)
	content.add_child(password_row)
	ui.password = ui.input("At least 8 characters",true)
	ui.password.max_length = 128
	ui.password.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	password_row.add_child(ui.password)
	fields.password = ui.password
	if mode == "recovery": fields.new_password = ui.password
	if mode in ["signup","recovery"]:
		confirm_password = ui.input("Confirm password",true)
		confirm_password.max_length = 128
		confirm_password.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		password_row.add_child(confirm_password)
		fields.confirm = confirm_password
	var preferences := HBoxContainer.new()
	preferences.add_theme_constant_override("separation",10)
	content.add_child(preferences)
	var show_password := CheckButton.new()
	show_password.text = "Show password"
	show_password.focus_mode = Control.FOCUS_ALL
	show_password.toggled.connect(func(enabled):
		ui.password.secret = not enabled
		if confirm_password: confirm_password.secret = not enabled)
	preferences.add_child(show_password)
	remember = CheckButton.new()
	remember.text = "Remember this device"
	remember.button_pressed = true
	remember.focus_mode = Control.FOCUS_ALL
	preferences.add_child(remember)
	text_block("SERVER ADDRESS",10,ui.MUTED)
	ui.address = ui.input("Paste a shared game link or ws://host:port")
	ui.address.text = endpoint
	ui.address.max_length = 256
	content.add_child(ui.address)
	fields.address = ui.address
	server_hint = text_block(connection_help(endpoint),11,ui.MUTED)
	server_hint.name = "ServerConnectionHelp"
	ui.address.text_changed.connect(func(value):
		if is_instance_valid(server_hint): server_hint.text = connection_help(normalize_endpoint(value)))
	ui.connect_button = add_button("submit","Reset password" if mode == "recovery" else ("Create account & play  →" if mode == "signup" else "Sign in & play  →"),submit,true)
	ui.password.text_submitted.connect(func(_value):
		if confirm_password: confirm_password.grab_focus()
		else: submit())
	if confirm_password: confirm_password.text_submitted.connect(func(_value): submit())
	status_panel = PanelContainer.new()
	status_panel.custom_minimum_size.y = 64
	status_panel.add_theme_stylebox_override("panel",ui.box(Color("143640"),Color("437c7b"),12))
	content.add_child(status_panel)
	status = ui.label("Your progress belongs to this server. Passwords stay off this device.",14,ui.MUTED)
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.clip_text = false
	status_panel.add_child(status)
	ui.form_status = status
	if mode != "recovery": add_button("recover","I have a recovery code",func(): show_form("recovery")).custom_minimum_size.y = 36
	add_button("back","←  Back to start",show_title).custom_minimum_size.y = 36
	layout()
	focus_name.call_deferred()

func valid_name(value: String) -> bool:
	if value.length() < 3 or value.length() > 20: return false
	if not (value[0] >= "a" and value[0] <= "z") and not (value[0] >= "A" and value[0] <= "Z"): return false
	for character in value:
		if not (character >= "a" and character <= "z") and not (character >= "A" and character <= "Z") and not (character >= "0" and character <= "9") and character != "_": return false
	return true

func submit() -> void:
	if loading: return
	var explorer: String = ui.username.text.strip_edges()
	if not valid_name(explorer):
		set_status("Start with a letter. Use 3–20 letters, numbers, or underscores.")
		ui.username.grab_focus()
		return
	if ui.password.text.length() < 8:
		set_status("Choose a password with at least 8 characters.")
		ui.password.grab_focus()
		return
	if confirm_password and confirm_password.text != ui.password.text:
		set_status("Those passwords do not match. Try the confirmation again.")
		confirm_password.grab_focus()
		return
	endpoint = normalize_endpoint(ui.address.text)
	var endpoint_problem := endpoint_error(endpoint)
	if not endpoint_problem.is_empty():
		set_status(endpoint_problem)
		ui.address.grab_focus()
		return
	ui.address.text = endpoint
	var credentials := {"name":explorer,"password":ui.password.text,"register":mode == "signup"}
	if mode == "recovery":
		if str(fields.recovery.text).strip_edges().is_empty():
			set_status("Enter the recovery code you saved for this server.")
			return
		credentials = {"type":"recovery_reset","name":explorer,"recovery_code":str(fields.recovery.text).strip_edges(),"new_password":ui.password.text}
	credentials.protocol = 2
	ui.remember_session = remember.button_pressed and mode != "recovery"
	persist_endpoint()
	get_viewport().gui_release_focus()
	ui.password.clear()
	if confirm_password: confirm_password.clear()
	if fields.has("recovery"): fields.recovery.clear()
	ui.login.emit(endpoint,credentials)
	set_loading("Connecting to your server")

func initial_endpoint(is_web: bool, protocol: String, host: String, stored: String = "", requested_join: String = "") -> String:
	# Browser games connect to their own page. An old native/IndexedDB setting
	# must never silently turn a hosted game into a connection to this device.
	if is_web:
		var target := validated_lan_join(is_web,protocol,host,requested_join)
		if not target.is_empty(): return target
		return ("wss://" if protocol == "https:" else "ws://") + host
	var remembered := normalize_endpoint(stored)
	return remembered if valid_endpoint(remembered) else "ws://127.0.0.1:8765"

func validated_lan_join(is_web: bool, protocol: String, host: String, requested_join: String) -> String:
	# A static local browser client may explicitly join the friend's LAN
	# authority. Public pages cannot redirect players through this parameter.
	if not is_web or protocol != "http:" or requested_join.is_empty(): return ""
	var page := endpoint_parts("ws://" + host)
	if page.is_empty() or page.host not in ["127.0.0.1","localhost","::1"]: return ""
	if not requested_join.begins_with("ws://"): return ""
	var target := endpoint_parts(requested_join)
	if target.is_empty() or str(target.port).is_empty() or requested_join != "ws://" + str(target.authority): return ""
	var address: String = target.host
	if not address.is_valid_ip_address() or ":" in address: return ""
	var private_address := address.begins_with("10.") or address.begins_with("192.168.")
	if address.begins_with("172."):
		var second := address.get_slice(".",1).to_int()
		private_address = second >= 16 and second <= 31
	return requested_join if private_address else ""

func normalize_endpoint(value: String) -> String:
	var result := value.strip_edges()
	if result.begins_with("https://"): result = "wss://" + result.substr(8)
	elif result.begins_with("http://"): result = "ws://" + result.substr(7)
	# Game links often end in index.html; the socket shares the site's origin.
	if result.ends_with("/index.html"): result = result.trim_suffix("/index.html")
	return result

func endpoint_parts(value: String) -> Dictionary:
	if not value.begins_with("ws://") and not value.begins_with("wss://"): return {}
	for character in value:
		if character.unicode_at(0) <= 32 or character.unicode_at(0) == 127: return {}
	if "#" in value or "\\" in value: return {}
	var authority := value.substr(6 if value.begins_with("wss://") else 5).split("/")[0].split("?")[0]
	if authority.is_empty() or "@" in authority: return {}
	var host := authority
	var port := ""
	if authority.begins_with("["):
		var end := authority.find("]")
		if end < 2: return {}
		host = authority.substr(1,end-1)
		if not host.is_valid_ip_address() or not ":" in host: return {}
		var suffix := authority.substr(end+1)
		if not suffix.is_empty():
			if not suffix.begins_with(":"): return {}
			port = suffix.substr(1)
			if port.is_empty(): return {}
	else:
		if authority.count(":") > 1: return {}
		if ":" in authority:
			host = authority.get_slice(":",0)
			port = authority.get_slice(":",1)
			if port.is_empty(): return {}
		if host.is_empty() or host.begins_with(".") or host.ends_with(".") or ".." in host: return {}
		for part in host.split("."):
			if part.is_empty() or part.begins_with("-") or part.ends_with("-"): return {}
			for character in part.to_lower():
				if not (character >= "a" and character <= "z") and not (character >= "0" and character <= "9") and character != "-": return {}
		# A four-part numeric address should be an actual IPv4 address.
		if host.split(".").size() == 4 and host.replace(".","").is_valid_int() and not host.is_valid_ip_address(): return {}
	if not port.is_empty():
		for character in port:
			if character < "0" or character > "9": return {}
		if port.to_int() < 1 or port.to_int() > 65535: return {}
	return {"authority":authority.to_lower(),"host":host.to_lower(),"port":port,"secure":value.begins_with("wss://")}

func endpoint_origin(value: String) -> String:
	var parts := endpoint_parts(value)
	if parts.is_empty(): return ""
	var default_port := "443" if parts.secure else "80"
	return ("wss://" if parts.secure else "ws://") + str(parts.host) + ":" + (str(parts.port) if not str(parts.port).is_empty() else default_port)

func valid_endpoint(value: String) -> bool:
	return not endpoint_parts(value).is_empty()

func endpoint_error(value: String) -> String:
	if not valid_endpoint(value): return "Enter a valid game link or ws://host:port server address. Check the host and port (1–65535)."
	if web_client and page_protocol == "https:" and not value.begins_with("wss://"):
		return "This page uses HTTPS, so the server must use wss://. Open your host's HTTPS game link or enter its secure server address."
	return ""

func usable_session(saved: Dictionary) -> Dictionary:
	if saved.is_empty(): return {}
	var saved_endpoint := str(saved.get("endpoint",""))
	if not endpoint_error(saved_endpoint).is_empty(): return {}
	if web_client:
		var current := initial_endpoint(true,page_protocol,page_host,"",join_endpoint)
		if endpoint_origin(saved_endpoint) != endpoint_origin(current): return {}
	return saved

func local_address(host: String) -> bool:
	return host in ["localhost","::1","::","0.0.0.0"] or host.ends_with(".localhost") or (host.is_valid_ip_address() and (host.begins_with("127.") or host.begins_with("::ffff:127.")))

func lan_address(host: String) -> bool:
	if not host.is_valid_ip_address(): return false
	if host.begins_with("10.") or host.begins_with("192.168.") or host.begins_with("169.254."): return true
	if host.begins_with("172."):
		var second := host.get_slice(".",1).to_int()
		return second >= 16 and second <= 31
	return ":" in host and (host.begins_with("fc") or host.begins_with("fd") or host.begins_with("fe80:"))

func location_title(value: String) -> String:
	var parts := endpoint_parts(value)
	if parts.is_empty(): return "CHOOSE A GAME SERVER"
	var scope := "THIS COMPUTER" if local_address(parts.host) else ("LOCAL NETWORK" if lan_address(parts.host) else "SHARED SERVER")
	return scope + "  ·  " + str(parts.authority)

func connection_help(value: String) -> String:
	var problem := endpoint_error(value)
	if not problem.is_empty(): return problem
	var host: String = endpoint_parts(value).host
	if local_address(host):
		return "This address works on this computer only. Friends need the host's shared game link and separate accounts. One person hosts for everyone."
	if lan_address(host):
		return "One person hosts. Friends on the same network run Join-WORLDFORGE-LAN.bat and paste the host's address. Use separate accounts; the client opens on localhost."
	return "Friends use this same server with separate accounts. Open the exact shared game link; your account, friends, and worlds are saved here."

func persist_endpoint() -> void:
	if web_client: return
	var prefs := ConfigFile.new()
	prefs.load("user://preferences.cfg")
	prefs.set_value("connection","endpoint",endpoint)
	prefs.save("user://preferences.cfg")

func resume_saved() -> void:
	var saved: Dictionary = usable_session(ui.load_session())
	if saved.is_empty():
		show_form("signin")
		return
	ui.remember_session = true
	last_form = "signin"
	name_hint = str(saved.get("name",""))
	endpoint = str(saved.get("endpoint",endpoint))
	ui.login.emit(endpoint,{"token":saved.token,"protocol":2})
	set_loading("Restoring your saved session")

func build_loading() -> void:
	loading_card = PanelContainer.new()
	loading_card.add_theme_stylebox_override("panel",ui.box(Color("173e49"),Color("68bca5"),32))
	add_child(loading_card)
	var body: VBoxContainer = ui.column(loading_card,16)
	var kicker: Label = ui.label("WORLDFORGE  /  PREPARING YOUR JOURNEY",11,ui.ACCENT)
	var header_row := HBoxContainer.new()
	kicker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(kicker)
	loading_spinner = LoadingSpinner.new()
	loading_spinner.custom_minimum_size = Vector2(32,32)
	loading_spinner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header_row.add_child(loading_spinner)
	body.add_child(header_row)
	phase_label = ui.label("Connecting to your server",25,ui.INK)
	phase_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(phase_label)
	loading_bar = ProgressBar.new()
	loading_bar.custom_minimum_size.y = 6
	loading_bar.show_percentage = false
	loading_bar.add_theme_stylebox_override("background",ui.box(Color("214f58"),Color("214f58"),0))
	loading_bar.add_theme_stylebox_override("fill",ui.box(Color("66e7b4"),Color("66e7b4"),0))
	body.add_child(loading_bar)
	loading_detail = ui.label("Connecting you to a persistent world. Your progress loads with your account.",13,ui.MUTED)
	loading_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(loading_detail)
	retry_button = ui.button("Cancel & return",func():
		ui.signed_out.emit()
		show_form(last_form))
	body.add_child(retry_button)
	loading_card.hide()

func set_loading(next_phase: String, progress := -1.0) -> void:
	loading = true
	visible = true
	phase = next_phase
	if is_instance_valid(ui.connect_button): ui.connect_button.disabled = true
	phase_label.text = phase
	elapsed = 0.0
	if card: card.hide()
	hero.hide()
	loading_card.show()
	loading_bar.visible = progress >= 0.0
	if progress >= 0.0: loading_bar.value = clampf(progress,0.0,1.0) * 100.0
	layout()

func finish_loading() -> void:
	loading = false
	loading_card.hide()
	if ui.game_enabled: hide()

func set_status(text: String) -> void:
	if loading:
		phase_label.text = text
		phase = text
	elif status:
		status.text = text
		status.add_theme_color_override("font_color",Color("ffe0b2"))
		status_panel.add_theme_stylebox_override("panel",ui.box(Color("413b39"),Color("d9a67f"),12))

func auth_error(text: String) -> void:
	var target := last_form
	show_form(target)
	set_status(connection_feedback(text))

func connection_feedback(text: String) -> String:
	var transport_failure := text.begins_with("Connection timed") or text == "Could not open that server address." or text == "Disconnected. Sign in to reconnect. Your progress is saved."
	if not transport_failure: return text
	var parts := endpoint_parts(endpoint)
	if parts.is_empty(): return text + " Check the server address above."
	if local_address(parts.host):
		return text + " Start Play-WORLDFORGE.bat on this computer, or use your host's shared game link."
	if lan_address(parts.host):
		return text + " Keep the host's hosting window open. Both computers must be on the same network and use the exact shared link."
	return text + " Check the shared game link and ask the host to keep the server online."

func layout() -> void:
	var viewport := get_viewport().get_visible_rect().size
	size = viewport
	var narrow := viewport.x < 1120
	hero.visible = not loading and not narrow
	hero.position = Vector2(64,maxf(65.0,viewport.y * .12))
	hero.size = Vector2(maxf(450.0,viewport.x*.49),460)
	if card:
		var card_height := (560.0 if buttons.has("continue") else 490.0) if mode == "title" else 700.0
		card.position = Vector2((viewport.x-470)/2 if narrow else viewport.x-526, maxf(36.0,(viewport.y-card_height)/2))
		card.size = Vector2(470,minf(card_height,viewport.y-72))
	loading_card.size = Vector2(minf(540.0,viewport.x-56),300)
	loading_card.position = (viewport-loading_card.size)/2
	publish_rects.call_deferred()
	queue_redraw()

func publish_rects() -> void:
	if not OS.has_feature("web") or not is_inside_tree(): return
	await get_tree().process_frame
	if not is_inside_tree(): return
	var data := {"mode":"loading" if loading else ("game" if ui.game_enabled else mode),"buttons":{},"fields":{},"modal":ui.debug_modal_rects()}
	for key in buttons:
		if is_instance_valid(buttons[key]): data.buttons[key] = rect_data(buttons[key])
	for key in fields:
		if is_instance_valid(fields[key]): data.fields[key] = rect_data(fields[key])
	JavaScriptBridge.eval("window.worldforge_ui = " + JSON.stringify(data) + ";")

func rect_data(control: Control) -> Dictionary:
	var rect := control.get_global_rect()
	return {"x":rect.position.x,"y":rect.position.y,"w":rect.size.x,"h":rect.size.y}

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE and (loading or not ui.game_enabled):
		if loading:
			ui.signed_out.emit()
			show_form(last_form)
		elif mode != "title": show_title()
		get_viewport().set_input_as_handled()

func _process(delta: float) -> void:
	if not visible: return
	spinner += delta
	if loading_spinner:
		loading_spinner.clock = spinner
		loading_spinner.queue_redraw()
	if loading:
		elapsed += delta
		loading_detail.text = "Still waiting for the server… You can cancel and try again." if elapsed > 6 else "A world of possibilities is just around the corner."
	queue_redraw()

func _draw() -> void:
	if ui == null: return
	if loading:
		draw_rect(Rect2(Vector2.ZERO,size),Color(.025,.08,.1,.88))
		return
	var top := Color("19647a")
	var bottom := Color("85cebc")
	for i in range(36):
		draw_rect(Rect2(0,size.y*i/36,size.x,size.y/36+1),top.lerp(bottom,i/35.0))
	var sun := Vector2(size.x*.43,size.y*.22)
	for i in range(5,-1,-1): draw_circle(sun,42+i*15,Color(1,.94,.67,.035 if i>0 else .95))
	for i in range(7):
		var cloud := Vector2(fposmod(i*287+spinner*6,size.x+260)-130,size.y*.10+i%3*54)
		for j in range(4): draw_circle(cloud+Vector2(j*30,sin(j)*5),21+j%2*7,Color(.8,1,.95,.16))
	var horizon := size.y*.7
	draw_colored_polygon(PackedVector2Array([Vector2(0,horizon),Vector2(size.x*.18,horizon-120),Vector2(size.x*.3,horizon-36),Vector2(size.x*.46,horizon-150),Vector2(size.x*.65,horizon-50),Vector2(size.x*.82,horizon-90),Vector2(size.x,horizon),Vector2(size.x,size.y),Vector2(0,size.y)]),Color("418f94"))
	draw_colored_polygon(PackedVector2Array([Vector2(0,horizon+85),Vector2(size.x*.1,horizon-25),Vector2(size.x*.27,horizon+10),Vector2(size.x*.43,horizon-30),Vector2(size.x*.61,horizon+88),Vector2(size.x,horizon+45),Vector2(size.x,size.y),Vector2(0,size.y)]),Color("2d7979"))
	var base := Vector2(70,size.y*.78)
	var island_width := minf(size.x*.5,680)
	var earth := PackedVector2Array([base,base+Vector2(island_width,0),base+Vector2(island_width-42,80),base+Vector2(island_width*.68,147),base+Vector2(island_width*.36,114),base+Vector2(24,66)])
	draw_colored_polygon(earth,Color("80564b"))
	draw_colored_polygon(PackedVector2Array([base+Vector2(25,45),base+Vector2(island_width-24,45),base+Vector2(island_width*.68,147),base+Vector2(island_width*.36,114)]),Color("4a5961"))
	draw_rect(Rect2(base+Vector2(-5,-16),Vector2(island_width+10,19)),Color("5ae6a2"))
	draw_rect(Rect2(base+Vector2(-5,-16),Vector2(island_width+10,5)),Color("bdffbf"))
	for i in range(35):
		var p := base+Vector2(i*island_width/35,-16)
		draw_line(p,p+Vector2(sin(spinner+i)*3,-5-i%4),Color("91f5ac"),2)
	for i in range(3): draw_tree(base+Vector2(island_width*(.18+i*.25),-18),.82+i*.12)
	var house := base+Vector2(island_width*.53,-16)
	draw_rect(Rect2(house+Vector2(-42,-80),Vector2(84,80)),Color("ce9e76"))
	for i in range(4): draw_line(house+Vector2(-42,-i*20),house+Vector2(42,-i*20),Color("a8795c"),2)
	draw_colored_polygon(PackedVector2Array([house+Vector2(-54,-76),house+Vector2(0,-119),house+Vector2(54,-76)]),Color("ffad82"))
	draw_line(house+Vector2(-54,-76),house+Vector2(0,-119),Color("ffe0a3"),4)
	draw_rect(Rect2(house+Vector2(-27,-56),Vector2(23,28)),Color("6ee2d4"))
	draw_rect(Rect2(house+Vector2(12,-44),Vector2(22,44)),Color("5d655d"))
	var explorer := base+Vector2(island_width*.75,-16+sin(spinner*2.2)*.6)
	draw_rect(Rect2(explorer+Vector2(-6,-18),Vector2(5,18)),Color("244c61"))
	draw_rect(Rect2(explorer+Vector2(2,-18),Vector2(5,18)),Color("244c61"))
	draw_rect(Rect2(explorer+Vector2(-8,-40),Vector2(17,25)),Color("ffbd80"))
	draw_rect(Rect2(explorer+Vector2(-5,-56),Vector2(13,16)),Color("ffe0b3"))
	draw_rect(Rect2(explorer+Vector2(-7,-58),Vector2(17,6)),Color("624d45"))
	draw_circle(explorer+Vector2(5,-49),1.6,Color("21424c"))
	for i in range(16):
		var p := Vector2(fposmod(i*89+sin(spinner*.6+i)*22,size.x*.54),size.y*.60+sin(spinner*.7+i*1.4)*66)
		draw_circle(p,1.8,Color(1,1,.7,.35+.25*sin(spinner+i)))
	draw_rect(Rect2(0,size.y-40,size.x,40),Color(.045,.18,.19,.55))
	var font: Font = ui.root.theme.default_font
	draw_string(font,Vector2(24,size.y-15),"STAGE 2  /  THE HORIZON UPDATE",HORIZONTAL_ALIGNMENT_LEFT,-1,10,Color("c2eee1"))

func draw_tree(base: Vector2, scale: float) -> void:
	draw_rect(Rect2(base+Vector2(-7,-99)*scale,Vector2(14,99)*scale),Color("725249"))
	for i in range(3):
		var top := base+Vector2(0,-170+i*31)*scale
		draw_colored_polygon(PackedVector2Array([top,top+Vector2(-47-i*5,60)*scale,top+Vector2(47+i*5,60)*scale]),Color("48c894") if i%2 else Color("62dfa1"))
		draw_line(top,top+Vector2(-47-i*5,60)*scale,Color("a1efb4"),2)


class LoadingSpinner extends Control:
	var clock := 0.0
	func _draw() -> void:
		for i in range(12):
			var angle := clock*2.7 + i*TAU/12
			draw_circle(size/2+Vector2(cos(angle),sin(angle))*11,2.0,Color(.5,1,.78,.18+.82*i/12.0))


func focus_name() -> void:
	if visible and not loading and mode != "title" and is_instance_valid(ui.username) and ui.username.is_inside_tree():
		ui.username.grab_focus()


func focus_start() -> void:
	if visible and not loading and mode == "title":
		var key := "continue" if buttons.has("continue") else "play"
		if is_instance_valid(buttons.get(key)): buttons[key].grab_focus()
