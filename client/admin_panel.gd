extends RefCounted
## Server-authorized administration. Keep inputs alive when replies update the lists.
var ui: ForgeUI
var state: ForgeState
var art: ForgeArt
var snapshot := {}
var body: VBoxContainer
var tabs: TabContainer
var item_list: ItemList
var item_search: LineEdit
var item_filter: OptionButton
var item_title: Label
var item_description: Label
var item_icon: TextureRect
var item_count: Label
var give_target: OptionButton
var quantity: SpinBox
var give_button: Button
var player_list: ItemList
var player_search: LineEdit
var player_filter: OptionButton
var player_status: Label
var target_input: LineEdit
var reason: LineEdit
var mute_minutes: SpinBox
var world_input: LineEdit
var confirm_row: HBoxContainer
var confirm_text: Label
var confirm_button: Button
var moderation_buttons := {}
var splits: Array[BoxContainer] = []
var selected_item := ""
var selected_player := ""
var pending_action := {}
var search_items := ""
var search_players := ""
var selected_tab := 0

func reset() -> void:
	snapshot = {}
	pending_action.clear()
	selected_item = ""
	selected_player = ""
	search_items = ""
	search_players = ""
	selected_tab = 0
	moderation_buttons.clear()
	splits.clear()
	body = null

func open(data: Dictionary) -> void:
	snapshot = data
	if is_open():
		refresh(data)
		return
	body = ui.begin_modal("World administration", "admin", 920, 650)
	var intro := HBoxContainer.new()
	body.add_child(intro)
	var subtitle := ui.label("Create, help explorers, and keep your worlds welcoming.", 12, ui.MUTED)
	subtitle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.add_child(subtitle)
	intro.add_child(ui.button("Refresh", func(): ui.intent.emit("admin_open", {})))
	tabs = TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tabs.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(tabs)
	splits.clear()
	build_supplies()
	build_explorers()
	tabs.current_tab = clampi(selected_tab, 0, 1)
	tabs.tab_changed.connect(func(index: int): selected_tab = index)
	if not ui.get_viewport().size_changed.is_connected(layout):
		ui.get_viewport().size_changed.connect(layout)
	refresh(data)
	layout()

func is_open() -> bool:
	return ui.modal_kind == "admin" and is_instance_valid(body) and is_instance_valid(ui.modal)

func page(title: String) -> BoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = title
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	var split := BoxContainer.new()
	split.add_theme_constant_override("separation", 18)
	split.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	split.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(split)
	splits.append(split)
	return split

func list_widget(parent: Node) -> ItemList:
	var list := ItemList.new()
	list.custom_minimum_size = Vector2(240, 200)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.fixed_icon_size = Vector2i(32, 32)
	list.add_theme_font_size_override("font_size", 13)
	list.add_theme_stylebox_override("panel", ui.box(Color("102025"), Color("354f49"), 8))
	list.add_theme_stylebox_override("selected", ui.box(Color("365548"), Color("8cab86"), 6))
	list.add_theme_stylebox_override("selected_focus", ui.box(Color("365548"), Color("8cab86"), 6))
	list.add_theme_color_override("font_color", ui.INK)
	list.add_theme_color_override("font_selected_color", ui.INK)
	parent.add_child(list)
	return list

func dropdown(parent: Node) -> OptionButton:
	var field := OptionButton.new()
	field.custom_minimum_size.y = 36
	field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.add_theme_font_size_override("font_size", 13)
	parent.add_child(field)
	return field

func number_field(parent: Node, maximum: int, initial: int) -> SpinBox:
	var field := SpinBox.new()
	field.min_value = 1
	field.max_value = maximum
	field.step = 1
	field.value = initial
	field.custom_minimum_size = Vector2(108, 36)
	parent.add_child(field)
	return field

func build_supplies() -> void:
	var split := page("Supplies")
	var catalogue := ui.column(split, 9)
	catalogue.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	catalogue.size_flags_vertical = Control.SIZE_EXPAND_FILL
	catalogue.add_child(ui.label("BLOCKS, TOOLS & MATERIALS", 10, ui.ACCENT))
	item_search = ui.input("Search by name or item ID…")
	item_search.text = search_items
	catalogue.add_child(item_search)
	item_filter = dropdown(catalogue)
	for category in ["All categories", "Blocks", "Materials", "Tools", "Seeds & crops", "Stations & storage"]:
		item_filter.add_item(category)
	item_list = list_widget(catalogue)
	item_list.item_selected.connect(func(index: int):
		selected_item = str(item_list.get_item_metadata(index))
		update_item_detail())
	item_count = ui.label("", 11, ui.MUTED)
	catalogue.add_child(item_count)
	item_search.text_changed.connect(func(value: String): search_items = value; populate_items())
	item_filter.item_selected.connect(func(_index: int): populate_items())
	var details := ui.column(split, 12)
	details.custom_minimum_size.x = 280
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	details.add_child(ui.label("SELECT AN ITEM", 10, ui.ACCENT))
	item_icon = TextureRect.new()
	item_icon.custom_minimum_size = Vector2(72, 72)
	item_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	item_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	details.add_child(item_icon)
	item_title = ui.label("Choose from the catalogue", 20)
	item_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.add_child(item_title)
	item_description = ui.label("", 12, ui.MUTED)
	item_description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.add_child(item_description)
	details.add_child(HSeparator.new())
	details.add_child(ui.label("SEND TO BACKPACK", 10, ui.ACCENT))
	give_target = dropdown(details)
	var amount_row := HBoxContainer.new()
	details.add_child(amount_row)
	amount_row.add_child(ui.label("Quantity", 13, ui.MUTED))
	quantity = number_field(amount_row, 9999, 99)
	give_button = ui.button("Give selected item", grant_item, true)
	details.add_child(give_button)
	var hint := ui.label("Choose yourself or another explorer. The whole amount must fit in their backpack. Trading explorers must finish their exchange first.", 12, ui.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	details.add_child(hint)

func build_explorers() -> void:
	var split := page("Explorers")
	var accounts := ui.column(split, 9)
	accounts.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	accounts.size_flags_vertical = Control.SIZE_EXPAND_FILL
	accounts.add_child(ui.label("EXPLORER DIRECTORY", 10, ui.ACCENT))
	player_search = ui.input("Find an explorer…")
	player_search.text = search_players
	accounts.add_child(player_search)
	player_filter = dropdown(accounts)
	for filter in ["All explorers", "Online", "Banned", "Muted"]:
		player_filter.add_item(filter)
	player_list = list_widget(accounts)
	player_list.fixed_icon_size = Vector2i.ZERO
	player_list.item_selected.connect(func(index: int):
		selected_player = str(player_list.get_item_metadata(index))
		var player := find_player(selected_player)
		target_input.text = str(player.get("name", ""))
		pending_action.clear()
		confirm_row.visible = false
		update_player_detail())
	player_search.text_changed.connect(func(value: String): search_players = value; populate_players())
	player_filter.item_selected.connect(func(_index: int): populate_players())
	accounts.add_child(ui.label("Online status covers every world on this server.", 11, ui.MUTED))
	var actions := ui.column(split, 9)
	actions.custom_minimum_size.x = 310
	actions.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions.add_child(ui.label("SELECT AN EXPLORER OR ENTER THEIR NAME", 10, ui.ACCENT))
	target_input = ui.input("Explorer name")
	target_input.max_length = 20
	actions.add_child(target_input)
	target_input.text_changed.connect(func(_value: String):
		selected_player = ""
		pending_action.clear()
		confirm_row.visible = false
		update_player_detail())
	player_status = ui.label("Select an explorer to see their status.", 12, ui.MUTED)
	player_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	actions.add_child(player_status)
	reason = ui.input("Reason (optional)")
	reason.max_length = 180
	actions.add_child(reason)
	var removal := HBoxContainer.new()
	actions.add_child(removal)
	for action in ["kick", "ban", "unban"]:
		var control := ui.button(action.capitalize(), func(): moderate(action))
		control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		removal.add_child(control)
		moderation_buttons[action] = control
	var mute_row := HBoxContainer.new()
	actions.add_child(mute_row)
	mute_minutes = number_field(mute_row, 1440, 10)
	mute_minutes.suffix = "min"
	for action in ["mute", "unmute"]:
		var control := ui.button(action.capitalize(), func(): moderate(action))
		control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		mute_row.add_child(control)
		moderation_buttons[action] = control
	confirm_row = HBoxContainer.new()
	confirm_row.visible = false
	actions.add_child(confirm_row)
	confirm_text = ui.label("", 11, ui.ACCENT)
	confirm_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	confirm_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	confirm_row.add_child(confirm_text)
	confirm_button = ui.button("Confirm", confirm_moderation, true)
	confirm_row.add_child(confirm_button)
	confirm_row.add_child(ui.button("Cancel", func(): pending_action.clear(); confirm_row.visible = false))
	actions.add_child(HSeparator.new())
	actions.add_child(ui.label("TRAVEL TO A SAFE WORLD SPAWN", 10, ui.ACCENT))
	world_input = ui.input("Existing world name")
	world_input.max_length = 20
	world_input.text = str(state.meta.get("name", ""))
	actions.add_child(world_input)
	var travel := ui.button("Move explorer to world", teleport_player)
	actions.add_child(travel)
	var hint := ui.label("Bans remain until removed. Muting stops chat for the chosen time. Administrators cannot be kicked, banned, or muted here.", 11, ui.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	actions.add_child(hint)

func refresh(data: Dictionary) -> void:
	snapshot = data
	if not is_open(): return
	populate_items()
	populate_targets()
	populate_players()
	update_player_detail()

func populate_items() -> void:
	if not is_instance_valid(item_list): return
	var scroll := item_list.get_v_scroll_bar().value
	item_list.clear()
	var categories: Array = [[], ["block"], ["material"], ["tool"], ["seed", "crop"], ["station", "storage", "core"]]
	var chosen: Array = categories[item_filter.selected]
	var query := item_search.text.strip_edges().to_lower()
	var items: Array = snapshot.get("items", []).duplicate()
	items.sort_custom(func(a: Dictionary, b: Dictionary): return str(a.get("name", a.id)).naturalnocasecmp_to(str(b.get("name", b.id))) < 0)
	for item in items:
		var id := str(item.get("id", ""))
		if id.is_empty(): continue
		var definition: Dictionary = state.items.get(id, item)
		var category := str(item.get("category", ""))
		if not chosen.is_empty() and not category in chosen: continue
		var searchable := (str(item.get("name", id)) + " " + id + " " + str(definition.get("description", ""))).to_lower()
		if not query.is_empty() and not query in searchable: continue
		var index := item_list.add_item(str(item.get("name", id)), art.icon(id, definition))
		item_list.set_item_metadata(index, id)
		item_list.set_item_tooltip(index, str(item.get("name", id)) + "  /  " + category.capitalize() + "\n" + id)
		if id == selected_item: item_list.select(index)
	item_list.get_v_scroll_bar().value = scroll
	item_count.text = str(item_list.item_count) + " matching items  /  " + str(items.size()) + " in this server"
	if selected_item.is_empty() and item_list.item_count > 0:
		selected_item = str(item_list.get_item_metadata(0))
		item_list.select(0)
	update_item_detail()

func update_item_detail() -> void:
	var item := {}
	for entry in snapshot.get("items", []):
		if str(entry.get("id", "")) == selected_item: item = entry; break
	give_button.disabled = item.is_empty()
	if item.is_empty():
		item_icon.texture = null
		item_title.text = "Choose from the catalogue"
		item_description.text = ""
		return
	var definition: Dictionary = state.items.get(selected_item, item)
	item_icon.texture = art.icon(selected_item, definition)
	item_title.text = str(item.get("name", selected_item))
	item_description.text = str(definition.get("description", "")) + "\n\n" + str(item.get("category", "item")).capitalize() + "  /  " + selected_item + "\nStack limit: " + str(int(item.get("stack", 1)))

func populate_targets() -> void:
	var previous := state.player_id
	if give_target.item_count > 0 and give_target.selected >= 0:
		previous = str(give_target.get_item_metadata(give_target.selected))
	give_target.clear()
	give_target.add_item("My backpack · " + state.player_name)
	give_target.set_item_metadata(0, state.player_id)
	for player in snapshot.get("players", []):
		var id := str(player.get("id", ""))
		if id.is_empty() or id == state.player_id: continue
		var index := give_target.item_count
		give_target.add_item(str(player.get("name", "Explorer")) + (" · online" if player.get("online", false) else " · offline"))
		give_target.set_item_metadata(index, id)
		if id == previous: give_target.select(index)

func populate_players() -> void:
	if not is_instance_valid(player_list): return
	var scroll := player_list.get_v_scroll_bar().value
	player_list.clear()
	var query := player_search.text.strip_edges().to_lower()
	var players: Array = snapshot.get("players", []).duplicate()
	players.sort_custom(func(a: Dictionary, b: Dictionary):
		if bool(a.get("online", false)) != bool(b.get("online", false)): return bool(a.get("online", false))
		return str(a.get("name", "")).naturalnocasecmp_to(str(b.get("name", ""))) < 0)
	for player in players:
		var id := str(player.get("id", ""))
		var name := str(player.get("name", "Explorer"))
		if id.is_empty() or (not query.is_empty() and not query in name.to_lower()): continue
		if player_filter.selected == 1 and not player.get("online", false): continue
		if player_filter.selected == 2 and not player.get("banned", false): continue
		if player_filter.selected == 3 and not player.get("muted", false): continue
		var status := "Online" if player.get("online", false) else "Offline"
		if player.get("banned", false): status = "Banned"
		elif player.get("muted", false): status += " · muted"
		if player.get("admin", false): status += " · admin"
		var index := player_list.add_item(name + "  ·  " + status)
		player_list.set_item_metadata(index, id)
		player_list.set_item_tooltip(index, name + "\n" + str(player.get("world", "")))
		if id == selected_player: player_list.select(index)
	player_list.get_v_scroll_bar().value = scroll

func find_player(id: String) -> Dictionary:
	for player in snapshot.get("players", []):
		if str(player.get("id", "")) == id: return player
	return {}

func target_player() -> Dictionary:
	if not selected_player.is_empty(): return find_player(selected_player)
	var name := target_input.text.strip_edges().to_lower()
	for player in snapshot.get("players", []):
		if str(player.get("name", "")).to_lower() == name: return player
	return {}

func target_value() -> String:
	return selected_player if not selected_player.is_empty() else target_input.text.strip_edges()

func update_player_detail() -> void:
	var player := target_player()
	var target := target_value()
	var protected := bool(player.get("admin", false)) or str(player.get("id", "")) == state.player_id
	for action in moderation_buttons:
		var control: Button = moderation_buttons[action]
		control.disabled = target.is_empty() or (protected and action in ["ban", "kick", "mute"])
	if player.is_empty():
		player_status.text = "Enter an existing explorer's name." if not target.is_empty() else "Select an explorer to see their status."
		return
	var status := "Online in " + str(player.get("world", "a world")) if player.get("online", false) else "Offline"
	if player.get("admin", false): status += " · Administrator"
	if player.get("banned", false): status += "\nBanned: " + str(player.get("ban_reason", "No reason given"))
	if player.get("muted", false): status += "\nChat muted"
	player_status.text = status

func grant_item() -> void:
	if selected_item.is_empty() or give_target.selected < 0: return
	quantity.apply()
	ui.intent.emit("admin_action", {"action":"grant", "target":str(give_target.get_item_metadata(give_target.selected)), "item":selected_item, "count":int(quantity.value)})

func moderate(action: String) -> void:
	var target := target_value()
	if target.is_empty(): ui.notify("Choose an explorer first."); return
	mute_minutes.apply()
	var request := {"action":action, "target":target, "reason":reason.text.strip_edges()}
	if action == "mute": request["minutes"] = int(mute_minutes.value)
	if action in ["ban", "kick"]:
		pending_action = request
		confirm_text.text = action.capitalize() + " " + target_input.text.strip_edges() + "?"
		confirm_row.visible = true
		return
	ui.intent.emit("admin_action", request)

func confirm_moderation() -> void:
	if pending_action.is_empty(): return
	ui.intent.emit("admin_action", pending_action.duplicate())
	pending_action.clear()
	confirm_row.visible = false

func teleport_player() -> void:
	var target := target_value()
	var world := world_input.text.strip_edges()
	if target.is_empty(): ui.notify("Choose an explorer first."); return
	if world.is_empty(): ui.notify("Enter an existing world name."); return
	ui.intent.emit("admin_action", {"action":"teleport", "target":target, "world":world})

func layout() -> void:
	if not is_open(): return
	var size := ui.get_viewport().get_visible_rect().size
	ui.modal.size = Vector2(minf(920, size.x - 32), minf(650, size.y - 36))
	ui.modal.position = (size - ui.modal.size) / 2
	for split in splits:
		if is_instance_valid(split): split.vertical = ui.modal.size.x < 760
