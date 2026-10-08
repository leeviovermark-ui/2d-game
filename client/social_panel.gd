extends RefCounted
## Friend lists, requests, direct conversations, and world invitations.
var ui: ForgeUI
var state: ForgeState
var data := {"friends":[], "incoming":[], "outgoing":[], "blocked":[]}
var owner := ""
var tab := "friends"
var search: LineEdit
var content: VBoxContainer
var tabs: HBoxContainer
var request_name: LineEdit
var peer_id := ""
var peer_name := ""
var message_input: LineEdit
var conversation: RichTextLabel
var threads := {}
var unread := {}
var invitation := {}
var invite_row: HBoxContainer

func scope_account() -> void:
	if owner == state.player_id: return
	reset()
	owner = state.player_id

func reset() -> void:
	owner = ""
	tab = "friends"
	data = {"friends":[], "incoming":[], "outgoing":[], "blocked":[]}
	threads.clear()
	unread.clear()
	peer_id = ""
	peer_name = ""
	invitation.clear()
	for field in [search, request_name]:
		if is_instance_valid(field):
			field.set_block_signals(true)
			field.clear()
			field.set_block_signals(false)
	message_input = null
	conversation = null

func open() -> void:
	scope_account()
	if ui.modal_kind == "social" and is_instance_valid(content):
		refresh(data)
		return
	var body := ui.begin_modal("Friends & explorers", "social", 800, 660)
	body.add_child(ui.label("Keep in touch across worlds. Meet nearby for a secure trade.", 13, ui.MUTED))
	tabs = HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 8)
	body.add_child(tabs)
	for pair in [["friends", "Friends"], ["requests", "Requests"], ["nearby", "Nearby"], ["messages", "Messages"], ["blocked", "Blocked"]]:
		var key: String = pair[0]
		var button := ui.button(pair[1], func(): select_tab(key))
		button.name = key.capitalize() + "Tab"
		tabs.add_child(button)
	var request_row := HBoxContainer.new()
	request_row.add_theme_constant_override("separation", 8)
	body.add_child(request_row)
	request_name = ui.input("Add a friend by explorer name")
	request_name.name = "FriendName"
	request_name.max_length = 20
	request_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	request_row.add_child(request_name)
	request_row.add_child(ui.button("Send request", send_request, true))
	request_name.text_submitted.connect(func(_text): send_request())
	search = ui.input("Filter explorers")
	search.name = "FriendSearch"
	body.add_child(search)
	search.text_changed.connect(func(_text): render())
	invite_row = HBoxContainer.new()
	invite_row.add_theme_constant_override("separation", 8)
	body.add_child(invite_row)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.y = 160
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	content = ui.column(scroll, 9)
	content.name = "SocialResults"
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(ui.label("Friends and blocks are saved on this server. Direct conversations on this device last until you sign out.", 10, ui.MUTED))
	render()
	ui.intent.emit("social_open", {})

func send_request() -> void:
	var target := request_name.text.strip_edges()
	if target.length() < 3:
		ui.notify("Enter an explorer's name to send a friend request.")
		return
	ui.intent.emit("social_action", {"action":"request", "target":target})
	request_name.clear()

func select_tab(value: String) -> void:
	tab = value
	render()

func refresh(payload: Dictionary) -> void:
	scope_account()
	data = payload
	if ui.modal_kind == "social" and is_instance_valid(content): render()

func clear_children(node: Node) -> void:
	for child in node.get_children():
		node.remove_child(child)
		child.queue_free()

func render() -> void:
	if ui.modal_kind != "social" or not is_instance_valid(content): return
	# Message controls stay alive while friends come online or a catalogue updates.
	if tab == "messages" and is_instance_valid(message_input):
		update_conversation()
		render_invite()
		ui.publish_modal_rects()
		return
	clear_children(content)
	message_input = null
	conversation = null
	search.visible = tab != "messages"
	for button in tabs.get_children():
		button.text = button.name.trim_suffix("Tab")
		if button.name == "RequestsTab": button.text += " (" + str(data.get("incoming", []).size()) + ")"
		if button.name == "MessagesTab" and not unread.is_empty(): button.text += " •"
		button.disabled = button.name.to_lower().trim_suffix("tab") == tab
	render_invite()
	match tab:
		"messages": render_messages()
		"requests": render_requests()
		"nearby": render_nearby()
		"blocked": render_blocked()
		_: render_friends()
	ui.publish_modal_rects()

func matches(explorer: Dictionary) -> bool:
	var query := search.text.strip_edges().to_lower()
	return query.is_empty() or str(explorer.name).to_lower().contains(query)

func explorer_row(explorer: Dictionary) -> HBoxContainer:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", ui.box(Color("20515a"), Color("44887f"), 10))
	content.add_child(panel)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	panel.add_child(row)
	var descriptions := ui.column(row, 4)
	descriptions.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	descriptions.add_child(ui.label(str(explorer.name), 16))
	var online: bool = explorer.get("online", false)
	descriptions.add_child(ui.label("● " + str(explorer.get("world", "Exploring")) if online else "○ Offline", 11, Color("8df2bc") if online else ui.MUTED))
	return row

func render_friends() -> void:
	var count := 0
	for friend in data.get("friends", []):
		if not matches(friend): continue
		count += 1
		var row := explorer_row(friend)
		row.add_child(ui.button("Message" + (" •" if unread.has(friend.id) else ""), func(): open_conversation(friend.id, friend.name)))
		var join := ui.button("Join", func(): ui.intent.emit("social_action", {"action":"join", "target":friend.id}), true)
		join.disabled = not friend.get("online", false)
		row.add_child(join)
		var invite := ui.button("Invite here", func(): ui.intent.emit("social_action", {"action":"invite", "target":friend.id}))
		invite.disabled = not friend.get("online", false)
		row.add_child(invite)
		row.add_child(ui.button("Remove", func(): confirm_remove(friend)))
	if count == 0: content.add_child(ui.label("No friends match yet. Send an explorer a request above.\nAccepted friends appear here even when they are offline.", 13, ui.MUTED))

func confirm_remove(friend: Dictionary) -> void:
	var confirm := ConfirmationDialog.new()
	confirm.title = "Remove friend"
	confirm.dialog_text = "Remove " + str(friend.name) + " from your friends?"
	ui.root.add_child(confirm)
	confirm.confirmed.connect(func(): ui.intent.emit("social_action", {"action":"remove", "target":friend.id}); confirm.queue_free())
	confirm.canceled.connect(func(): confirm.queue_free())
	confirm.popup_centered(Vector2i(370, 160))

func render_requests() -> void:
	content.add_child(ui.label("INCOMING REQUESTS", 11, ui.ACCENT))
	var incoming_count := 0
	for explorer in data.get("incoming", []):
		if not matches(explorer): continue
		incoming_count += 1
		var row := explorer_row(explorer)
		row.add_child(ui.button("Accept", func(): ui.intent.emit("social_action", {"action":"accept", "target":explorer.id}), true))
		row.add_child(ui.button("Decline", func(): ui.intent.emit("social_action", {"action":"decline", "target":explorer.id})))
	if incoming_count == 0: content.add_child(ui.label("No pending incoming requests.", 13, ui.MUTED))
	content.add_child(HSeparator.new())
	content.add_child(ui.label("REQUESTS YOU SENT", 11, ui.ACCENT))
	var outgoing_count := 0
	for explorer in data.get("outgoing", []):
		if not matches(explorer): continue
		outgoing_count += 1
		var row := explorer_row(explorer)
		row.add_child(ui.label("Awaiting reply", 11, ui.MUTED))
	if outgoing_count == 0: content.add_child(ui.label("No outgoing requests.", 13, ui.MUTED))

func render_nearby() -> void:
	var count := 0
	for explorer in state.players.values():
		if explorer.id == state.player_id or not matches(explorer): continue
		count += 1
		var row := explorer_row(explorer.merged({"online":true, "world":state.meta.get("name", "")}))
		row.add_child(ui.button("Trade", func(): ui.intent.emit("trade_request", {"player":explorer.id}), true))
		row.add_child(ui.button("Add friend", func(): ui.intent.emit("social_action", {"action":"request", "target":explorer.id})))
		row.add_child(ui.button("Block chat", func(): ui.intent.emit("social_action", {"action":"block", "target":explorer.id})))
	if count == 0: content.add_child(ui.label("You have this world to yourself.\nInvite an online friend, or discover a busier world in the catalogue.", 13, ui.MUTED))

func render_blocked() -> void:
	var count := 0
	for explorer in data.get("blocked", []):
		if not matches(explorer): continue
		count += 1
		var row := explorer_row(explorer)
		row.add_child(ui.button("Unblock", func(): ui.intent.emit("social_action", {"action":"unblock", "target":explorer.id}), true))
	if count == 0: content.add_child(ui.label("Your block list is empty. Block an explorer from the Nearby tab.", 13, ui.MUTED))

func open_conversation(id: String, name: String) -> void:
	peer_id = id
	peer_name = name
	unread.erase(id)
	tab = "messages"
	message_input = null
	render()

func render_messages() -> void:
	var choices := HBoxContainer.new()
	choices.add_theme_constant_override("separation", 8)
	content.add_child(choices)
	var recipients := OptionButton.new()
	recipients.name = "MessageRecipient"
	recipients.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choices.add_child(recipients)
	var peers: Array = []
	for friend in data.get("friends", []): peers.append({"id":friend.id, "name":friend.name})
	if not peer_id.is_empty() and not peers.any(func(friend): return friend.id == peer_id): peers.append({"id":peer_id, "name":peer_name})
	for i in range(peers.size()):
		recipients.add_item(str(peers[i].name))
		if peers[i].id == peer_id: recipients.select(i)
	if peer_id.is_empty() and not peers.is_empty():
		peer_id = peers[0].id
		peer_name = peers[0].name
	recipients.item_selected.connect(func(index): open_conversation(peers[index].id, peers[index].name))
	choices.add_child(ui.button("Invite to my world", func():
		if not peer_id.is_empty(): ui.intent.emit("social_action", {"action":"invite", "target":peer_id})))
	conversation = RichTextLabel.new()
	conversation.name = "DirectConversation"
	conversation.custom_minimum_size.y = 210
	conversation.fit_content = false
	conversation.scroll_following = true
	conversation.bbcode_enabled = false
	conversation.add_theme_stylebox_override("normal", ui.box(Color("12373f"), Color("397b7a"), 12))
	content.add_child(conversation)
	var send_row := HBoxContainer.new()
	content.add_child(send_row)
	message_input = ui.input("Write a private message…")
	message_input.name = "DirectMessageInput"
	message_input.max_length = 180
	message_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	message_input.editable = not peer_id.is_empty()
	send_row.add_child(message_input)
	message_input.text_submitted.connect(func(_text): send_message())
	var send := ui.button("Send", send_message, true)
	send.disabled = peer_id.is_empty()
	send_row.add_child(send)
	content.add_child(ui.label("Direct messages require an accepted friend who is online. Blocks prevent contact.", 11, ui.MUTED))
	update_conversation()

func send_message() -> void:
	if peer_id.is_empty() or not is_instance_valid(message_input): return
	var text := message_input.text.strip_edges()
	if text.is_empty(): return
	ui.intent.emit("social_action", {"action":"message", "target":peer_id, "text":text})

func update_conversation() -> void:
	if not is_instance_valid(conversation): return
	unread.erase(peer_id)
	conversation.clear()
	if peer_id.is_empty():
		conversation.add_text("Accept a friend request to start a conversation.")
		return
	conversation.add_text("CONVERSATION WITH " + peer_name.to_upper() + "\n\n")
	for message in threads.get(peer_id, []):
		conversation.add_text(("You" if message.get("sent", false) else str(message.name)) + "  ›  " + str(message.text) + "\n")

func receive_message(message: Dictionary) -> void:
	scope_account()
	var peer: String = str(message.get("peer_id", message.get("id", "")))
	var thread: Array = threads.get(peer, [])
	thread.append(message.duplicate(true))
	if thread.size() > 60: thread.pop_front()
	threads[peer] = thread
	if message.get("sent", false) and peer_id == peer and is_instance_valid(message_input) and message_input.text.strip_edges() == str(message.text):
		message_input.clear()
	if not message.get("sent", false):
		if ui.modal_kind != "social" or tab != "messages" or peer_id != peer:
			unread[peer] = true
			ui.notify(str(message.name) + " sent you a private message. Press P to reply.")
	if ui.modal_kind == "social" and tab == "messages" and peer_id == peer: update_conversation()

func receive_invite(payload: Dictionary) -> void:
	scope_account()
	invitation = payload.duplicate(true)
	ui.notify(str(payload.name) + " invited you to " + str(payload.world) + ". Press P to visit.")
	if ui.modal_kind == "social" and is_instance_valid(invite_row): render_invite()

func render_invite() -> void:
	if not is_instance_valid(invite_row): return
	clear_children(invite_row)
	if invitation.is_empty() or float(invitation.get("expires", 0)) < state.now():
		invitation.clear()
		invite_row.visible = false
		return
	invite_row.visible = true
	var label := ui.label(str(invitation.name) + " invited you to " + str(invitation.world), 12, ui.ACCENT)
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	invite_row.add_child(label)
	invite_row.add_child(ui.button("Visit world", func():
		ui.intent.emit("travel", {"world":invitation.world})
		invitation.clear()
		render_invite(), true))
	invite_row.add_child(ui.button("Dismiss", func(): invitation.clear(); render_invite()))
