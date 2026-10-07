extends RefCounted
## Inventory, workshop, travel, storage, permissions, and social interaction panels.
var ui: ForgeUI
var state: ForgeState
var art: ForgeArt

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
	var body := ui.begin_modal("The workshop","craft",660,610)
	body.add_child(ui.label("Make more from what you find. Stations must be within five tiles.",12,ui.MUTED))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	var list := ui.column(scroll,8)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for recipe in state.recipes:
		var panel := PanelContainer.new()
		panel.add_theme_stylebox_override("panel",ui.box(Color("1d3032"),Color("3c504a"),12))
		list.add_child(panel)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation",13)
		panel.add_child(row)
		var icon := TextureRect.new()
		icon.texture = art.icon(recipe.output,state.items[recipe.output])
		icon.custom_minimum_size = Vector2(38,38)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		row.add_child(icon)
		var desc := ui.column(row,4)
		desc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		desc.add_child(ui.label(state.items[recipe.output].name+"  ×"+str(recipe.amount),14))
		var materials := ""
		var enough := true
		for item in recipe.ingredients:
			var n: int = state.owned(item)
			materials += state.items[item].name+" "+str(n)+"/"+str(recipe.ingredients[item])+"   "
			if n < recipe.ingredients[item]: enough = false
		desc.add_child(ui.label(materials,11,ui.MUTED if enough else Color("be9582")))
		if recipe.has("station"):
			desc.add_child(ui.label("Requires "+state.items[recipe.station].name,10,ui.MUTED))
		var action := ui.button("Craft",func(): ui.intent.emit("craft",{"recipe":recipe.id}),enough)
		action.disabled = not enough
		row.add_child(action)

func open_worlds() -> void:
	ui.intent.emit("directory",{})
	render_worlds()

func render_worlds() -> void:
	var body := ui.begin_modal("Beyond your horizon","worlds",670,620)
	body.add_child(ui.label("Visit a world, or start a new story. Names are unique across the server.",12,ui.MUTED))
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.y = 180
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	var list := ui.column(scroll,7)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for world in ui.directory:
		var row := HBoxContainer.new()
		list.add_child(row)
		var desc := ui.column(row,3)
		desc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		desc.add_child(ui.label(world.name,16))
		desc.add_child(ui.label(world.biome.capitalize()+"  /  "+("Unclaimed" if world.owner == null else "Founded by "+world.owner_name),11,ui.MUTED))
		row.add_child(ui.button("Visit  →",func(): ui.intent.emit("travel",{"world":world.name}); ui.close_modal()))
	body.add_child(HSeparator.new())
	body.add_child(ui.label("CREATE A WORLD",10,ui.ACCENT))
	var name_field := ui.input("MY_FIRST_WORLD")
	name_field.max_length = 20
	body.add_child(name_field)
	var biome := OptionButton.new()
	biome.custom_minimum_size.y = 36
	for value in ["Forest · cedar groves & green meadows","Desert · warm dunes & open sky","Snow · quiet pines & frozen peaks"]:
		biome.add_item(value)
	body.add_child(biome)
	body.add_child(ui.button("Create & enter world",func():
		ui.intent.emit("create_world",{"world":name_field.text,"biome":["forest","desert","snow"][biome.selected]}),true))
	body.add_child(ui.label("Place a World Core to claim your world and manage builder access.",11,ui.MUTED))

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
	var body := ui.begin_modal("Around the campfire","social",560,450)
	body.add_child(ui.label("Real explorers in your current world. Meet nearby to trade.",12,ui.MUTED))
	for p in state.players.values():
		if p.id == state.player_id: continue
		var row := HBoxContainer.new()
		body.add_child(row)
		var name_tag := ui.label(p.name,16)
		name_tag.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(name_tag)
		row.add_child(ui.button("Trade",func(): ui.intent.emit("trade_request",{"player":p.id})))
		row.add_child(ui.button("Block / unblock chat",func(): ui.intent.emit("ignore",{"player":p.id})))
	if state.players.size() <= 1:
		body.add_child(ui.label("You have this world to yourself.\nA second client can connect to the same server address.",14,ui.MUTED))

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
		ui.intent.emit("trade_offer",{"offer":offer})))
	var actions := HBoxContainer.new()
	body.add_child(actions)
	actions.add_child(ui.button("Clear offer",func(): ui.intent.emit("trade_offer",{"offer":{}})))
	var lock := ui.button("Lock my offer",func(): ui.intent.emit("trade_lock",{"revision":trade.revision}),true)
	lock.disabled = state.player_id in trade.locked
	actions.add_child(lock)
	var confirm := ui.button("Confirm exchange",func(): ui.intent.emit("trade_confirm",{"revision":trade.revision}),true)
	confirm.disabled = trade.locked.size() != 2 or state.player_id in trade.confirmed
	actions.add_child(confirm)
	body.add_child(ui.button("Cancel trade safely",func(): ui.intent.emit("trade_cancel",{})))

func open_settings() -> void:
	var body := ui.begin_modal("Around the campfire","settings",560,430)
	var toggle := CheckButton.new()
	toggle.text = "Interaction sounds"
	toggle.button_pressed = ui.sound
	toggle.toggled.connect(func(value): ui.sound = value; ui.audio_changed.emit(value))
	body.add_child(toggle)
	body.add_child(ui.button("Explorers & trading  [P]",func(): open_social()))
	body.add_child(ui.button("World permissions",func(): open_permissions()))
	body.add_child(ui.button("Controls & field guide  [H]",func(): open_help()))
	body.add_child(ui.button("Disconnect & save",func(): ui.signed_out.emit()))
	body.add_child(ui.label("Progress is saved on the server. Reconnect with your password\nor this device's saved session. Use WSS for remote servers.",12,ui.MUTED))

func open_help() -> void:
	var body := ui.begin_modal("An explorer's field guide","help",630,560)
	body.add_child(ui.label("A / D or ← / →       Move\nSpace / W / ↑         Jump\nHold left mouse       Mine a nearby tile\nRight mouse           Place the selected block or plant a seed\nE                             Interact with the tile under your cursor\n1–9 / 0                    Select hotbar slot\nI / C / M                  Backpack / crafting / worlds\nP / Enter                 Nearby explorers / world chat\nJ / Esc                    Field notes / close panel",14,ui.INK))
	body.add_child(HSeparator.new())
	body.add_child(ui.label("Find your footing",18,ui.ACCENT))
	body.add_child(ui.label("Gather cedar logs and fiber from the trees. Your cedar pick can mine\nstone. Place a workbench, then craft a stone pick to reach iron.\nPlant sungrain on earth; it ripens in 90 seconds, even while offline.\nPress E to harvest or open a chest. Create a world, then place your\nWorld Core to claim it. Invite builders, meet explorers, and trade.",13,ui.MUTED))
