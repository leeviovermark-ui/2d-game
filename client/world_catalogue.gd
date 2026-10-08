extends RefCounted
## The catalogue updates in place, retaining filters and an unfinished creation form.
var ui: ForgeUI
var state: ForgeState
var search: LineEdit
var biome: OptionButton
var sort_order: OptionButton
var results: VBoxContainer
var summary: Label
var name_field: LineEdit
var creation_biome: OptionButton
var error_label: Label

func reset() -> void:
	search = null
	biome = null
	sort_order = null
	results = null
	summary = null
	name_field = null
	creation_biome = null
	error_label = null

func open() -> void:
	if ui.modal_kind == "worlds" and is_instance_valid(results):
		refresh()
		return
	var body := ui.begin_modal("World catalogue", "worlds", 840, 680)
	body.add_child(ui.label("Discover a home, visit your friends, or forge a fresh world.", 13, ui.MUTED))
	var filters := HBoxContainer.new()
	filters.add_theme_constant_override("separation", 10)
	body.add_child(filters)
	search = ui.input("Search worlds or their founders")
	search.name = "WorldSearch"
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.max_length = 32
	filters.add_child(search)
	biome = OptionButton.new()
	biome.name = "WorldBiome"
	for title in ["Every biome", "Forest", "Desert", "Snow"]: biome.add_item(title)
	filters.add_child(biome)
	sort_order = OptionButton.new()
	sort_order.name = "WorldSort"
	for title in ["Featured", "Newest first", "Most explorers", "A → Z", "Favorites"]: sort_order.add_item(title)
	filters.add_child(sort_order)
	search.text_changed.connect(func(_text): refresh())
	biome.item_selected.connect(func(_index): refresh())
	sort_order.item_selected.connect(func(_index): refresh())
	summary = ui.label("Connecting to the catalogue…", 11, ui.MUTED)
	body.add_child(summary)
	var scroll := ScrollContainer.new()
	scroll.name = "WorldResultsScroll"
	scroll.custom_minimum_size.y = 160
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	results = ui.column(scroll, 8)
	results.name = "WorldResults"
	results.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(HSeparator.new())
	body.add_child(ui.label("FORGE A NEW WORLD", 11, ui.ACCENT))
	var create_row := HBoxContainer.new()
	create_row.add_theme_constant_override("separation", 10)
	body.add_child(create_row)
	name_field = ui.input("MY_FIRST_WORLD")
	name_field.name = "NewWorldName"
	name_field.max_length = 20
	name_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	create_row.add_child(name_field)
	creation_biome = OptionButton.new()
	creation_biome.name = "NewWorldBiome"
	for title in ["Forest · green meadows", "Desert · golden dunes", "Snow · frosted peaks"]: creation_biome.add_item(title)
	create_row.add_child(creation_biome)
	create_row.add_child(ui.button("Create & enter", create_world, true))
	name_field.text_submitted.connect(func(_text): create_world())
	error_label = ui.label("New worlds appear in everyone's catalogue. Place a World Core to claim builder access.", 11, ui.MUTED)
	error_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(error_label)
	refresh()

func create_world() -> void:
	var world := name_field.text.strip_edges().to_upper()
	var pattern := RegEx.new()
	pattern.compile("^[A-Z][A-Z0-9_]{2,19}$")
	if not pattern.search(world):
		error_label.text = "Start with a letter, then use letters, numbers, or underscores. Names must be 3–20 characters."
		return
	error_label.text = "Creating " + world + "…"
	ui.intent.emit("create_world", {"world":world, "biome":["forest", "desert", "snow"][creation_biome.selected]})

func refresh() -> void:
	if ui.modal_kind != "worlds" or not is_instance_valid(results): return
	for child in results.get_children():
		results.remove_child(child)
		child.queue_free()
	var matching: Array = []
	var query := search.text.strip_edges().to_lower()
	var selected_biome: String = ["all", "forest", "desert", "snow"][biome.selected]
	for world in ui.directory:
		if selected_biome != "all" and world.biome != selected_biome: continue
		if sort_order.selected == 4 and not world.get("favorite", false): continue
		var searchable := str(world.name) + " " + str(world.get("owner_name", "")) + " " + str(world.get("title", ""))
		if not query.is_empty() and not searchable.to_lower().contains(query): continue
		matching.append(world)
	matching.sort_custom(func(a, b):
		match sort_order.selected:
			1:
				if float(a.get("created", 0)) != float(b.get("created", 0)): return float(a.get("created", 0)) > float(b.get("created", 0))
			2:
				if int(a.get("online", 0)) != int(b.get("online", 0)): return int(a.get("online", 0)) > int(b.get("online", 0))
			0:
				if bool(a.get("featured", false)) != bool(b.get("featured", false)): return bool(a.get("featured", false))
		return str(a.name).naturalnocasecmp_to(str(b.name)) < 0)
	summary.text = str(matching.size()) + " of " + str(ui.directory.size()) + " worlds  ·  You are in " + str(state.meta.get("name", ""))
	if matching.is_empty():
		results.add_child(ui.label("No worlds match these filters. Try another search or forge your own.", 13, ui.MUTED))
	for world in matching: add_world(world)
	ui.publish_modal_rects()

func add_world(world: Dictionary) -> void:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", ui.box(Color("20515a"), Color("44887f"), 12))
	results.add_child(panel)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	panel.add_child(row)
	var symbol := ui.label({"forest":"♣", "desert":"☀", "snow":"❄"}.get(world.biome, "◆"), 28, {"forest":Color("83edb1"), "desert":Color("ffd693"), "snow":Color("b9efff")}.get(world.biome, ui.ACCENT))
	symbol.custom_minimum_size.x = 34
	row.add_child(symbol)
	var description := ui.column(row, 4)
	description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	description.add_child(ui.label(str(world.name) + ("  ·  Your world" if world.get("owner") == state.player_id else ""), 17))
	var population := int(world.get("online", 0))
	var founder := "Unclaimed" if world.get("owner") == null else "Founded by " + str(world.get("owner_name", "explorer"))
	description.add_child(ui.label(str(world.biome).capitalize() + "  ·  " + founder + "  ·  " + str(population) + " online", 11, ui.MUTED))
	row.add_child(ui.button("★" if world.get("favorite", false) else "☆", func(): ui.intent.emit("social_action", {"action":"favorite", "world":world.name, "favorite":not world.get("favorite", false)})))
	var current: bool = str(world.name) == str(state.meta.get("name", ""))
	var visit := ui.button("Here" if current else "Visit  →", func(): ui.intent.emit("travel", {"world":world.name}), not current)
	visit.disabled = current
	row.add_child(visit)
