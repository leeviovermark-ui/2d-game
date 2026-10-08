extends SceneTree
## Exercise the actual snapshot/prediction state without network or UI substitutes.
const State = preload("res://client/state.gd")
const Movement = preload("res://client/movement.gd")
var checks := []

func verify(condition: bool, description: String) -> void:
	checks.append({"passed":condition, "description":description})

func initial_player(x: float = 11.5, epoch: String = "first-epoch") -> Dictionary:
	var motion := {"x":x, "y":19.449, "vx":0.0, "vy":0.0, "grounded":true, "coyote":0.0, "jump_buffer":0.0}
	return motion.merged({"id":"local", "name":"Local", "processed_input":0, "epoch":epoch,
		"ack_state":motion.duplicate(true), "held":null, "mining":null})

func world(name: String = "START") -> Dictionary:
	var tiles := []
	for x in range(144): tiles.append([x,21,"stone"])
	return {"meta":{"name":name, "owner":null}, "width":144, "height":56, "tiles":tiles, "crops":[], "drops":[]}

func _initialize() -> void:
	var state := State.new()
	state.player_id = "local"
	var start := initial_player()
	state.load_world(world(), start)
	var inputs := []
	for i in range(5): inputs.append(state.predict({"axis":1, "jump":false, "jump_held":false}))
	verify(inputs[0].epoch == "first-epoch", "predicted inputs carry the authoritative movement epoch")
	state.interpolate(1.0/60.0)
	verify(state.predicted.x > start.x, "local movement is predicted before another server snapshot")
	verify(state.display_positions.local.x > start.x, "predicted movement reaches presentation immediately")
	var expected: Dictionary = state.predicted.duplicate(true)
	var acknowledged: Dictionary = start.ack_state.duplicate(true)
	for i in range(2): Movement.step(acknowledged, state, inputs[i], 1.0/60.0)
	var packet := initial_player()
	packet.merge(acknowledged, true)
	packet.processed_input = 2
	packet.ack_state = acknowledged
	state.apply_players([packet])
	verify(state.pending_inputs.size() == 3 and state.pending_inputs[0].seq == 3,
		"acknowledged inputs are removed and only newer frames replay")
	verify(absf(state.predicted.x - expected.x) < .00001 and absf(state.predicted.y - expected.y) < .00001,
		"replaying unacknowledged inputs recovers the deterministic trajectory")
	verify(state.last_ack == 2, "the accepted sequence advances")
	var duplicate: Dictionary = packet.duplicate(true)
	duplicate.ack_state.x = 100.0
	state.apply_players([duplicate])
	verify(absf(state.predicted.x - expected.x) < .00001, "duplicate acknowledgements cannot rewind prediction")
	verify(state.pending_inputs.size() == 3, "duplicate acknowledgements preserve pending inputs")
	for i in range(150): state.predict({"axis":1, "jump":false, "jump_held":false})
	verify(state.pending_inputs.size() == 120, "pending prediction history is bounded")
	verify(state.input_sequence == 155, "history trimming preserves monotonic input sequences")
	state.correction = Vector2(1,1)
	state.load_world(world("DESTINATION"), initial_player(30.5, "second-epoch"))
	verify(state.pending_inputs.is_empty() and state.input_sequence == 0, "world travel discards old input history and resets sequence")
	verify(state.correction == Vector2.ZERO and state.remote_samples.is_empty(), "world travel clears visual correction and remote history")
	verify(absf(state.predicted.x - 30.5) < .00001, "world travel seeds prediction from the new authoritative spawn")
	var next := state.predict({"axis":0, "jump":false, "jump_held":false})
	verify(next.seq == 1, "first input in the new world starts a fresh sequence")
	verify(next.epoch == "second-epoch", "world travel replaces the old movement epoch")
	var local := initial_player(30.5, "second-epoch")
	var remote := initial_player(14.5)
	remote.id = "remote"
	remote.name = "Remote"
	remote.vx = 4.0
	state.apply_players([local, remote])
	var now := Time.get_ticks_msec() / 1000.0
	state.remote_samples.remote = [
		{"time":now-.12, "position":Vector2(14.5,19.449), "velocity":Vector2(4,0)},
		{"time":now-.02, "position":Vector2(14.9,19.449), "velocity":Vector2(4,0)}]
	state.interpolate(1.0/60.0)
	var rendered: Vector2 = state.display_positions.remote
	verify(is_finite(rendered.x) and is_finite(rendered.y) and rendered.x >= 14.5 and rendered.x <= 14.9,
		"remote interpolation stays finite and between bracketing snapshots")
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 1:
		push_error("Expected prediction result path.")
		quit(1)
		return
	var output := FileAccess.open(arguments[0], FileAccess.WRITE)
	if output == null:
		push_error("Could not create prediction output.")
		quit(1)
		return
	output.store_string(JSON.stringify({"checks":checks}))
	output.close()
	quit()
