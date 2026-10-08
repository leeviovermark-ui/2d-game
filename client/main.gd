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
var minimap
var inspect_elapsed := 0.0
var footstep_clock := 0.0

func _ready() -> void:
	landscape = load("res://client/landscape.gd").new()
	landscape.state = state
	landscape.art = art
	add_child(landscape)
	network = load("res://client/network.gd").new()
	add_child(network)
	network.packet.connect(on_packet)
	network.status_changed.connect(on_status)
	audio = load("res://client/audio.gd").new()
	add_child(audio)
	ui = load("res://client/ui.gd").new()
	ui.state = state
	ui.art = art
	ui.intent.connect(on_intent)
	ui.login.connect(func(endpoint,credentials): network.connect_server(endpoint,credentials))
	ui.signed_out.connect(sign_out)
	ui.audio_changed.connect(func(enabled): audio.enabled=enabled)
	add_child(ui)
	minimap = load("res://client/minimap.gd").new()
	minimap.state = state
	ui.root.add_child(minimap)
	minimap.hide()
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
	inspect_elapsed += delta
	if inspect_elapsed >= .25:
		inspect_elapsed = 0
		publish_controls()
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

func _physics_process(delta: float) -> void:
	if network: network.poll()
	if not playing or not network.connected: return
	var active: bool = not focused() and not ui.modal and not ui.front_menu.loading
	var axis := 0
	var held := false
	if active:
		axis = int(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT))-int(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT))
		held = Input.is_physical_key_pressed(KEY_SPACE) or Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP)
	var was_grounded: bool = state.predicted.get("grounded", false)
	var intent := state.predict({"axis":axis, "jump":jump_pending and active, "jump_held":held, "sprint":active and Input.is_physical_key_pressed(KEY_SHIFT)})
	if was_grounded and float(state.predicted.get("vy", 0)) < -1: audio.play("jump")
	footstep_clock -= delta
	if active and state.predicted.get("grounded", false) and absf(float(state.predicted.get("vx", 0))) > 2:
		if footstep_clock <= 0:
			audio.play("footstep")
			footstep_clock = maxf(.20, 1.9 / absf(float(state.predicted.vx)))
	else: footstep_clock = 0
	network.send(intent.merged({"type":"input"}))
	jump_pending = false

func _input(event: InputEvent) -> void:
	if playing and event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		if ui.front_menu.loading:
			sign_out()
			ui.front_menu.show_form(ui.front_menu.last_form)
			return
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
		elif event.keycode == KEY_L: ui.open_gameplay()
		elif event.keycode == KEY_K: minimap.visible = not minimap.visible
		elif event.keycode == KEY_F and not ui.modal: network.action("use_item", {"slot":state.selected})
		elif event.keycode == KEY_G and not ui.modal:
			var target: Vector2i = landscape.tile_at_mouse()
			network.action("fish", {"x":target.x, "y":target.y})
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
			mining_target = Vector2i(-1,-1)
			state.inventory = data.slots
			state.selected = int(data.selected)
			state.server_offset = float(data.server_time)-Time.get_unix_time_from_system()
			state.load_world(data.world, data.get("player", {}))
			minimap.world_changed()
			state.trade = {}
			state.social = {}
			state.progression = {}
			playing = true
			landscape.landing = false
			ui.save_session(data.token,network.endpoint)
			ui.finish_loading()
			ui.show_game(true)
			if data.get("recovery_code") is String and not str(data.recovery_code).is_empty(): ui.show_recovery_code(data.recovery_code)
			if state.is_admin: ui.append_chat("Server", "Administrator access: type /addomen in chat to open your tools.")
		"world":
			state.load_world(data.world, data.get("player", {}))
			mining_target = Vector2i(-1,-1)
			jump_pending = false
			ui.close_modal()
			landscape.camera = Vector2(0,105)
			ui.finish_loading()
			minimap.world_changed()
		"players":
			state.apply_players(data.players)
			state.server_offset = float(data.server_time)-Time.get_unix_time_from_system()
		"inventory":
			state.inventory = data.slots
			state.selected = int(data.selected)
			ui.refresh_inventory()
			if ui.modal_kind == "craft": ui.refresh_craft()
			if ui.modal_kind == "machine" and ui.panels.gameplay_panel: ui.panels.gameplay_panel.update_machine_recipe()
			if ui.modal_kind == "gameplay": ui.refresh_gameplay(state.progression)
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
			minimap.dirty = true
		"drop": state.drops[data.drop.id] = data.drop
		"drop_removed":
			state.drops.erase(data.id)
			if data.get("collector") == state.player_id: audio.play("collect")
		"metadata": state.meta = data.meta
		"departure": state.players.erase(data.id); state.display_positions.erase(data.id)
		"chat": ui.append_chat(data.name,data.text)
		"error":
			if playing: ui.notify(data.text)
			else:
				if ui.game_enabled: ui.show_game(false)
				if data.get("request_type") == "auth" and not network.resume_token.is_empty():
					ui.clear_session()
					network.resume_token = ""
				network.disconnect_server(false)
				ui.on_auth_error(data.text)
			if data.get("code") == "session_expired":
				ui.clear_session()
				network.resume_token = ""
			if playing and str(data.get("request_type", "")).begins_with("account_"): ui.apply_account({"text":data.text})
			if ui.front_menu.loading: ui.finish_loading()
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
		"account_result":
			ui.apply_account(data)
			if data.action == "logout":
				sign_out(false)
		"social_state": state.social = data; ui.refresh_social(data)
		"private_message": ui.receive_private_message(data)
		"world_invite": ui.receive_world_invite(data)
		"progression": state.progression = data; ui.refresh_gameplay(data)
		"progress_update":
			if ui.modal_kind == "gameplay": network.send({"type":"progression"})
		"open_machine": ui.open_machine(data)
		"machine_update": ui.refresh_machine(data)
		"open_portal": ui.open_portal(data)
		"portal": state.portals[Vector2i(data.x,data.y)] = data.destination
		"equipment":
			if state.players.has(state.player_id): state.players[state.player_id].appearance = data.appearance
			if ui.modal_kind == "gameplay": ui.refresh_gameplay(state.progression)
		"appearance":
			if state.players.has(data.player): state.players[data.player].appearance = data.appearance
		"emote":
			if data.player == state.player_id: audio.play("emote")
			if state.players.has(data.player):
				state.players[data.player].emote = data.emote
				state.players[data.player].emote_until = data.until
		"vitals":
			if not state.predicted.is_empty(): state.predicted.energy = data.energy
		"fishing_result": ui.notify("Caught " + str(state.items.get(data.item, {}).get("name",data.item)) + "!"); audio.play("fish")
		"fish_splash": landscape.burst(int(data.x),int(data.y),"water")
		"consume": audio.play("eat")
		"pong": state.latency = maxi(0, Time.get_ticks_msec()-int(data.sent))
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

func on_status(text: String) -> void:
	ui.set_status(text)
	if text.begins_with("Reconnecting"):
		playing = false
		ui.close_modal(false)
		state.trade = {}
		ui.set_loading(text)
	elif text.begins_with("Connecting") or text.begins_with("Verifying"):
		ui.set_loading(text)
	elif text.begins_with("Disconnected") or text.begins_with("Connection timed") or text.begins_with("Could not"):
		var was_playing: bool = playing or ui.game_enabled
		playing = false
		landscape.landing = true
		ui.finish_loading()
		if was_playing: ui.show_game(false)
		ui.on_auth_error(text)

func sign_out(revoke := true) -> void:
	if revoke and network.connected: network.send({"type":"account_logout"})
	network.disconnect_server()
	playing = false
	landscape.landing = true
	minimap.hide()
	ui.clear_session()
	ui.show_game(false)

func on_intent(kind: String, data: Dictionary) -> void:
	if kind in ["travel", "create_world"] or (kind == "social_action" and data.get("action") == "join"):
		ui.set_loading("Entering your next world…")
	if kind in ["chat","directory","ignore","social_open","progression","account_info","account_password","account_recovery_rotate","account_sessions_clear","account_logout"]:
		network.send(data.merged({"type":kind}))
	else:
		network.action(kind,data)

func publish_controls() -> void:
	if not OS.has_feature("web") or not JavaScriptBridge.eval("window.worldforge_inspect === true", true): return
	var controls: Array = []
	var pending: Array = [ui.root]
	var viewport := get_viewport().get_visible_rect()
	var screen_transform := get_viewport().get_screen_transform()
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		pending.append_array(node.get_children())
		if not node is Control or not node.is_visible_in_tree(): continue
		var rect: Rect2 = node.get_global_rect().intersection(viewport)
		var ancestor: Node = node.get_parent()
		while ancestor is Control:
			if ancestor.clip_contents: rect = rect.intersection(ancestor.get_global_rect())
			ancestor = ancestor.get_parent()
		if rect.size.x <= 1 or rect.size.y <= 1: continue
		rect = screen_transform * rect
		var info := {"kind":node.get_class(),"name":str(node.name),"path":str(node.get_path()),"rect":{"x":rect.position.x,"y":rect.position.y,"w":rect.size.x,"h":rect.size.y}}
		if node is Button:
			info.text = node.text
			info.disabled = node.disabled
			if node is OptionButton:
				info.options = []
				info.selected = node.selected
				for index in range(node.item_count): info.options.append(node.get_item_text(index))
				var popup: PopupMenu = node.get_popup()
				info.popup_visible = popup.visible
				if popup.visible and popup.item_count > 0:
					var popup_transform := popup.get_screen_transform()
					var popup_rect := popup_transform * Rect2(Vector2.ZERO,Vector2(popup.size))
					info.popup_rect = {"x":popup_rect.position.x,"y":popup_rect.position.y,"w":popup_rect.size.x,"h":popup_rect.size.y}
					var panel_style := popup.get_theme_stylebox("panel")
					var top: float = panel_style.get_content_margin(SIDE_TOP)
					var bottom: float = panel_style.get_content_margin(SIDE_BOTTOM)
					var row_height: float = (popup.size.y-top-bottom) / popup.item_count
					info.popup_items = []
					for index in range(popup.item_count):
						var row := popup_transform * Rect2(0,top+index*row_height,popup.size.x,row_height)
						info.popup_items.append({"index":index,"text":popup.get_item_text(index),"rect":{"x":row.position.x,"y":row.position.y,"w":row.size.x,"h":row.size.y}})
		elif node is LineEdit:
			info.placeholder = node.placeholder_text
		elif node is SpinBox:
			info.min = node.min_value
			info.max = node.max_value
		elif node is ItemList:
			info.items = []
			info.selected = Array(node.get_selected_items())
			for index in range(node.item_count): info.items.append(node.get_item_text(index))
		elif node is Label:
			info.text = node.text
		else:
			if node.get_script() == load("res://client/slot.gd"):
				info.kind = "Slot"
				info.slot_index = node.index
				info.hotbar = node.hotbar
			else: continue
		if node.get_script() == load("res://client/slot.gd"):
			info.kind = "Slot"
			info.slot_index = node.index
			info.hotbar = node.hotbar
		controls.append(info)
	JavaScriptBridge.eval("window.worldforge_controls = " + JSON.stringify(controls) + ";", true)
