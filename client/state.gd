extends RefCounted
class_name ForgeState
## The renderer reads these snapshots. It never changes gameplay authority.
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

func _init() -> void:
	var defs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://shared/definitions.json"))
	for item in defs.items:
		items[item.id] = item
	recipes = defs.recipes
	movement = defs.movement

func load_world(world: Dictionary) -> void:
	meta = world.meta
	width = int(world.width)
	height = int(world.height)
	tiles.clear()
	crops.clear()
	drops.clear()
	players.clear()
	display_positions.clear()
	storage.clear()
	for tile in world.tiles:
		tiles[Vector2i(tile[0], tile[1])] = tile[2]
	for crop in world.crops:
		crops[Vector2i(crop[0], crop[1])] = crop[2]
	for drop in world.drops:
		drops[drop.id] = drop

func apply_players(list: Array) -> void:
	var current := {}
	for p in list:
		current[p.id] = p
		if not display_positions.has(p.id):
			display_positions[p.id] = Vector2(p.x, p.y)
	players = current
	for id in display_positions.keys():
		if not players.has(id):
			display_positions.erase(id)

func interpolate(delta: float) -> void:
	for id in players:
		var p: Dictionary = players[id]
		var target := Vector2(p.x, p.y)
		var pos: Vector2 = display_positions[id]
		display_positions[id] = target if pos.distance_to(target) > 5 else pos.lerp(target, 1.0 - exp(-delta * (24.0 if id == player_id else 15.0)))

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
