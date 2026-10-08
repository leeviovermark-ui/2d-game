extends SceneTree
## Actual Godot controls verify async refreshes do not erase a player's work.
var checks := 0
var intents: Array = []

func _initialize() -> void:
	call_deferred("run_checks")

func expect(value: bool, message: String) -> void:
	if not value:
		push_error(message)
		quit(1)
		return
	checks += 1

func run_checks() -> void:
	var state := ForgeState.new()
	state.player_id = "aster"
	state.player_name = "Aster"
	state.meta = {"name":"NEXUS", "biome":"forest", "owner":null}
	state.inventory.resize(30)
	state.inventory.fill(null)
	state.inventory[0] = {"id":"wood", "n":99}
	state.players = {"aster":{"id":"aster", "name":"Aster", "x":10, "y":19.5, "vx":0, "vy":0, "appearance":{}}, "briar":{"id":"briar", "name":"Briar", "x":11, "y":19.5, "vx":0, "vy":0}}
	state.display_positions = {"aster":Vector2(10,19.5)}
	state.tiles[Vector2i(10,20)] = "bench"
	var ui := ForgeUI.new()
	ui.state = state
	ui.art = ForgeArt.new()
	get_root().add_child(ui)
	await process_frame
	ui.show_game(true)
	ui.intent.connect(func(kind, payload): intents.append({"kind":kind,"data":payload}))
	ui.open_craft()
	await process_frame
	ui.panels.craft_search.text = "Cedar planks"
	ui.panels.craft_search.grab_focus()
	ui.panels.craft_amount.value = 2
	ui.refresh_craft()
	expect(ui.panels.craft_search.text == "Cedar planks", "Craft refresh erased recipe search.")
	expect(ui.panels.craft_search.has_focus(), "Craft refresh stole keyboard focus.")
	expect(int(ui.panels.craft_amount.value) == 2, "Craft refresh erased batch quantity.")
	for recipe in state.recipes:
		if recipe.output == "planks":
			ui.panels.craft_rows[recipe.id].button.pressed.emit()
			break
	expect(intents.back().kind == "craft" and typeof(intents.back().data.count) == TYPE_INT and intents.back().data.count == 2, "Craft button did not send integer batch quantity.")
	ui.directory = [
		{"name":"BUILD_HOME", "biome":"forest", "owner":null,"owner_name":"","online":2,"created":1,"favorite":false,"featured":false},
		{"name":"SNOW_HOME", "biome":"snow", "owner":null,"owner_name":"","online":1,"created":2,"favorite":false,"featured":false}
	]
	ui.open_worlds()
	await process_frame
	var catalogue = ui.panels.catalogue
	catalogue.search.text = "BUILD"
	catalogue.name_field.text = "UNFINISHED_WORLD"
	ui.directory.append({"name":"BUILD_NEW", "biome":"forest", "owner":null,"owner_name":"","online":0,"created":3,"favorite":false,"featured":false})
	ui.render_worlds()
	expect(catalogue.search.text == "BUILD" and catalogue.name_field.text == "UNFINISHED_WORLD", "Catalogue update erased filters or world creation draft.")
	expect(catalogue.results.get_child_count() == 2, "New worlds did not appear in the filtered catalogue.")
	catalogue.name_field.text = "! invalid !"
	var before := intents.size()
	catalogue.create_world()
	expect(intents.size() == before, "Invalid world name was sent to the server.")
	for invalid in ["1_FIRST_WORLD", "_FIRST_WORLD"]:
		catalogue.name_field.text = invalid
		catalogue.create_world()
		expect(intents.size() == before, "A world name without an initial letter was sent to the server.")
	ui.refresh_social({"friends":[{"id":"briar","name":"Briar","online":true,"world":"NEXUS"}], "incoming":[{"id":"cora","name":"Cora","online":false,"world":null}], "outgoing":[], "blocked":[]})
	ui.open_social()
	await process_frame
	var social = ui.panels.social_panel
	expect(social.content.get_child_count() == 1 and social.content.get_child(0) is PanelContainer, "An empty friend search hid accepted friends.")
	social.select_tab("nearby")
	expect(social.content.get_child_count() == 1 and social.content.get_child(0) is PanelContainer, "An empty nearby search hid other online explorers.")
	social.select_tab("friends")
	social.request_name.text = "Cora"
	social.send_request()
	expect(intents.back().kind == "social_action" and intents.back().data.action == "request" and intents.back().data.target == "Cora", "Friend request button sent an incorrect action.")
	social.open_conversation("briar", "Briar")
	await process_frame
	social.message_input.text = "My unfinished reply"
	social.message_input.grab_focus()
	ui.refresh_social(social.data)
	expect(social.message_input.text == "My unfinished reply" and social.message_input.has_focus(), "Presence refresh erased a direct message draft or stole focus.")
	ui.receive_private_message({"id":"briar","name":"Briar","peer_id":"briar","peer_name":"Briar","text":"[b]Hello[/b]","sent":false})
	expect(social.conversation.get_parsed_text().contains("[b]Hello[/b]") and not social.conversation.bbcode_enabled, "Direct message markup was interpreted instead of shown as text.")
	social.send_message()
	expect(social.message_input.text == "My unfinished reply", "An unconfirmed or rejected direct message erased the draft.")
	ui.receive_private_message({"id":"aster","name":"Aster","peer_id":"briar","peer_name":"Briar","text":"My unfinished reply","sent":true})
	expect(social.message_input.text.is_empty(), "An authoritative direct-message confirmation did not clear the matching sent draft.")
	state.player_id = "different_account"
	ui.refresh_social({"friends":[], "incoming":[], "outgoing":[], "blocked":[]})
	expect(social.threads.is_empty(), "A new account could read the previous account's private conversations.")
	expect(social.peer_id.is_empty() and social.tab == "friends" and social.message_input == null, "A new account inherited the previous account's message draft or recipient.")
	state.player_id = "aster"
	var recipe: Dictionary = state.recipes[0].duplicate(true)
	recipe.duration = 3
	ui.open_machine({"world":"NEXUS","x":10,"y":20,"station":"bench","name":"Test workshop","recipes":[recipe],"jobs":[{"id":"job_1","owner":"aster","name":"Aster","recipe":recipe.id,"output":recipe.output,"amount":1,"ready":state.now()-1,"complete":true}]})
	await process_frame
	var gameplay = ui.panels.gameplay_panel
	expect(not gameplay.job_labels.job_1.button.disabled, "Ready machine output could not be collected by its owner.")
	gameplay.job_labels.job_1.button.pressed.emit()
	expect(intents.back().kind == "machine_collect" and intents.back().data.job == "job_1", "Machine collect control sent an incorrect job ID.")
	gameplay.machine_amount.value = 3
	ui.refresh_machine(gameplay.machine)
	expect(int(gameplay.machine_amount.value) == 3, "Machine update erased batch quantity.")
	ui.open_admin({"items":[state.items.wood], "players":[{"id":"aster","name":"Aster","admin":true,"online":true,"world":"NEXUS"}, {"id":"briar","name":"Briar","admin":false,"online":true,"world":"NEXUS"}]})
	await process_frame
	var admin = ui.panels.admin_panel
	admin.pending_action = {"action":"ban", "target":"briar", "reason":"Private moderation draft"}
	admin.selected_player = "briar"
	admin.search_players = "Briar"
	social.threads = {"briar":[{"text":"A private conversation"}]}
	gameplay.progression = {"quests":[], "points":60, "level":2}
	ui.show_game(false)
	await process_frame
	expect(social.threads.is_empty() and social.peer_id.is_empty() and social.tab == "friends", "Disconnect did not clear private conversations and selections.")
	expect(gameplay.machine.is_empty() and gameplay.job_labels.is_empty() and gameplay.progression.points == 0, "Disconnect retained the previous account's machine jobs or explorer progress.")
	expect(admin.snapshot.is_empty() and admin.pending_action.is_empty() and admin.selected_player.is_empty() and admin.search_players.is_empty(), "Disconnect retained privileged administration state or moderation drafts.")
	expect(ui.directory.is_empty() and ui.panels.craft_rows.is_empty() and ui.modal_kind.is_empty(), "Disconnect retained catalogue favorites, crafting controls, or an open modal.")
	state.player_id = "cora"
	state.player_name = "Cora"
	ui.show_game(true)
	ui.open_worlds()
	await process_frame
	expect(catalogue.name_field.text.is_empty() and catalogue.search.text.is_empty(), "A new account inherited the previous account's world creation draft or catalogue search.")
	await process_frame
	await process_frame
	ui.queue_free()
	await process_frame
	await process_frame
	print(JSON.stringify({"panel_checks":checks,"status":"passed"}))
	quit(0)
