extends RefCounted
## Inventory, workshop, travel, storage, permissions, and social interaction panels.
var ui: ForgeUI
var state: ForgeState
var art: ForgeArt
var admin_panel
var catalogue
var social_panel
var gameplay_panel
var craft_search: LineEdit
var craft_category: OptionButton
var craft_amount: SpinBox
var craft_results: VBoxContainer
var craft_scroll: ScrollContainer
var craft_summary: Label
var craft_rows := {}
var icon_refresh_generation := 0

func get_catalogue():
	if not catalogue:
		catalogue = load("res://client/world_catalogue.gd").new()
		catalogue.ui = ui
		catalogue.state = state
	return catalogue

func get_social():
	if not social_panel:
		social_panel = load("res://client/social_panel.gd").new()
		social_panel.ui = ui
		social_panel.state = state
	return social_panel

func get_gameplay():
	if not gameplay_panel:
		gameplay_panel = load("res://client/gameplay_panel.gd").new()
		gameplay_panel.ui = ui
		gameplay_panel.state = state
		gameplay_panel.art = art
	return gameplay_panel

func open_admin(data: Dictionary) -> void:
	if not admin_panel:
		admin_panel = load("res://client/admin_panel.gd").new()
		admin_panel.ui = ui
		admin_panel.state = state
		admin_panel.art = art
	admin_panel.open(data)

func refresh_admin(data: Dictionary) -> void:
	if admin_panel:
		admin_panel.refresh(data)

func open_inventory() -> void:
	var body := ui.begin_modal("Your backpack","inventory",680,456)
	body.add_child(ui.label("30 SLOTS   /   Drag to move · right-click to split · click to select",11,ui.MUTED))
	var grid := GridContainer.new()
	grid.columns = 10
	grid.add_theme_constant_override("h_separation",4)
	grid.add_theme_constant_override("v_separation",4)
	body.add_child(grid)
	for i in range(30):
		var slot = load("res://client/slot.gd").new()
		slot.index = i
		slot.art = art
		slot.draggable = true
		slot.splittable = true
		slot.custom_minimum_size = Vector2(58,58)
		slot.pressed.connect(func():
			if i < 10: ui.intent.emit("select",{"slot":i})
			else: ui.notify("Drag this item into the hotbar to equip it."))
		slot.dragged.connect(func(a,b,n): ui.intent.emit("move_slot",{"from":a,"to":b,"count":n}))
		slot.split_requested.connect(ui.split_stack)
		grid.add_child(slot)
		ui.inventory_slots.append(slot)
	var row := HBoxContainer.new()
	body.add_child(row)
	row.add_child(ui.button("Drop 1 selected item",func(): ui.intent.emit("drop_item",{"slot":state.selected,"count":1})))
	row.add_child(ui.button("Drop selected stack",func():
		var stack = state.inventory[state.selected]
		if stack: ui.intent.emit("drop_item",{"slot":state.selected,"count":int(stack.n)})))
	body.add_child(ui.label("Your first ten slots are your hotbar. Tools work while selected.",12,ui.MUTED))
	ui.refresh_inventory()

func open_craft() -> void:
	if ui.modal_kind == "craft" and is_instance_valid(craft_results):
		refresh_craft()
		return
	var body := ui.begin_modal("The workshop","craft",840,660)
	body.add_child(ui.label("Turn discoveries into possibilities. Stations must be within five tiles.",12,ui.MUTED))
	var filters := HBoxContainer.new()
	filters.add_theme_constant_override("separation",10)
	body.add_child(filters)
	craft_search = ui.input("Find a recipe, material, or station")
	craft_search.name = "RecipeSearch"
	craft_search.max_length = 40
	craft_search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	filters.add_child(craft_search)
	craft_category = OptionButton.new()
	craft_category.name = "RecipeCategory"
	for title in ["All recipes","Blocks","Tools","Stations","Food & farming","Outfits"]:
		craft_category.add_item(title)
	filters.add_child(craft_category)
	filters.add_child(ui.label("Batches",11,ui.MUTED))
	craft_amount = SpinBox.new()
	craft_amount.name = "CraftBatches"
	craft_amount.min_value = 1
	craft_amount.max_value = 50
	craft_amount.value = 1
	craft_amount.custom_minimum_size.x = 80
	filters.add_child(craft_amount)
	craft_summary = ui.label("",11,ui.MUTED)
	body.add_child(craft_summary)
	craft_scroll = ScrollContainer.new()
	craft_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(craft_scroll)
	craft_scroll.get_v_scroll_bar().value_changed.connect(func(_value): schedule_recipe_icons())
	craft_results = ui.column(craft_scroll,8)
	craft_results.name = "RecipeResults"
	craft_results.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	craft_rows.clear()
	for recipe in state.recipes:
		var panel := PanelContainer.new()
		panel.add_theme_stylebox_override("panel",ui.box(Color("20515a"),Color("44887f"),12))
		craft_results.add_child(panel)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation",13)
		panel.add_child(row)
		var icon := TextureRect.new()
		icon.custom_minimum_size = Vector2(38,38)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		row.add_child(icon)
		var desc := ui.column(row,4)
		desc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var title := ui.label("",15)
		desc.add_child(title)
		var materials := ui.label("",11,ui.MUTED)
		materials.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		desc.add_child(materials)
		var station: Label = null
		if recipe.has("station"):
			station = ui.label("",11,ui.ACCENT)
			station.text = "At " + state.items[recipe.station].name
			desc.add_child(station)
		var action := ui.button("Craft",func(): ui.intent.emit("craft",{"recipe":recipe.id,"count":int(craft_amount.value)}),true)
		row.add_child(action)
		craft_rows[recipe.id] = {"panel":panel,"icon":icon,"output":recipe.output,"title":title,"materials":materials,"station":station,"button":action}
	craft_search.text_changed.connect(func(_text): refresh_craft())
	craft_category.item_selected.connect(func(_index): refresh_craft())
	craft_amount.value_changed.connect(func(_value): refresh_craft())
	refresh_craft()

func refresh_craft() -> void:
	if ui.modal_kind != "craft" or not is_instance_valid(craft_results): return
	var quantity := int(craft_amount.value)
	var query := craft_search.text.strip_edges().to_lower()
	var visible_count := 0
	var ready_count := 0
	for recipe in state.recipes:
		if not craft_rows.has(recipe.id): continue
		var nodes: Dictionary = craft_rows[recipe.id]
		var definition: Dictionary = state.items[recipe.output]
		var category := str(definition.category)
		var category_matches := true
		match craft_category.selected:
			1: category_matches = category in ["block", "decoration"]
			2: category_matches = category == "tool"
			3: category_matches = category == "station"
			4: category_matches = category in ["food", "seed", "crop", "resource", "material"]
			5: category_matches = category in ["apparel", "equipment", "cosmetic", "outfit"]
		var haystack := str(definition.name) + " " + str(definition.get("description", ""))
		var materials := ""
		var enough := true
		for item in recipe.ingredients:
			var needed := int(recipe.ingredients[item]) * quantity
			var owned: int = state.owned(item)
			haystack += " " + str(state.items[item].name)
			materials += str(state.items[item].name) + " " + str(owned) + "/" + str(needed) + "   "
			if owned < needed: enough = false
		var station_near := true
		if recipe.has("station"):
			haystack += " " + str(state.items[recipe.station].name)
			station_near = station_nearby(recipe.station)
		nodes.panel.visible = category_matches and (query.is_empty() or haystack.to_lower().contains(query))
		if nodes.panel.visible: visible_count += 1
		nodes.title.text = str(definition.name) + "  ×" + str(int(recipe.amount) * quantity)
		nodes.materials.text = materials
		nodes.materials.add_theme_color_override("font_color",ui.MUTED if enough else Color("ffc1a4"))
		var machine_recipe: bool = recipe.get("seconds", 0) > 0 or recipe.get("duration", 0) > 0 or recipe.get("process_time", 0) > 0
		nodes.button.text = "Queue batch" if machine_recipe else "Craft"
		if machine_recipe and quantity > 20: nodes.button.text = "Max 20 batches"
		nodes.button.disabled = not enough or not station_near or (machine_recipe and quantity > 20)
		if enough and station_near and nodes.panel.visible and not nodes.button.disabled: ready_count += 1
		if recipe.has("station"):
			nodes.station.text = ("Use " if machine_recipe else "At ") + str(state.items[recipe.station].name) + (" · nearby" if station_near else " · move closer")
	craft_summary.text = str(visible_count) + " recipes shown  ·  " + str(ready_count) + " ready to craft  ·  " + str(quantity) + " batch" + ("es" if quantity != 1 else "")
	schedule_recipe_icons()
	ui.publish_modal_rects()

func schedule_recipe_icons() -> void:
	icon_refresh_generation += 1
	refresh_visible_recipe_icons.call_deferred(icon_refresh_generation)

func refresh_visible_recipe_icons(generation: int) -> void:
	if not is_instance_valid(ui) or not ui.is_inside_tree(): return
	await ui.get_tree().process_frame
	if generation != icon_refresh_generation or not is_instance_valid(ui) or ui.modal_kind != "craft" or not is_instance_valid(craft_scroll): return
	var visible_rect := craft_scroll.get_global_rect().grow(60)
	for nodes in craft_rows.values():
		if not is_instance_valid(nodes.panel) or not nodes.panel.visible or nodes.icon.texture != null: continue
		if nodes.panel.get_global_rect().intersects(visible_rect): nodes.icon.texture = art.icon(nodes.output,state.items[nodes.output])

func station_nearby(station: String) -> bool:
	var position: Vector2 = state.display_positions.get(state.player_id,Vector2.ZERO)
	for tile in state.tiles:
		if state.tiles[tile] == station and Vector2(tile.x+.5,tile.y+.5).distance_to(position) <= float(state.movement.reach): return true
	return false

func open_worlds() -> void:
	ui.intent.emit("directory",{})
	render_worlds()

func render_worlds() -> void:
	get_catalogue().open()

func open_storage() -> void:
	var body := ui.begin_modal("Cedar storage","storage",660,560)
	body.add_child(ui.label("Click a chest slot to withdraw. Click your backpack to deposit.\nTransfers are atomic and checked against current contents.",12,ui.MUTED))
	var grid := GridContainer.new()
	grid.columns = 6
	body.add_child(grid)
	for i in range(12):
		var slot = load("res://client/slot.gd").new()
		slot.art = art
		slot.pressed.connect(func():
			var stack = state.storage.slots[i]
			if stack: ui.intent.emit("storage",{"x":state.storage.x,"y":state.storage.y,"deposit":false,"slot":i,"count":int(stack.n)}))
		grid.add_child(slot)
		ui.storage_slots.append(slot)
	body.add_child(ui.label("YOUR BACKPACK   /   Click to deposit one entire stack",10,ui.MUTED))
	var pack := GridContainer.new()
	pack.columns = 10
	body.add_child(pack)
	for i in range(30):
		var slot = load("res://client/slot.gd").new()
		slot.art = art
		slot.custom_minimum_size = Vector2(55,55)
		slot.pressed.connect(func():
			var stack = state.inventory[i]
			if stack: ui.intent.emit("storage",{"x":state.storage.x,"y":state.storage.y,"deposit":true,"slot":i,"count":int(stack.n)}))
		pack.add_child(slot)
		ui.inventory_slots.append(slot)
	ui.refresh_inventory()
	refresh_storage()

func refresh_storage() -> void:
	for i in range(ui.storage_slots.size()):
		ui.storage_slots[i].set_stack(state.storage.slots[i],state.items)

func open_permissions() -> void:
	var body := ui.begin_modal("World Core","permissions",550,410)
	body.add_child(ui.label("WORLD  /  "+str(state.meta.get("name","")),11,ui.ACCENT))
	if state.meta.get("owner") != state.player_id:
		body.add_child(ui.label("This world belongs to "+str(state.meta.get("owner_name","nobody"))+".\nOnly its owner may change permissions.",14))
		return
	var guests := CheckButton.new()
	guests.text = "Allow guests to build, mine, and use storage"
	guests.button_pressed = state.meta.guest_build
	body.add_child(guests)
	body.add_child(ui.label("BUILDERS   /   Comma-separated explorer names",11,ui.MUTED))
	var builders := ui.input("ExplorerOne, ExplorerTwo")
	var names: Array = state.meta.get("builder_names",[])
	builders.text = ", ".join(names)
	body.add_child(builders)
	body.add_child(ui.button("Save world permissions",func():
		var list: Array = []
		for name in builders.text.split(","):
			if not name.strip_edges().is_empty(): list.append(name.strip_edges())
		ui.intent.emit("permissions",{"guest_build":guests.button_pressed,"builders":list}),true))
	body.add_child(ui.label("Builder access includes crafting stations and chest contents.\nOwnership remains with the explorer who placed the Core.",12,ui.MUTED))

func open_social() -> void:
	get_social().open()

func refresh_social(data: Dictionary) -> void:
	get_social().refresh(data)

func receive_private_message(data: Dictionary) -> void:
	get_social().receive_message(data)

func receive_world_invite(data: Dictionary) -> void:
	get_social().receive_invite(data)

func clear_private() -> void:
	if social_panel: social_panel.reset()
	if gameplay_panel: gameplay_panel.reset()
	if catalogue: catalogue.reset()
	if admin_panel: admin_panel.reset()
	ui.directory.clear()
	ui.current_invite = ""
	craft_rows.clear()
	craft_search = null
	craft_category = null
	craft_amount = null
	craft_results = null
	craft_scroll = null
	craft_summary = null
	icon_refresh_generation += 1

func open_gameplay(data: Dictionary = {}) -> void:
	get_gameplay().open(data)

func refresh_gameplay(data: Dictionary) -> void:
	get_gameplay().refresh(data)

func open_machine(data: Dictionary) -> void:
	get_gameplay().open_machine(data)

func refresh_machine(data: Dictionary) -> void:
	get_gameplay().refresh_machine(data)

func open_portal(data: Dictionary) -> void:
	get_gameplay().open_portal(data)

func show_invite(data: Dictionary) -> void:
	ui.current_invite = data.player
	ui.invite_button.text = data.name+" wants to trade  ·  Accept"
	ui.invite_button.visible = true
	ui.notify("Trade invitation expires in 20 seconds.")

func open_trade() -> void:
	ui.invite_button.visible = false
	var trade: Dictionary = state.trade
	var body := ui.begin_modal("A fair exchange","trade",680,580)
	var other: String = trade.players[0] if trade.players[1] == state.player_id else trade.players[1]
	body.add_child(ui.label("Offers changed? Both locks and confirmations reset. Inventory is held\nwhile trading. Stay nearby; disconnecting safely cancels the trade.",12,ui.MUTED))
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation",24)
	body.add_child(columns)
	for id in trade.players:
		var col := ui.column(columns,7)
		col.custom_minimum_size.x = 288
		col.add_child(ui.label(trade.names[trade.players.find(id)]+("  (you)" if id == state.player_id else ""),16,ui.ACCENT))
		var offer: Dictionary = trade.offers[id]
		if offer.is_empty(): col.add_child(ui.label("No items offered",12,ui.MUTED))
		for item in offer:
			col.add_child(ui.label(state.items[item].name+"  ×"+str(int(offer[item])),13))
		col.add_child(ui.label("LOCKED" if id in trade.locked else "Reviewing offer",10,ui.MUTED))
		if id in trade.confirmed: col.add_child(ui.label("CONFIRMED",10,ui.ACCENT))
	body.add_child(HSeparator.new())
	body.add_child(ui.label("EDIT YOUR OFFER   /   Changing it resets all confirmations",10,ui.MUTED))
	var row := HBoxContainer.new()
	body.add_child(row)
	var choices := OptionButton.new()
	choices.custom_minimum_size = Vector2(250,36)
	var ids: Array = []
	for stack in state.inventory:
		if stack and not stack.id in ids:
			ids.append(stack.id)
			choices.add_item(state.items[stack.id].name+" ("+str(state.owned(stack.id))+")")
	row.add_child(choices)
	var amount := SpinBox.new()
	amount.min_value = 1
	amount.max_value = 999
	amount.value = 1
	row.add_child(amount)
	row.add_child(ui.button("Set item",func():
		if ids.is_empty(): return
		var offer: Dictionary = trade.offers[state.player_id].duplicate()
		offer[ids[choices.selected]] = int(amount.value)
		ui.intent.emit("trade_offer",{"offer":offer,"trade_id":trade.id})))
	var actions := HBoxContainer.new()
	body.add_child(actions)
	actions.add_child(ui.button("Clear offer",func(): ui.intent.emit("trade_offer",{"offer":{},"trade_id":trade.id})))
	var lock := ui.button("Lock my offer",func(): ui.intent.emit("trade_lock",{"revision":trade.revision,"trade_id":trade.id}),true)
	lock.disabled = state.player_id in trade.locked
	actions.add_child(lock)
	var confirm := ui.button("Confirm exchange",func(): ui.intent.emit("trade_confirm",{"revision":trade.revision,"trade_id":trade.id}),true)
	confirm.disabled = trade.locked.size() != 2 or state.player_id in trade.confirmed
	actions.add_child(confirm)
	body.add_child(ui.button("Cancel trade safely",func(): ui.intent.emit("trade_cancel",{"trade_id":trade.id})))

func open_settings() -> void:
	var body := ui.begin_modal("Make yourself at home","settings",600,550)
	var toggle := CheckButton.new()
	toggle.text = "Interaction sounds"
	toggle.button_pressed = ui.sound
	toggle.toggled.connect(func(value): ui.sound = value; ui.audio_changed.emit(value))
	body.add_child(toggle)
	body.add_child(ui.button("Explorers & trading  [P]",func(): open_social()))
	body.add_child(ui.button("Explorer journal & equipment  [L]",func(): open_gameplay()))
	body.add_child(ui.button("Account & saved sessions",func(): ui.open_account()))
	body.add_child(ui.button("World permissions",func(): open_permissions()))
	body.add_child(ui.button("Controls & field guide  [H]",func(): open_help()))
	body.add_child(ui.button("Disconnect & save",func(): ui.signed_out.emit()))
	body.add_child(ui.label("Progress is saved on the server. Reconnect with your password\nor this device's saved session. Use WSS for remote servers.",12,ui.MUTED))

func open_help() -> void:
	var body := ui.begin_modal("An explorer's field guide","help",710,650)
	body.add_child(ui.label("A / D or ← / →       Move\nSpace / W / ↑         Jump · release for a shorter hop\nHold Shift                Sprint while you have energy\nHold left mouse       Mine a nearby tile\nRight mouse           Place the selected block or plant a seed\nE                             Harvest, open stations, chests, and portals\nG / F                        Fish nearby water / eat selected food\n1–9 / 0                    Select hotbar slot\nI / C / M                  Backpack / crafting / world catalogue\nP / Enter                 Friends & explorers / world chat\nL / K                        Explorer journal / minimap\nJ / Esc                    Field notes / close panel",14,ui.INK))
	body.add_child(HSeparator.new())
	body.add_child(ui.label("Find your footing",18,ui.ACCENT))
	body.add_child(ui.label("Gather cedar logs and fiber from the trees. Your cedar pick can mine\nstone. Place a workbench, then craft a stone pick to reach iron.\nPlant a garden on earth; crops grow even while you are away.\nUse processing stations for food, metals, and new building materials.\nCreate a world and place a World Core to manage builder access.\nPress L for new mechanics and goals, or P to invite a friend.",13,ui.MUTED))
