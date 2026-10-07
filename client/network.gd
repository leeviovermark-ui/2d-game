extends Node
## Presentation sends intents only. All valuable state arrives from the authority.
signal packet(data: Dictionary)
signal status_changed(status: String)

var socket: WebSocketPeer
var was_open := false
var sequence := 0
var prefix := ""
var credentials := {}
var endpoint := "ws://127.0.0.1:8765"
var connected := false
var deadline := 0.0

func connect_server(url: String, auth: Dictionary) -> void:
	if socket:
		socket.close()
	endpoint = url
	credentials = auth
	socket = WebSocketPeer.new()
	socket.inbound_buffer_size = 2097152
	var err := socket.connect_to_url(url)
	was_open = false
	connected = false
	deadline = Time.get_ticks_msec() / 1000.0 + 10.0
	prefix = "%x_%x" % [Time.get_unix_time_from_system(), randi()]
	if err != OK:
		status_changed.emit("Could not open that server address.")
	else:
		status_changed.emit("Connecting to your world…")

func _process(_delta: float) -> void:
	if not socket:
		return
	socket.poll()
	var state := socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		if not was_open:
			was_open = true
			send(credentials.merged({"type": "auth"}))
		while socket.get_available_packet_count():
			var data = JSON.parse_string(socket.get_packet().get_string_from_utf8())
			if data is Dictionary:
				if data.get("type") == "welcome":
					connected = true
				packet.emit(data)
	elif state == WebSocketPeer.STATE_CLOSED:
		connected = false
		status_changed.emit("Disconnected. Your saved progress is safe. Sign in to reconnect.")
		socket = null
	elif not was_open and Time.get_ticks_msec() / 1000.0 > deadline:
		socket.close()
		status_changed.emit("Connection timed out. Check the server address.")

func send(data: Dictionary) -> void:
	if socket and socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		socket.send_text(JSON.stringify(data))

func action(kind: String, data: Dictionary = {}) -> void:
	# Godot JSON decoding represents numbers as floats. Restore protocol integer
	# fields explicitly; the server deliberately rejects fractional quantities.
	data = data.duplicate(true)
	for field in ["x","y","slot","from","to","count","revision"]:
		if data.has(field): data[field] = int(data[field])
	if data.has("offer"):
		for item in data.offer: data.offer[item] = int(data.offer[item])
	sequence += 1
	send(data.merged({"type": kind, "request": prefix + "_" + str(sequence)}, true))

func disconnect_server() -> void:
	if socket:
		socket.close(1000, "Explorer signed out")
	connected = false
