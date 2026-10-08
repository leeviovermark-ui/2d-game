extends SceneTree
## Execute actual client movement against the same terrain/intents as Python.
const Movement = preload("res://client/movement.gd")

class PlaybackWorld extends RefCounted:
	var width := 144
	var height := 56
	var tiles := {}
	var items := {}
	var movement := {}

func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 2:
		push_error("Expected movement input and output paths.")
		quit(1)
		return
	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
	var result := {}
	for case in config.cases:
		var state := PlaybackWorld.new()
		state.items = config.items
		state.movement = config.movement
		for tile in case.tiles:
			state.tiles[Vector2i(int(tile[0]), int(tile[1]))] = tile[2]
		var player: Dictionary = case.initial.duplicate(true)
		var frames := []
		for intent in case.inputs:
			Movement.step(player, state, intent, float(config.delta))
			frames.append(player.duplicate(true))
		result[case.name] = frames
	var output := FileAccess.open(arguments[1], FileAccess.WRITE)
	if output == null:
		push_error("Could not create movement output.")
		quit(1)
		return
	output.store_string(JSON.stringify(result))
	output.close()
	quit()
