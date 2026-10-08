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

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 20
	endpoint = "ws://127.0.0.1:8765"
	if OS.has_feature("web"):
		var host = JavaScriptBridge.eval("window.location.host")
		var protocol = JavaScriptBridge.eval("window.location.protocol")
		endpoint = ("wss://" if protocol == "https:" else "ws://") + str(host)
	var prefs := ConfigFile.new()
	if prefs.load("user://preferences.cfg") == OK:
		endpoint = str(prefs.get_value("connection","endpoint",endpoint))
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
	var saved: Dictionary = ui.load_session()
	if not saved.is_empty():
		var continuing := add_button("continue","Continue as " + str(saved.get("name","explorer")),resume_saved,true)
		ui.continue_button = continuing
	add_button("play","Play WORLDFORGE  →",func(): show_form("signin" if not saved.is_empty() else "signup"),saved.is_empty())
	add_button("guide","How to play",func(): ui.open_help())
	add_button("settings","Settings",func(): ui.open_settings())
	text_block("Persistent worlds · Original pixel art · Play together",11,ui.MUTED)
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
	ui.address = ui.input("ws://127.0.0.1:8765")
	ui.address.text = endpoint
	ui.address.max_length = 256
	content.add_child(ui.address)
	fields.address = ui.address
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
	endpoint = ui.address.text.strip_edges()
	if not valid_endpoint(endpoint):
		set_status("Enter a ws:// or wss:// server address, including its host.")
		ui.address.grab_focus()
		return
	var credentials := {"name":explorer,"password":ui.password.text,"register":mode == "signup"}
	if mode == "recovery":
		if str(fields.recovery.text).strip_edges().is_empty():
			set_status("Enter the recovery code you saved for this server.")
			return
		credentials = {"type":"recovery_reset","name":explorer,"recovery_code":str(fields.recovery.text).strip_edges(),"new_password":ui.password.text}
	ui.remember_session = remember.button_pressed and mode != "recovery"
	persist_endpoint()
	get_viewport().gui_release_focus()
	ui.password.clear()
	if confirm_password: confirm_password.clear()
	if fields.has("recovery"): fields.recovery.clear()
	ui.login.emit(endpoint,credentials)
	set_loading("Connecting to your server")

func valid_endpoint(value: String) -> bool:
	if not value.begins_with("ws://") and not value.begins_with("wss://"): return false
	var host := value.substr(6 if value.begins_with("wss://") else 5).split("/")[0]
	return not host.is_empty() and not " " in value and not "\n" in value and not "\r" in value and not "\t" in value and not "@" in host and not host.begins_with(":")

func persist_endpoint() -> void:
	var prefs := ConfigFile.new()
	prefs.load("user://preferences.cfg")
	prefs.set_value("connection","endpoint",endpoint)
	prefs.save("user://preferences.cfg")

func resume_saved() -> void:
	var saved: Dictionary = ui.load_session()
	if saved.is_empty():
		show_form("signin")
		return
	ui.remember_session = true
	last_form = "signin"
	name_hint = str(saved.get("name",""))
	endpoint = str(saved.get("endpoint",endpoint))
	ui.login.emit(endpoint,{"token":saved.token})
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
	set_status(text)

func layout() -> void:
	var viewport := get_viewport().get_visible_rect().size
	size = viewport
	var narrow := viewport.x < 1120
	hero.visible = not loading and not narrow
	hero.position = Vector2(64,maxf(65.0,viewport.y * .12))
	hero.size = Vector2(maxf(450.0,viewport.x*.49),460)
	if card:
		var card_height := (500.0 if buttons.has("continue") else 430.0) if mode == "title" else 660.0
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
