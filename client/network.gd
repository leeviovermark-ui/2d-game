extends Node
## Intents only; passwords are cleared after authentication is sent.
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
var resume_token := ""
var intentional_close := false
var retry_count := 0
var retry_at := 0.0
var ping_at := 0.0

func connect_server(url: String, auth: Dictionary, reconnect := false) -> void:
	if socket: socket.close()
	endpoint = url
	credentials = auth.duplicate(true)
	if not reconnect:
		retry_count = 0
		resume_token = str(auth.get("token", ""))
	retry_at = 0.0
	intentional_close = false
	socket = WebSocketPeer.new()
	socket.inbound_buffer_size = 4194304
	socket.outbound_buffer_size = 262144
	var err := socket.connect_to_url(url)
	was_open = false
	connected = false
	deadline = Time.get_ticks_msec() / 1000.0 + 12.0
	prefix = "%x_%x" % [Time.get_unix_time_from_system(), randi()]
	if err != OK:
		credentials.clear()
		status_changed.emit("Could not open that server address.")
	else:
		status_changed.emit("Reconnecting to your server…" if reconnect else "Connecting to your server…")

func _process(_delta: float) -> void:
	poll()

func poll() -> void:
	var now := Time.get_ticks_msec() / 1000.0
	if not socket:
		if retry_at > 0 and now >= retry_at:
			connect_server(endpoint, {"token":resume_token}, true)
		return
	socket.poll()
	var ready := socket.get_ready_state()
	if ready == WebSocketPeer.STATE_OPEN:
		if not was_open:
			was_open = true
			var auth := credentials.duplicate(true)
			if not auth.has("type"): auth.type = "auth"
			auth.protocol = 2
			send(auth)
			credentials.clear()
			status_changed.emit("Verifying your explorer account…")
		while socket and socket.get_available_packet_count():
			var data = JSON.parse_string(socket.get_packet().get_string_from_utf8())
			if data is Dictionary:
				if data.get("type") == "welcome":
					connected = true
					resume_token = str(data.token)
					retry_count = 0
					ping_at = now + 2
				if data.get("type") == "account_result" and data.get("action") == "recovery_reset": deadline = INF
				packet.emit(data)
		if connected and now >= ping_at:
			ping_at = now + 3
			send({"type":"ping","sent":Time.get_ticks_msec()})
		elif not connected and now > deadline:
			credentials.clear()
			socket.close()
			intentional_close = true
			status_changed.emit("Connection timed out. Check the address or try again.")
	elif ready == WebSocketPeer.STATE_CLOSED:
		connected = false
		var code := socket.get_close_code()
		var reason := socket.get_close_reason()
		socket = null
		credentials.clear()
		if not intentional_close and not resume_token.is_empty() and code not in [1000,1008] and retry_count < 4:
			retry_count += 1
			retry_at = now + pow(2.0, retry_count-1) * .6
			status_changed.emit("Reconnecting… attempt %d of 4" % retry_count)
		else:
			retry_at = 0
			if intentional_close: return
			status_changed.emit("Disconnected. " + (reason if not reason.is_empty() else "Sign in to reconnect. Your progress is saved."))
	elif now > deadline and not connected:
		socket.close()
		intentional_close = true
		status_changed.emit("Connection timed out. Check the server address.")

func send(data: Dictionary) -> void:
	if socket and socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		socket.send_text(JSON.stringify(data))

func action(kind: String, data: Dictionary = {}) -> void:
	data = data.duplicate(true)
	for field in ["x","y","slot","from","to","count","revision","minutes"]:
		if data.has(field): data[field] = int(data[field])
	if data.has("offer"):
		for item in data.offer: data.offer[item] = int(data.offer[item])
	sequence += 1
	send(data.merged({"type": kind, "request": prefix + "_" + str(sequence)}, true))

func disconnect_server(forget := true) -> void:
	intentional_close = true
	retry_at = 0
	credentials.clear()
	if forget: resume_token = ""
	if socket:
		socket.close(1000, "Explorer signed out")
		socket.poll()
	connected = false
