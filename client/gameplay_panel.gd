extends RefCounted
## Progression, wearable gear, expressive social actions, and persistent machines.
var ui: ForgeUI
var state: ForgeState
var art: ForgeArt
var progression := {"quests":[], "points":0, "level":1}
var owner := ""
var tab := "quests"
var content: VBoxContainer
var heading: Label
var machine := {}
var machine_choices: OptionButton
var machine_ids: Array = []
var machine_amount: SpinBox
var machine_description: Label
var machine_start: Button
var job_list: VBoxContainer
var job_labels := {}

func scope_account() -> void:
	if owner == state.player_id: return
	reset()
	owner = state.player_id

func reset() -> void:
	owner = ""
	tab = "quests"
	progression = {"quests":[], "points":0, "level":1}
	machine.clear()
	machine_ids.clear()
	job_labels.clear()
	content = null
	heading = null
	machine_choices = null
	machine_amount = null
	machine_description = null
	machine_start = null
	job_list = null

func open(payload: Dictionary = {}) -> void:
	scope_account()
	if not payload.is_empty(): progression = payload
	var body := ui.begin_modal("Explorer journal", "gameplay", 810, 650)
	heading = ui.label("", 13, ui.ACCENT)
	body.add_child(heading)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 10)
	body.add_child(tabs)
	for pair in [["quests", "Goals & rewards"], ["equipment", "Equipment & food"], ["emotes", "Expressions"], ["guide", "New discoveries"]]:
		var key: String = pair[0]
		tabs.add_child(ui.button(pair[1], func(): tab = key; render()))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	content = ui.column(scroll, 12)
	content.name = "JournalContent"
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	render()
	ui.intent.emit("progression", {})

func refresh(payload: Dictionary) -> void:
	scope_account()
	progression = payload
	if ui.modal_kind == "gameplay" and is_instance_valid(content): render()

func clear_children(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func render() -> void:
	if ui.modal_kind != "gameplay" or not is_instance_valid(content): return
	clear_children(content)
	heading.text = "LEVEL " + str(int(progression.get("level", 1))) + "  ·  " + str(int(progression.get("points", 0))) + " EXPLORER POINTS"
	match tab:
		"equipment": render_equipment()
		"emotes": render_emotes()
		"guide": render_guide()
		_: render_quests()
	ui.publish_modal_rects()

func item_names(items: Dictionary) -> String:
	var parts: Array[String] = []
	for id in items:
		parts.append(str(state.items.get(id, {}).get("name", id)) + " ×" + str(int(items[id])))
	return ", ".join(parts)

func render_quests() -> void:
	content.add_child(ui.label("Your goals follow you across worlds. Rewards are granted by the server once.", 12, ui.MUTED))
	if progression.get("quests", []).is_empty():
		content.add_child(ui.label("Loading your explorer goals…", 14, ui.MUTED))
	for quest in progression.get("quests", []):
		var panel := PanelContainer.new()
		panel.add_theme_stylebox_override("panel", ui.box(Color("20515a"), Color("44887f"), 12))
		content.add_child(panel)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 16)
		panel.add_child(row)
		var description := ui.column(row, 5)
		description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		description.add_child(ui.label(str(quest.title), 17))
		var details := ui.label(str(quest.description), 12, ui.MUTED)
		details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		description.add_child(details)
		var progress := ProgressBar.new()
		progress.max_value = maxf(1, float(quest.target))
		progress.value = float(quest.current)
		progress.show_percentage = false
		progress.custom_minimum_size.y = 8
		progress.add_theme_stylebox_override("background", ui.box(Color("12373f"),Color("12373f"),0))
		progress.add_theme_stylebox_override("fill", ui.box(Color("75e7b5"),Color("75e7b5"),0))
		description.add_child(progress)
		var rewards := ui.label(str(int(quest.current)) + "/" + str(int(quest.target)) + "  ·  " + str(int(quest.get("points", 0))) + " points  ·  " + item_names(quest.get("reward", {})), 11, ui.ACCENT)
		rewards.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		description.add_child(rewards)
		var claimed: bool = quest.status == "claimed"
		var claim := ui.button("Claimed ✓" if claimed else "Claim reward", func(): ui.intent.emit("claim_quest", {"quest":quest.id}), quest.status == "ready")
		claim.disabled = quest.status != "ready"
		row.add_child(claim)

func render_equipment() -> void:
	var local_player: Dictionary = state.players.get(state.player_id, {})
	var appearance: Dictionary = local_player.get("appearance", {})
	content.add_child(ui.label("YOUR WARDROBE", 11, ui.ACCENT))
	for slot in ["hat", "back", "outfit"]:
		var row := HBoxContainer.new()
		content.add_child(row)
		var id: String = str(appearance.get(slot, ""))
		var description := ui.label(str(slot).capitalize() + "  ·  " + (str(state.items.get(id, {}).get("name", id)) if not id.is_empty() else "Nothing equipped"), 13)
		description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(description)
		var remove := ui.button("Take off", func(): ui.intent.emit("equip", {"slot":-1, "equipment":slot}))
		remove.disabled = id.is_empty()
		row.add_child(remove)
	content.add_child(HSeparator.new())
	content.add_child(ui.label("READY IN YOUR BACKPACK", 11, ui.ACCENT))
	var count := 0
	for index in range(state.inventory.size()):
		var stack = state.inventory[index]
		if not stack: continue
		var definition: Dictionary = state.items[stack.id]
		var wearable: bool = definition.has("equipment") or definition.has("wear") or definition.category in ["apparel", "equipment", "cosmetic", "outfit"]
		var food: bool = definition.category == "food" or definition.has("energy")
		if not wearable and not food: continue
		count += 1
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		content.add_child(row)
		var icon := TextureRect.new()
		icon.texture = art.icon(stack.id, definition)
		icon.custom_minimum_size = Vector2(42, 42)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		row.add_child(icon)
		var description := ui.column(row, 3)
		description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		description.add_child(ui.label(str(definition.name) + "  ×" + str(int(stack.n)), 15))
		var details := ui.label(str(definition.get("description", "")), 11, ui.MUTED)
		details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		description.add_child(details)
		row.add_child(ui.button("Wear" if wearable else "Eat", func(): ui.intent.emit("equip" if wearable else "use_item", {"slot":index}), true))
	if count == 0: content.add_child(ui.label("Craft an outfit or some food to see it here. Eating restores sprint energy.", 13, ui.MUTED))

func render_emotes() -> void:
	content.add_child(ui.label("Make the world feel a little more human. Nearby explorers see your expression.", 13, ui.MUTED))
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 12)
	content.add_child(grid)
	for pair in [["wave", "Wave hello"], ["cheer", "✦  Cheer"], ["heart", "♥  Heart"], ["dance", "♫  Dance"], ["sit", "Sit & relax"]]:
		var key: String = pair[0]
		var button := ui.button(pair[1], func(): ui.intent.emit("emote", {"emote":key}), true)
		button.custom_minimum_size = Vector2(210, 62)
		grid.add_child(button)
	content.add_child(ui.label("Expressions are brief and cannot move you through blocks or grant items.", 11, ui.MUTED))

func render_guide() -> void:
	for pair in [
		["Run toward your next discovery", "Hold Shift while moving to sprint. Energy recovers while resting; prepared food restores it faster."],
		["Grow a colorful garden", "Plant new seeds on earth. Crops keep growing while you are away. Use E to harvest mature plants."],
		["Let your workshop work", "Place a furnace, kitchen, or other processing station. Press E to queue a recipe, then return to collect the finished result."],
		["Fish by the water", "Craft and select a fishing rod. Point at nearby water and press G to cast. Your catch comes from the server."],
		["Connect your worlds", "Craft a portal and place it in a world you can build in. Press E to configure a destination; later interactions travel to that world."],
		["Build with friends", "Press P to send friend requests, private messages, and world invitations. The world catalogue shows who is online and remembers your favorites."],
		["Make yourself at home", "Craft furniture, lanterns, architectural blocks, wearable gear, and garden decorations. Drag useful items into your hotbar."]
	]:
		content.add_child(ui.label(pair[0], 17, ui.ACCENT))
		var description := ui.label(pair[1], 13, ui.MUTED)
		description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		content.add_child(description)

func open_machine(payload: Dictionary) -> void:
	if ui.modal_kind == "machine" and machine.get("world") == payload.get("world") and machine.get("x") == payload.x and machine.get("y") == payload.y and is_instance_valid(job_list):
		refresh_machine(payload)
		return
	machine = payload.duplicate(true)
	var body := ui.begin_modal(str(payload.name), "machine", 820, 650)
	body.add_child(ui.label("Queue a batch and let time do the work. Jobs persist while you explore or sign out.", 12, ui.MUTED))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	body.add_child(row)
	machine_choices = OptionButton.new()
	machine_choices.name = "MachineRecipe"
	machine_choices.custom_minimum_size.y = 40
	machine_choices.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(machine_choices)
	machine_ids.clear()
	for recipe in payload.get("recipes", []):
		machine_ids.append(recipe.id)
		machine_choices.add_item(str(state.items[recipe.output].name))
	row.add_child(ui.label("Batches", 11, ui.MUTED))
	machine_amount = SpinBox.new()
	machine_amount.name = "MachineBatches"
	machine_amount.min_value = 1
	machine_amount.max_value = 20
	machine_amount.value = 1
	row.add_child(machine_amount)
	machine_start = ui.button("Start batch", func():
		if not machine_ids.is_empty(): ui.intent.emit("machine_start", {"x":int(machine.x), "y":int(machine.y), "recipe":machine_ids[machine_choices.selected], "count":int(machine_amount.value)}), true)
	row.add_child(machine_start)
	machine_description = ui.label("", 12, ui.MUTED)
	machine_description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(machine_description)
	machine_choices.item_selected.connect(func(_index): update_machine_recipe())
	machine_amount.value_changed.connect(func(_value): update_machine_recipe())
	body.add_child(HSeparator.new())
	body.add_child(ui.label("CURRENT JOBS", 11, ui.ACCENT))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	job_list = ui.column(scroll, 9)
	job_list.name = "MachineJobs"
	job_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(ui.button("Refresh station", func(): ui.intent.emit("machine_open", {"x":int(machine.x), "y":int(machine.y)})))
	var timer := Timer.new()
	timer.wait_time = .5
	timer.timeout.connect(update_job_times)
	ui.modal.add_child(timer)
	timer.start()
	refresh_machine(payload)

func refresh_machine(payload: Dictionary) -> void:
	machine = payload.duplicate(true)
	if ui.modal_kind != "machine" or not is_instance_valid(job_list): return
	clear_children(job_list)
	job_labels.clear()
	for job in machine.get("jobs", []):
		var panel := PanelContainer.new()
		panel.add_theme_stylebox_override("panel", ui.box(Color("20515a"), Color("44887f"), 12))
		job_list.add_child(panel)
		var row := HBoxContainer.new()
		panel.add_child(row)
		var description := ui.column(row, 4)
		description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		description.add_child(ui.label(str(state.items[job.output].name) + "  ×" + str(int(job.amount)), 16))
		description.add_child(ui.label("Queued by " + str(job.name), 11, ui.MUTED))
		var status := ui.label("", 11, ui.ACCENT)
		description.add_child(status)
		var collect := ui.button("Collect", func(): ui.intent.emit("machine_collect", {"x":int(machine.x), "y":int(machine.y), "job":job.id}), true)
		row.add_child(collect)
		job_labels[job.id] = {"label":status, "button":collect}
	if machine.get("jobs", []).is_empty(): job_list.add_child(ui.label("No jobs yet. Choose a recipe to begin.", 13, ui.MUTED))
	update_machine_recipe()
	update_job_times()
	ui.publish_modal_rects()

func update_machine_recipe() -> void:
	if ui.modal_kind != "machine" or not is_instance_valid(machine_description): return
	if machine_ids.is_empty():
		machine_description.text = "This station has no available recipes."
		machine_start.disabled = true
		return
	var id: String = machine_ids[machine_choices.selected]
	for recipe in machine.get("recipes", []):
		if recipe.id != id: continue
		var quantity := int(machine_amount.value)
		var ingredients := ""
		var enough := true
		for item in recipe.ingredients:
			var needed := int(recipe.ingredients[item]) * quantity
			var owned: int = state.owned(item)
			ingredients += str(state.items[item].name) + " " + str(owned) + "/" + str(needed) + "   "
			if owned < needed: enough = false
		var duration := int(recipe.get("duration", 0)) * quantity
		machine_description.text = ingredients + "\nMakes " + str(int(recipe.amount) * quantity) + (" instantly." if duration == 0 else " in " + str(duration) + " seconds.")
		machine_start.text = "Craft now" if duration == 0 else "Start batch"
		machine_start.disabled = not enough
		return

func update_job_times() -> void:
	if ui.modal_kind != "machine" or not is_instance_valid(job_list): return
	for job in machine.get("jobs", []):
		if not job_labels.has(job.id): continue
		var remaining := maxf(0, float(job.ready) - state.now())
		var mine: bool = job.owner == state.player_id
		job_labels[job.id].label.text = "Ready to collect" if remaining <= 0 else "Finishing in " + str(ceili(remaining)) + "s"
		job_labels[job.id].button.disabled = remaining > 0 or not mine
		if not mine: job_labels[job.id].button.text = "Owner collects"

func open_portal(payload: Dictionary) -> void:
	var body := ui.begin_modal("Portal destination", "portal", 620, 420)
	body.add_child(ui.label("Connect this portal to an existing world. Only builders can configure it.", 13, ui.MUTED))
	var choices := OptionButton.new()
	choices.name = "PortalDestination"
	choices.custom_minimum_size.y = 42
	body.add_child(choices)
	var worlds: Array = payload.get("worlds", ui.directory)
	var names: Array = []
	for world in worlds:
		if world.name == state.meta.get("name", ""): continue
		names.append(world.name)
		choices.add_item(str(world.name))
		if world.name == payload.get("destination", ""): choices.select(names.size() - 1)
	var configure := ui.button("Set destination", func():
		if not names.is_empty(): ui.intent.emit("portal_config", {"x":int(payload.x), "y":int(payload.y), "world":names[choices.selected]}), true)
	configure.disabled = names.is_empty()
	body.add_child(configure)
	body.add_child(ui.label("Create another world in the catalogue first." if names.is_empty() else "After configuration, press E at the portal to travel.", 12, ui.MUTED))
