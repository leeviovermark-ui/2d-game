extends Node
## Client composition. Rendering/UI are separate from network and shared definitions.
var state := ForgeState.new()
var art := ForgeArt.new()
var network
var landscape
var ui
var audio
var jump_pending := false
var mining_target := Vector2i(-1,-1)
var playing := false

func _ready() -> void:
	landscape = load("res://client/landscape.gd").new()
	landscape.state = state
	landscape.art = art
	add_child(landscape)
	network = load("res://client/network.gd").new()
	add_child(network)
	network.packet.connect(on_packet)
	network.status_changed.connect(func(text):
		ui.set_status(text)
		if text.begins_with("Disconnected") or text.begins_with("Connection timed"):
			playing = false
			landscape.landing = true
			ui.show_game(false))
	audio = load("res://client/audio.gd").new()
	add_child(audio)
	ui = load("res://client/ui.gd").new()
	ui.state = state
	ui.art = art
	ui.intent.connect(func(kind,data):
		if kind in ["chat","directory","ignore"]: network.send(data.merged({"type":kind}))
		else: network.action(kind,data))
	ui.login.connect(func(endpoint,credentials): network.connect_server(endpoint,credentials))
	ui.signed_out.connect(func(): network.disconnect_server(); playing=false; landscape.landing=true; ui.show_game(false))
	ui.audio_changed.connect(func(enabled): audio.enabled=enabled)
	add_child(ui)
	get_viewport().size_changed.connect(resize)
	resize()
	# Automated smoke clients use the same real scene and network implementation.
	var args := OS.get_cmdline_user_args()
	if "--smoke" in args:
		var name_arg := args.find("--name")
		var name_value := args[name_arg+1] if name_arg >= 0 else "GodotSmoke"
		network.connect_server("ws://127.0.0.1:8765",{"name":name_value,"password":"smoketest-password","register":"--register" in args})

func resize() -> void:
	var size := get_viewport().get_visible_rect().size
	landscape.position = Vector2(20,94)
	landscape.size = Vector2(size.x-40,size.y-258)

func focused() -> bool:
	var focus := get_viewport().gui_get_focus_owner()
	return focus is LineEdit or focus is SpinBox

func _process(delta: float) -> void:
	state.interpolate(delta)
	if not playing or not network.connected:
		return
	landscape.target = landscape.tile_at_mouse() if landscape.get_global_rect().has_point(landscape.get_global_mouse_position()) and not ui.modal else Vector2i(-1,-1)
	if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and not ui.modal and not focused() and landscape.target.x >= 0 and get_viewport().gui_get_hovered_control() == null:
		if landscape.target != mining_target and state.tiles.has(landscape.target):
			mining_target = landscape.target
			network.action("mine",{"x":mining_target.x,"y":mining_target.y})
	elif mining_target.x >= 0:
		mining_target = Vector2i(-1,-1)
		network.action("mine_cancel")

func _physics_process(_delta: float) -> void:
	if network: network.poll()
	if not playing or not network.connected: return
	var active: bool = not focused() and not ui.modal
	var axis := 0
	var held := false
	if active:
		axis = int(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT))-int(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT))
		held = Input.is_physical_key_pressed(KEY_SPACE) or Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP)
	var intent := state.predict({"axis":axis, "jump":jump_pending and active, "jump_held":held})
	network.send(intent.merged({"type":"input"}))
	jump_pending = false

func _input(event: InputEvent) -> void:
	if playing and event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		ui.close_modal()
		get_viewport().gui_release_focus()
		get_viewport().set_input_as_handled()

func _unhandled_input(event: InputEvent) -> void:
	if not playing:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			ui.close_modal()
			get_viewport().gui_release_focus()
			return
		if focused(): return
		if event.keycode in [KEY_SPACE,KEY_W,KEY_UP]: jump_pending = true
		elif event.keycode == KEY_I: ui.open_inventory()
		elif event.keycode == KEY_C: ui.open_craft()
		elif event.keycode == KEY_M: ui.open_worlds()
		elif event.keycode == KEY_P: ui.open_social()
		elif event.keycode == KEY_H: ui.open_help()
		elif event.keycode == KEY_J: ui.notes.visible = not ui.notes.visible
		elif event.keycode == KEY_ENTER: ui.chat_input.grab_focus()
		elif event.keycode == KEY_E and not ui.modal:
			var target: Vector2i = landscape.tile_at_mouse()
			network.action("interact",{"x":target.x,"y":target.y})
		elif event.keycode >= KEY_1 and event.keycode <= KEY_9: network.action("select",{"slot":event.keycode-KEY_1})
		elif event.keycode == KEY_0: network.action("select",{"slot":9})
	elif event is InputEventMouseButton and event.pressed and not ui.modal:
		if event.button_index == MOUSE_BUTTON_RIGHT and landscape.get_global_rect().has_point(event.position):
			var target: Vector2i = landscape.tile_at_mouse()
			network.action("place",{"x":target.x,"y":target.y})
		elif event.button_index in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN]:
			network.action("select",{"slot":posmod(state.selected+(1 if event.button_index==MOUSE_BUTTON_WHEEL_DOWN else -1),10)})

func on_packet(data: Dictionary) -> void:
	match data.type:
		"welcome":
			state.player_id = data.id
			state.player_name = data.name
			state.is_admin = data.get("admin", false)
			jump_pending = false
			state.inventory = data.slots
			state.selected = int(data.selected)
			state.server_offset = float(data.server_time)-Time.get_unix_time_from_system()
			state.load_world(data.world, data.get("player", {}))
			state.trade = {}
			playing = true
			landscape.landing = false
			ui.save_session(data.token,network.endpoint)
			ui.show_game(true)
			if state.is_admin: ui.append_chat("Server", "Administrator access: type /addomen in chat to open your tools.")
		"world":
			state.load_world(data.world, data.get("player", {}))
			mining_target = Vector2i(-1,-1)
			jump_pending = false
			ui.close_modal()
			landscape.camera = Vector2(0,105)
		"players":
			state.apply_players(data.players)
			state.server_offset = float(data.server_time)-Time.get_unix_time_from_system()
		"inventory":
			state.inventory = data.slots
			state.selected = int(data.selected)
			ui.refresh_inventory()
			if ui.modal_kind == "craft": ui.open_craft()
		"tile":
			var tile := Vector2i(data.x,data.y)
			var previous: String = state.tiles.get(tile,"")
			if data.item == null:
				state.tiles.erase(tile)
				state.crops.erase(tile)
				landscape.burst(tile.x,tile.y,previous)
				audio.play("mine")
				if previous == "wood": ui.tutorial.gather = true
			else:
				state.tiles[tile] = data.item
				if data.get("planted") != null: state.crops[tile] = data.planted
				ui.tutorial.build = true
				audio.play("place")
			ui.update_notes()
		"drop": state.drops[data.drop.id] = data.drop
		"drop_removed":
			state.drops.erase(data.id)
			if data.get("collector") == state.player_id: audio.play("collect")
		"metadata": state.meta = data.meta
		"departure": state.players.erase(data.id); state.display_positions.erase(data.id)
		"chat": ui.append_chat(data.name,data.text)
		"error":
			if playing: ui.notify(data.text)
			else: ui.set_status(data.text)
		"notice":
			ui.notify(data.text)
			if data.text.begins_with("Crafted"): audio.play("craft")
		"directory":
			ui.directory = data.worlds
			if ui.modal_kind == "worlds": ui.render_worlds()
		"storage": state.storage = data; ui.open_storage()
		"storage_update":
			if state.storage.get("x") == data.x and state.storage.get("y") == data.y:
				state.storage = data
				if ui.modal_kind == "storage": ui.refresh_storage()
		"admin_panel": ui.open_admin(data)
		"admin_state": ui.refresh_admin(data)
		"open_craft": ui.open_craft()
		"open_permissions": state.meta = data.meta; ui.open_permissions()
		"trade_invite": ui.show_invite(data)
		"trade": state.trade = data.trade; ui.open_trade()
		"trade_closed":
			state.trade = {}
			if ui.modal_kind == "trade": ui.close_modal()
			ui.notify(data.text)
