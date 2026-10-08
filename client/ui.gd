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
const INK := Color("e2e7d9")
const MUTED := Color("9daea3")
const ACCENT := Color("d9be82")

func box(bg: Color = Color("162529"), border: Color = Color("3b4f4c"), margin: int = 16) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.border_color = border
	style.set_border_width_all(1)
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
	node.add_theme_stylebox_override("normal",box(Color("bac8a6") if primary else Color("223336"),Color("bac8a6") if primary else Color("465a53"),10))
	node.add_theme_stylebox_override("hover",box(Color("d1d8b9") if primary else Color("304640"),Color("c4cdac"),10))
	node.add_theme_stylebox_override("pressed",box(Color("98af91") if primary else Color("3a5147"),Color("b1c297"),10))
	node.add_theme_color_override("font_color",Color("1d302c") if primary else INK)
	node.add_theme_color_override("font_hover_color",Color("1d302c") if primary else INK)
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
	node.add_theme_stylebox_override("normal",box(Color("101f23"),Color("3b504b"),10))
	node.add_theme_stylebox_override("focus",box(Color("14272a"),Color("a7ba99"),10))
	node.add_theme_color_override("font_color",INK)
	node.add_theme_color_override("font_placeholder_color",Color("72877d"))
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
	header.add_theme_stylebox_override("panel",box(Color("102025"),Color("344641"),0))
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
	nav.add_child(button("Settings",func(): open_settings()))

func build_login() -> void:
	login_intro = VBoxContainer.new()
	root.add_child(login_intro)
	login_intro.add_theme_constant_override("separation",16)
	login_intro.add_child(label("THE WORLD IS WHAT YOU MAKE IT",11,ACCENT))
	login_intro.add_child(label("Small beginnings.\nLimitless worlds.",44))
	login_intro.add_child(label("Find your place in a living, persistent sandbox.\nBuild a home. Grow a harvest. Bring a friend.",16,Color("bcc9b7")))
	var space := Control.new()
	space.custom_minimum_size.y = 12
	login_intro.add_child(space)
	login_intro.add_child(label("01   BUILD YOUR CORNER OF THE WORLD",11,MUTED))
	login_intro.add_child(label("02   GROW, CRAFT & EXCHANGE",11,MUTED))
	login_intro.add_child(label("03   LEAVE SOMETHING WORTH DISCOVERING",11,MUTED))
	login_panel = Panel.new()
	login_panel.add_theme_stylebox_override("panel",box(Color("142529"),Color("567066")))
	root.add_child(login_panel)
	var body := column(margin(login_panel,28),10)
	body.add_child(label("BEGIN YOUR JOURNEY",10,ACCENT))
	body.add_child(label("Welcome, explorer.",26))
	body.add_child(label("One account. A thousand possibilities.",13,MUTED))
	body.add_child(HSeparator.new())
	body.add_child(label("EXPLORER NAME",10,MUTED))
	username = input("Choose your name")
	username.max_length = 20
	body.add_child(username)
	body.add_child(label("PASSWORD",10,MUTED))
	password = input("At least 8 characters",true)
	password.max_length = 128
	body.add_child(password)
	create_account = CheckButton.new()
	create_account.text = "Create a new account"
	create_account.button_pressed = true
	body.add_child(create_account)
	body.add_child(label("SERVER ADDRESS",10,MUTED))
	address = input("ws://127.0.0.1:8765")
	address.text = "ws://127.0.0.1:8765"
	if OS.has_feature("web"):
		var host = JavaScriptBridge.eval("window.location.host")
		var protocol = JavaScriptBridge.eval("window.location.protocol")
		address.text = ("wss://" if protocol == "https:" else "ws://") + str(host)
	body.add_child(address)
	connect_button = button("Enter WORLDFORGE   →",func(): submit_login(),true)
	connect_button.custom_minimum_size.y = 46
	body.add_child(connect_button)
	password.text_submitted.connect(func(_text): submit_login())
	form_status = label("Progress is saved on the server, not this device.",11,MUTED)
	form_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	form_status.custom_minimum_size.y = 35
	body.add_child(form_status)
	continue_button = button("Continue your journey",func():
		var saved := load_session()
		if not saved.is_empty(): login.emit(str(saved.get("endpoint",address.text)),{"token":saved.token}))
	body.add_child(continue_button)
	refresh_session()

func refresh_session() -> void:
	var saved := load_session()
	continue_button.visible = not saved.is_empty()
	if not saved.is_empty():
		continue_button.text = "Continue as "+str(saved.get("name","explorer"))
		create_account.button_pressed = false

func submit_login() -> void:
	if username.text.strip_edges().length() < 3 or password.text.length() < 8:
		set_status("Choose a name and a password of at least 8 characters.")
		return
	if not address.text.begins_with("ws://") and not address.text.begins_with("wss://"):
		set_status("Use a ws:// or wss:// server address.")
		return
	login.emit(address.text,{"name":username.text.strip_edges(),"password":password.text,"register":create_account.button_pressed})

func save_session(token: String, endpoint: String) -> void:
	var file := FileAccess.open("user://session.json",FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify({"token":token,"endpoint":endpoint,"name":state.player_name}))
	password.clear()

func load_session() -> Dictionary:
	if not FileAccess.file_exists("user://session.json"):
		return {}
	var result = JSON.parse_string(FileAccess.get_file_as_string("user://session.json"))
	return result if result is Dictionary else {}

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
	chat_log.add_theme_color_override("default_color",Color("c0cdbc"))
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
	notes.add_theme_stylebox_override("panel",box(Color(.055,.105,.11,.86),Color("41574a")))
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
	toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast.add_theme_stylebox_override("normal",box(Color("1c302b"),Color("526b52"),12))
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
	login_intro.position = Vector2(64,155)
	login_intro.visible = login_panel.visible and not compact
	login_panel.position = Vector2((size.x-410)/2 if compact else size.x-488,139)
	login_panel.size = Vector2(410,584)
	online.position = Vector2(size.x-240,73)
	hotbar.position = Vector2((size.x-605)/2,size.y-129)
	selected_name.position = Vector2(size.x/2-400,size.y-62)
	selected_name.size = Vector2(800,20)
	connection.position = Vector2(26,size.y-29)
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

func show_game(enabled: bool) -> void:
	refresh_session()
	login_panel.visible = not enabled
	login_intro.visible = not enabled and not compact
	header.find_child("Navigation",true,false).visible = enabled
	for node in [world_name,world_details,online,hotbar,selected_name,connection,chat_box,notes,root.get_node("Controls")]:
		node.visible = enabled
	if not enabled:
		close_modal()
		invite_button.visible = false
		toast.visible = false
		set_status("Enter a world with your account.")
	else:
		append_chat("Field guide","Welcome to WORLDFORGE. Point at a block and hold left click to gather. Press H for controls.")
	layout()
	refresh_inventory()

func set_status(text: String) -> void:
	form_status.text = text
	form_status.add_theme_color_override("font_color",ACCENT)

func notify(text: String) -> void:
	toast.text = text
	toast.visible = true
	toast_time = 4

func _process(delta: float) -> void:
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
	modal.size = Vector2(width,height)
	modal.add_theme_stylebox_override("panel",box(Color("14262a"),Color("6a7e67")))
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
	if cancel_trade and modal_kind == "trade" and not state.trade.is_empty():
		intent.emit("trade_cancel",{"trade_id":state.trade.id})
	if modal:
		modal.queue_free()
	modal = null
	modal_kind = ""
	inventory_slots.clear()
	storage_slots.clear()
	offer_fields.clear()

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
