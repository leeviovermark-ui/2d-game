extends CanvasLayer
class_name ForgeUI
## Compact game UI. Every action maps to a server intent or a local setting.
signal intent(kind: String, data: Dictionary)
signal login(endpoint: String, credentials: Dictionary)
signal signed_out
signal audio_changed(enabled: bool)
var panels
var state: ForgeState
var art: ForgeArt
var root: Control
var header: Panel
var login_panel: Panel
var login_intro: VBoxContainer
var form_status: Label
var username: LineEdit
var password: LineEdit
var address: LineEdit
var create_account: CheckButton
var connect_button: Button
var continue_button: Button
var world_name: Label
var world_details: Label
var online: Label
var energy_container: VBoxContainer
var energy_bar: ProgressBar
var energy_label: Label
var connection: Label
var hotbar: HBoxContainer
var hotbar_slots: Array = []
var selected_name: Label
var chat_box: VBoxContainer
var chat_log: RichTextLabel
var chat_input: LineEdit
var notes: Panel
var note_text: Label
var toast: Label
var toast_time := 0.0
var modal: Panel
var modal_kind := ""
var modal_body: VBoxContainer
var inventory_slots: Array = []
var directory: Array = []
var storage_slots: Array = []
var offer_fields := {}
var current_invite := ""
var invite_button: Button
var sound := true
var tutorial := {"gather":false,"build":false,"grow":false,"craft":false}
var compact := false
var front_menu
var game_enabled := false
var remember_session := true
var account_menu
var account_status: Label
var account_fields := {}
var account_data := {}
const INK := Color("f2fff8")
const MUTED := Color("b6d3cb")
const ACCENT := Color("f5d48e")

func box(bg: Color = Color("123c43"), border: Color = Color("3f7b7c"), margin: int = 16) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(10)
	style.set_content_margin_all(margin)
	return style

func label(text: String, font_size: int = 14, color: Color = INK) -> Label:
	var node := Label.new()
	node.text = text
	node.add_theme_font_size_override("font_size",font_size)
	node.add_theme_color_override("font_color",color)
	return node

func button(text: String, callback: Callable, primary: bool = false) -> Button:
	var node := Button.new()
	node.text = text
	node.focus_mode = Control.FOCUS_NONE
	node.custom_minimum_size.y = 36
	node.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	node.add_theme_stylebox_override("normal",box(Color("66e7b4") if primary else Color("21535a"),Color("76ebc3") if primary else Color("4f8c87"),10))
	node.add_theme_stylebox_override("hover",box(Color("a0f3ca") if primary else Color("326b70"),Color("9df6d1"),10))
	node.add_theme_stylebox_override("pressed",box(Color("4acfa1") if primary else Color("39797b"),Color("78d3be"),10))
	node.add_theme_color_override("font_color",Color("0e3f37") if primary else INK)
	node.add_theme_color_override("font_hover_color",Color("0e3f37") if primary else INK)
	var focus_style := box(Color(0,0,0,0),ACCENT,10)
	focus_style.set_border_width_all(2)
	node.add_theme_stylebox_override("focus",focus_style)
	node.add_theme_stylebox_override("disabled",box(Color("23474e"),Color("396269"),10))
	node.add_theme_color_override("font_disabled_color",Color("7ca3a0"))
	node.add_theme_font_size_override("font_size",13)
	node.pressed.connect(func():
		get_viewport().gui_release_focus()
		callback.call())
	return node

func input(placeholder: String, secret: bool = false) -> LineEdit:
	var node := LineEdit.new()
	node.placeholder_text = placeholder
	node.secret = secret
	node.custom_minimum_size.y = 40
	node.add_theme_stylebox_override("normal",box(Color("0f3037"),Color("4f8584"),10))
	node.add_theme_stylebox_override("focus",box(Color("20515a"),Color("74d9bd"),10))
	node.add_theme_color_override("font_color",INK)
	node.add_theme_color_override("font_placeholder_color",Color("7ba9a5"))
	node.add_theme_font_size_override("font_size",14)
	return node

func column(parent: Node, separation: int = 12) -> VBoxContainer:
	var c := VBoxContainer.new()
	c.add_theme_constant_override("separation",separation)
	parent.add_child(c)
	return c

func margin(parent: Node, padding: int = 22) -> MarginContainer:
	var m := MarginContainer.new()
	parent.add_child(m)
	m.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left","right","top","bottom"]:
		m.add_theme_constant_override("margin_"+side,padding)
	return m

func _ready() -> void:
	panels = load("res://client/panels.gd").new()
	panels.ui = self
	panels.state = state
	panels.art = art
	root = Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var theme := Theme.new()
	theme.default_font = load("res://assets/fonts/DejaVuSans.ttf")
	theme.default_font_size = 14
	theme.set_color("font_color","Label",INK)
	theme.set_color("font_color","CheckButton",INK)
	root.theme = theme
	build_header()
	build_login()
	build_hud()
	get_viewport().size_changed.connect(layout)
	layout()
	show_game(false)

func build_header() -> void:
	header = Panel.new()
	header.add_theme_stylebox_override("panel",box(Color("153b43"),Color("498984"),0))
	root.add_child(header)
	var row := HBoxContainer.new()
	header.add_child(row)
	row.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	row.offset_left = 26
	row.offset_right = -26
	row.add_theme_constant_override("separation",14)
	var emblem := TextureRect.new()
	emblem.texture = load("res://assets/icon.svg")
	emblem.custom_minimum_size = Vector2(42,42)
	emblem.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	emblem.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	row.add_child(emblem)
	var brand := column(row,0)
	brand.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	brand.add_child(label("WORLDFORGE",20))
	brand.add_child(label("MAKE SOMETHING THAT MATTERS",9,MUTED))
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	var nav := HBoxContainer.new()
	nav.name = "Navigation"
	nav.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	nav.add_theme_constant_override("separation",8)
	row.add_child(nav)
	nav.add_child(button("Explore worlds  [M]",func(): open_worlds()))
	nav.add_child(button("Crafting  [C]",func(): open_craft()))
	nav.add_child(button("Backpack  [I]",func(): open_inventory()))
	nav.add_child(button("Journal  [L]",func(): open_gameplay()))
	nav.add_child(button("Settings",func(): open_settings()))

func build_login() -> void:
	front_menu = load("res://client/front_menu.gd").new()
	front_menu.ui = self
	root.add_child(front_menu)

func refresh_session() -> void:
	if front_menu and front_menu.mode == "title" and not game_enabled and not front_menu.loading:
		front_menu.show_title()

func submit_login() -> void:
	if front_menu: front_menu.submit()

func save_session(token: String, endpoint: String) -> void:
	if remember_session:
		var saved := {"token":token,"endpoint":endpoint,"name":state.player_name}
		# IndexedDB sync is asynchronous in the browser. Save the remembered
		# token synchronously so an immediate refresh keeps the account.
		if OS.has_feature("web"): write_web_session(saved)
		var file := FileAccess.open("user://session.json",FileAccess.WRITE)
		if file: file.store_string(JSON.stringify(saved))
	else:
		clear_session()
	if is_instance_valid(password): password.clear()
	if front_menu and is_instance_valid(front_menu.confirm_password): front_menu.confirm_password.clear()

func valid_session(value: Variant) -> Dictionary:
	if not value is Dictionary or not value.get("token") is String or str(value.token).is_empty(): return {}
	if not value.get("endpoint") is String or not value.get("name") is String: return {}
	return value

func read_session_file() -> Dictionary:
	if not FileAccess.file_exists("user://session.json"): return {}
	return valid_session(JSON.parse_string(FileAccess.get_file_as_string("user://session.json")))

func write_web_session(saved: Dictionary) -> bool:
	var result = JavaScriptBridge.eval("(()=>{try{localStorage.setItem('worldforge.session.v2',JSON.stringify(" + JSON.stringify(saved) + "));localStorage.removeItem('worldforge.session.cleared');return true;}catch(_){return false;}})()",true)
	return result == true

func load_session() -> Dictionary:
	if OS.has_feature("web"):
		var raw = JavaScriptBridge.eval("(()=>{try{const raw=localStorage.getItem('worldforge.session.v2');const cleared=localStorage.getItem('worldforge.session.cleared')==='1';if(cleared)return JSON.stringify({available:true,present:true,session:null});if(raw===null)return JSON.stringify({available:true,present:false});try{return JSON.stringify({available:true,present:true,session:JSON.parse(raw)});}catch(_){return JSON.stringify({available:true,present:true,session:null});}}catch(_){return JSON.stringify({available:false,present:true,session:null});}})()",true)
		var result = JSON.parse_string(str(raw))
		if not result is Dictionary or not result.get("available",false): return {}
		if result.get("present",false): return valid_session(result.get("session"))
		# Migrate a Stage 1 session once. A synchronous logout tombstone above
		# prevents an old IndexedDB file from restoring a revoked token.
		var legacy := read_session_file()
		if not legacy.is_empty(): write_web_session(legacy)
		return legacy
	return read_session_file()

func clear_session() -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.eval("(()=>{try{localStorage.setItem('worldforge.session.cleared','1');localStorage.removeItem('worldforge.session.v2');return true;}catch(_){return false;}})()",true)
	if FileAccess.file_exists("user://session.json"):
		DirAccess.remove_absolute("user://session.json")

func show_start() -> void:
	show_game(false)

func set_loading(phase: String, progress: float = -1.0) -> void:
	if front_menu: front_menu.set_loading(phase,progress)

func finish_loading() -> void:
	if front_menu: front_menu.finish_loading()

func on_auth_error(text: String) -> void:
	if front_menu: front_menu.auth_error(text)

func build_hud() -> void:
	world_name = label("NEXUS",18)
	world_name.position = Vector2(28,69)
	root.add_child(world_name)
	world_details = label("",11,MUTED)
	world_details.position = Vector2(120,74)
	root.add_child(world_details)
	online = label("",12,MUTED)
	root.add_child(online)
	hotbar = HBoxContainer.new()
	hotbar.add_theme_constant_override("separation",5)
	root.add_child(hotbar)
	for i in range(10):
		var slot = load("res://client/slot.gd").new()
		slot.index = i
		slot.hotbar = true
		slot.draggable = true
		slot.splittable = true
		slot.art = art
		slot.custom_minimum_size = Vector2(56,56)
		slot.pressed.connect(func(): intent.emit("select",{"slot":i}))
		slot.dragged.connect(func(a,b,n): intent.emit("move_slot",{"from":a,"to":b,"count":n}))
		slot.split_requested.connect(split_stack)
		hotbar.add_child(slot)
		hotbar_slots.append(slot)
	selected_name = label("",13,INK)
	selected_name.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	root.add_child(selected_name)
	connection = label("●  CONNECTED    ·    SERVER-SAVED",10,MUTED)
	root.add_child(connection)
	energy_container = column(root,4)
	energy_container.mouse_filter = Control.MOUSE_FILTER_STOP
	energy_container.tooltip_text = "Hold Shift while moving to sprint. Energy recovers while walking or resting. Food restores energy."
	energy_label = label("ENERGY  100 / 100   ·   SHIFT TO SPRINT",9,MUTED)
	energy_container.add_child(energy_label)
	energy_bar = ProgressBar.new()
	energy_bar.custom_minimum_size = Vector2(195,8)
	energy_bar.show_percentage = false
	energy_bar.value = 100
	energy_bar.add_theme_stylebox_override("background",box(Color("17464b"),Color("407d76"),0))
	energy_bar.add_theme_stylebox_override("fill",box(Color("6aebb8"),Color("6aebb8"),0))
	energy_container.add_child(energy_bar)
	var controls := label("A D  move     SPACE  jump     LMB  mine     RMB  place     E  interact",11,MUTED)
	controls.name = "Controls"
	controls.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	root.add_child(controls)
	chat_box = VBoxContainer.new()
	chat_box.add_theme_constant_override("separation",4)
	root.add_child(chat_box)
	chat_box.add_child(label("WORLD CHAT    ·    ENTER TO TALK",9,MUTED))
	chat_log = RichTextLabel.new()
	chat_log.bbcode_enabled = false
	chat_log.custom_minimum_size = Vector2(320,104)
	chat_log.scroll_following = true
	chat_log.add_theme_font_size_override("normal_font_size",12)
	chat_log.add_theme_color_override("default_color",Color("d2f1e4"))
	chat_log.add_theme_stylebox_override("normal",box(Color(.04,.09,.10,.7),Color(.15,.24,.22,.5),9))
	chat_box.add_child(chat_log)
	chat_input = input("Say something to this world…")
	chat_input.max_length = 180
	chat_input.custom_minimum_size.y = 30
	chat_input.text_submitted.connect(func(text):
		if not text.strip_edges().is_empty(): intent.emit("chat",{"text":text})
		chat_input.clear()
		chat_input.release_focus())
	chat_box.add_child(chat_input)
	notes = Panel.new()
	notes.add_theme_stylebox_override("panel",box(Color(.06,.20,.23,.93),Color("5a9388")))
	root.add_child(notes)
	var notes_body := column(margin(notes,16),10)
	var notes_row := HBoxContainer.new()
	notes_body.add_child(notes_row)
	notes_row.add_child(label("FIELD NOTES   /   01",10,ACCENT))
	var hide := button("−",func(): notes.visible = false)
	hide.custom_minimum_size = Vector2(22,22)
	notes_row.add_child(hide)
	notes_body.add_child(label("Make yourself at home",16))
	note_text = label("",12,MUTED)
	update_notes()
	notes_body.add_child(note_text)
	toast = label("",13,ACCENT)
	toast.z_index = 60
	toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast.add_theme_stylebox_override("normal",box(Color("215b50"),Color("78ceb3"),12))
	toast.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(toast)
	toast.visible = false
	invite_button = button("",func(): intent.emit("trade_accept",{"player":current_invite}))
	root.add_child(invite_button)
	invite_button.visible = false

func layout() -> void:
	var size := get_viewport().get_visible_rect().size
	header.size = Vector2(size.x,62)
	compact = size.x < 1100
	if front_menu: front_menu.layout()
	online.position = Vector2(size.x-240,73)
	hotbar.position = Vector2((size.x-605)/2,size.y-129)
	selected_name.position = Vector2(size.x/2-400,size.y-62)
	selected_name.size = Vector2(800,20)
	connection.position = Vector2(26,size.y-29)
	energy_container.position = Vector2(size.x-232,size.y-(177 if compact else 122))
	energy_container.size = Vector2(202,34)
	var controls := root.get_node("Controls") as Label
	controls.position = Vector2(size.x/2-420,size.y-29)
	controls.size = Vector2(840,20)
	chat_box.position = Vector2(34,size.y-350)
	chat_box.size = Vector2(310,160)
	notes.position = Vector2(34,109)
	notes.size = Vector2(254,214)
	toast.position = Vector2(size.x/2-280,107)
	toast.size = Vector2(560,44)
	invite_button.position = Vector2(size.x-330,111)
	invite_button.size = Vector2(295,42)
	if modal:
		modal.position = (size-modal.size)/2
	if front_menu: front_menu.publish_rects.call_deferred()

func show_game(enabled: bool) -> void:
	game_enabled = enabled
	if front_menu:
		if enabled: front_menu.hide()
		else: front_menu.show_title()
	header.find_child("Navigation",true,false).visible = enabled
	for node in [world_name,world_details,online,hotbar,selected_name,connection,energy_container,chat_box,notes,root.get_node("Controls")]:
		node.visible = enabled
	if not enabled:
		if panels.has_method("clear_private"): panels.clear_private()
		chat_log.clear()
		close_modal()
		invite_button.visible = false
		toast.visible = false
		set_status("Enter a world with your account.")
	else:
		append_chat("Field guide","Welcome to WORLDFORGE. Point at a block and hold left click to gather. Press H for controls.")
	layout()
	refresh_inventory()

func set_status(text: String) -> void:
	if front_menu: front_menu.set_status(text)

func notify(text: String) -> void:
	toast.text = text
	toast.visible = true
	toast_time = 4

func _process(delta: float) -> void:
	if game_enabled:
		var energy: float = clampf(float(state.predicted.get("energy",100)),0.0,100.0)
		energy_bar.value = lerpf(energy_bar.value,energy,1.0-exp(-delta*9.0))
		energy_label.text = "ENERGY  " + str(roundi(energy)) + " / 100   ·   SHIFT TO SPRINT"
	if toast_time > 0:
		toast_time -= delta
		toast.visible = toast_time > 0
	if not state.meta.is_empty():
		world_name.text = state.meta.name
		world_details.position.x = 42 + world_name.get_minimum_size().x
		var biome: String = state.meta.biome
		world_details.text = " /  "+biome.to_upper()+"    ·    "+("UNCLAIMED" if state.meta.owner == null else state.meta.owner_name+"'S WORLD")
		online.text = "●  "+str(state.players.size())+" EXPLORER"+("S" if state.players.size() != 1 else "")+" ONLINE"

func refresh_inventory() -> void:
	for i in range(hotbar_slots.size()):
		var slot = hotbar_slots[i]
		slot.selected = i == state.selected
		slot.set_stack(state.inventory[i] if i < state.inventory.size() else null,state.items)
	for i in range(inventory_slots.size()):
		var slot = inventory_slots[i]
		if is_instance_valid(slot):
			slot.set_stack(state.inventory[i] if i < state.inventory.size() else null,state.items)
	if state.inventory.size() > state.selected and state.inventory[state.selected]:
		var def: Dictionary = state.items[state.inventory[state.selected].id]
		selected_name.text = def.name + "    /    " + def.category.to_upper()
	else:
		selected_name.text = "Bare hands    /    SELECT A SLOT"
	if state.owned("grain") > 0: tutorial.grow = true
	if state.owned("stone_pick") > 0: tutorial.craft = true
	update_notes()

func split_stack(from: int, count: int) -> void:
	for offset in range(30):
		var to := posmod(offset+10,30)
		if state.inventory[to] == null:
			intent.emit("move_slot",{"from":from,"to":to,"count":count})
			return
	notify("Make room in your backpack before splitting a stack.")

func update_notes() -> void:
	if not note_text: return
	var text := ""
	for pair in [["gather","Gather cedar from a tree"],["build","Place your first block"],["grow","Plant & harvest sungrain"],["craft","Craft a stone pickaxe"]]:
		text += ("✓  " if tutorial[pair[0]] else "·   ")+pair[1]+"\n"
	note_text.text = text+"\nH  controls   /   J  field notes"

func append_chat(name: String, text: String) -> void:
	chat_log.add_text(name+"  ›  "+text+"\n")
	if chat_log.get_line_count() > 100:
		var lines := chat_log.text.split("\n")
		chat_log.text = "\n".join(lines.slice(-60))

func begin_modal(title: String, kind: String, width: float = 680, height: float = 530) -> VBoxContainer:
	close_modal(false)
	modal_kind = kind
	modal = Panel.new()
	modal.z_index = 50
	modal.size = Vector2(width,height)
	modal.add_theme_stylebox_override("panel",box(Color("153b43"),Color("74a99b")))
	root.add_child(modal)
	modal_body = column(margin(modal,24),13)
	var top := HBoxContainer.new()
	modal_body.add_child(top)
	var heading := label(title,22)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(heading)
	top.add_child(button("Close  [Esc]",func(): close_modal()))
	modal_body.add_child(HSeparator.new())
	layout()
	return modal_body

func close_modal(cancel_trade: bool = true) -> void:
	if account_menu:
		if modal_kind == "account": account_menu.clear_passwords()
		if modal_kind == "recovery_code": account_menu.recovery_code = ""
	if cancel_trade and modal_kind == "trade" and not state.trade.is_empty():
		intent.emit("trade_cancel",{"trade_id":state.trade.id})
	if modal:
		modal.queue_free()
	modal = null
	modal_kind = ""
	inventory_slots.clear()
	storage_slots.clear()
	offer_fields.clear()
	if front_menu: front_menu.publish_rects.call_deferred()

func open_inventory() -> void:
	panels.open_inventory()

func open_craft() -> void:
	panels.open_craft()

func open_worlds() -> void:
	panels.open_worlds()

func render_worlds() -> void:
	panels.render_worlds()

func open_storage() -> void:
	panels.open_storage()

func refresh_storage() -> void:
	panels.refresh_storage()

func open_permissions() -> void:
	panels.open_permissions()

func open_social() -> void:
	panels.open_social()

func show_invite(data: Dictionary) -> void:
	panels.show_invite(data)

func open_trade() -> void:
	panels.open_trade()

func open_settings() -> void:
	panels.open_settings()

func open_help() -> void:
	panels.open_help()


func open_admin(data: Dictionary) -> void:
	panels.open_admin(data)

func refresh_admin(data: Dictionary) -> void:
	panels.refresh_admin(data)


func refresh_craft() -> void:
	panels.refresh_craft()

func refresh_social(data: Dictionary) -> void:
	panels.refresh_social(data)

func receive_private_message(data: Dictionary) -> void:
	panels.receive_private_message(data)

func receive_world_invite(data: Dictionary) -> void:
	panels.receive_world_invite(data)

func open_gameplay(data: Dictionary = {}) -> void:
	panels.open_gameplay(data)

func refresh_gameplay(data: Dictionary) -> void:
	panels.refresh_gameplay(data)

func open_machine(data: Dictionary) -> void:
	panels.open_machine(data)

func refresh_machine(data: Dictionary) -> void:
	panels.refresh_machine(data)

func open_portal(data: Dictionary) -> void:
	panels.open_portal(data)


func open_account() -> void:
	ensure_account_menu()
	account_menu.open()

func ensure_account_menu() -> void:
	if not account_menu:
		account_menu = load("res://client/account_menu.gd").new()
		account_menu.ui = self

func show_recovery_code(code: String) -> void:
	ensure_account_menu()
	account_menu.show_code(code)

func apply_account(data: Dictionary) -> void:
	ensure_account_menu()
	if data.get("action") == "recovery_reset":
		front_menu.show_form("signin")
		front_menu.set_status(str(data.get("text","Password reset. Sign in with your new password.")))
		clear_session()
	account_menu.apply(data)


func debug_modal_rects() -> Dictionary:
	if not is_instance_valid(modal): return {}
	var info := {"kind":modal_kind,"panel":front_menu.rect_data(modal),"buttons":[],"fields":{}}
	var pending: Array = [modal]
	while not pending.is_empty():
		var node: Node = pending.pop_front()
		if node is Button:
			info.buttons.append({"text":node.text,"name":str(node.name),"rect":front_menu.rect_data(node)})
		elif node is LineEdit:
			info.fields[str(node.name)] = front_menu.rect_data(node)
		pending.append_array(node.get_children())
	return info


func publish_modal_rects() -> void:
	if front_menu: front_menu.publish_rects.call_deferred()
