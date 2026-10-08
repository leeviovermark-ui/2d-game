extends RefCounted
class_name ForgeState
## Immediate local prediction is reconciled against server-confirmed input frames.
const Movement = preload("res://client/movement.gd")
var items := {}
var recipes: Array = []
var movement := {}
var tiles := {}
var crops := {}
var drops := {}
var players := {}
var display_positions := {}
var inventory: Array = []
var selected := 0
var player_id := ""
var player_name := ""
var meta := {}
var width := 144
var height := 56
var server_offset := 0.0
var storage := {}
var trade := {}
var is_admin := false
var social := {}
var progression := {}
var portals := {}
var latency := 0
var predicted := {}
var pending_inputs: Array = []
var input_sequence := 0
var last_ack := -1
var movement_epoch := ""
var correction := Vector2.ZERO
var remote_samples := {}

func _init() -> void:
	var defs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://shared/definitions.json"))
	for item in defs.items:
		items[item.id] = item
	recipes = defs.recipes
	movement = defs.movement

func load_world(world: Dictionary, local_player: Dictionary = {}) -> void:
	meta = world.meta
	width = int(world.width)
	height = int(world.height)
	tiles.clear()
	crops.clear()
	drops.clear()
	players.clear()
	display_positions.clear()
	storage.clear()
	portals.clear()
	predicted.clear()
	pending_inputs.clear()
	remote_samples.clear()
	input_sequence = 0
	last_ack = -1
	movement_epoch = ""
	correction = Vector2.ZERO
	for tile in world.tiles:
		tiles[Vector2i(tile[0], tile[1])] = tile[2]
	for crop in world.crops:
		crops[Vector2i(crop[0], crop[1])] = crop[2]
	for drop in world.drops:
		drops[drop.id] = drop
	if not local_player.is_empty():
		apply_players([local_player])

func apply_players(list: Array) -> void:
	var current := {}
	var timestamp := Time.get_ticks_msec() / 1000.0
	for p in list:
		current[p.id] = p
		var position := Vector2(p.x, p.y)
		if not display_positions.has(p.id): display_positions[p.id] = position
		if p.id == player_id:
			reconcile(p)
		else:
			var samples: Array = remote_samples.get(p.id, [])
			if not samples.is_empty() and position.distance_to(samples.back().position) > 4:
				samples.clear()
			samples.append({"time":timestamp, "position":position, "velocity":Vector2(p.vx,p.vy)})
			if samples.size() > 8: samples.pop_front()
			remote_samples[p.id] = samples
	players = current
	for id in display_positions.keys():
		if not players.has(id):
			display_positions.erase(id)
			remote_samples.erase(id)

func reconcile(p: Dictionary) -> void:
	var ack := int(p.get("processed_input", 0))
	if predicted.is_empty():
		predicted = p.get("ack_state", p).duplicate(true)
		last_ack = ack
		movement_epoch = p.get("epoch", "")
		return
	if ack <= last_ack: return
	var previous := Vector2(predicted.x, predicted.y) + correction
	predicted = p.get("ack_state", p).duplicate(true)
	var remaining: Array = []
	for intent in pending_inputs:
		if int(intent.seq) > ack:
			remaining.append(intent)
			Movement.step(predicted, self, intent, 1.0/60.0)
	pending_inputs = remaining
	last_ack = ack
	var difference := previous - Vector2(predicted.x, predicted.y)
	correction = difference if difference.length() < 3 else Vector2.ZERO

func predict(intent: Dictionary) -> Dictionary:
	input_sequence += 1
	intent = intent.merged({"seq":input_sequence, "epoch":movement_epoch})
	if not predicted.is_empty(): Movement.step(predicted, self, intent, 1.0/60.0)
	pending_inputs.append(intent)
	if pending_inputs.size() > 120: pending_inputs.pop_front()
	return intent

func visual_player(id: String) -> Dictionary:
	var p: Dictionary = players.get(id, {}).duplicate()
	if id == player_id and not predicted.is_empty():
		p.merge(predicted, true)
	return p

func interpolate(delta: float) -> void:
	correction *= exp(-delta * 22.0)
	var render_time := Time.get_ticks_msec() / 1000.0 - .075
	for id in players:
		if id == player_id and not predicted.is_empty():
			display_positions[id] = Vector2(predicted.x, predicted.y) + correction
			continue
		var samples: Array = remote_samples.get(id, [])
		if samples.is_empty(): continue
		var position: Vector2 = samples[0].position
		for i in range(1, samples.size()):
			var a: Dictionary = samples[i-1]
			var b: Dictionary = samples[i]
			if render_time >= a.time and render_time <= b.time:
				position = a.position.lerp(b.position, clampf((render_time-a.time)/maxf(.001,b.time-a.time),0,1))
				break
		if render_time >= samples.back().time:
			position = samples.back().position + samples.back().velocity * clampf(render_time-samples.back().time,0,.08)
		display_positions[id] = position

func now() -> float:
	return Time.get_unix_time_from_system() + server_offset

func owned(item: String) -> int:
	var n := 0
	for stack in inventory:
		if stack and stack.id == item:
			n += int(stack.n)
	return n

func can_build() -> bool:
	return meta.get("owner") == null or meta.get("owner") == player_id or player_id in meta.get("builders", []) or meta.get("guest_build", false)
