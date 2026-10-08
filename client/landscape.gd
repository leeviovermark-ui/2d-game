extends Control
## Visible tiles only. Parallax, lighting and animation never change game authority.
var state: ForgeState
var art: ForgeArt
var camera := Vector2.ZERO
var target := Vector2i(-1, -1)
var clock := 0.0
var particles: Array = []
var landing := true
const TILE := 32.0
var font: Font = preload("res://assets/fonts/DejaVuSans.ttf")
var avatar_motion := {}
var lights: Array = []
var light_grid := {}
var _last_world := ""
var _light_clock := 0.0

func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func _process(delta: float) -> void:
	clock += delta
	if state and state.display_positions.has(state.player_id):
		var pos: Vector2 = state.display_positions[state.player_id]
		var player: Dictionary = state.visual_player(state.player_id)
		var look_ahead := clampf(float(player.get("vx", 0)) * 9.0, -58.0, 58.0)
		var desired := Vector2(pos.x * TILE - size.x * .44 + look_ahead, pos.y * TILE - size.y * .64)
		desired.x = clampf(desired.x, 0, maxf(0, state.width * TILE - size.x))
		desired.y = clampf(desired.y, 0, maxf(0, state.height * TILE - size.y))
		var world_name: String = state.meta.get("name", "")
		if _last_world != world_name or camera.distance_to(desired) > 640:
			camera = desired
			_last_world = world_name
		else:
			camera.x = lerpf(camera.x, desired.x, 1.0 - exp(-delta * 9.0))
			camera.y = lerpf(camera.y, desired.y, 1.0 - exp(-delta * 7.0))
	elif landing:
		camera = Vector2(0, 105)
		_last_world = ""
	if state:
		for id in state.players:
			var player: Dictionary = state.visual_player(id)
			if not avatar_motion.has(id):
				avatar_motion[id] = {"phase": 0.0, "facing": 1, "grounded": true, "landing": 0.0}
			var motion: Dictionary = avatar_motion[id]
			var vx: float = player.get("vx", 0)
			var grounded: bool = player.get("grounded", true)
			if absf(vx) > .12:
				motion.facing = -1 if vx < 0 else 1
			motion.phase += absf(vx) * delta * 2.9
			if grounded and not motion.grounded:
				motion.landing = .13
			motion.grounded = grounded
			motion.landing = maxf(0, float(motion.landing) - delta)
			motion.dust_clock = float(motion.get("dust_clock", 0)) - delta
			if grounded and absf(vx) > 3 and float(motion.dust_clock) <= 0 and particles.size() < 160 and state.display_positions.has(id):
				motion.dust_clock = .16
				var feet: Vector2 = state.display_positions[id] * TILE + Vector2(0, 49)
				particles.append({"pos": feet + Vector2(-signf(vx) * 6, -2), "velocity": Vector2(-vx * 2, -14), "life": .32, "color": Color("d7c39e"), "size": 2})
		for id in avatar_motion.keys():
			if not state.players.has(id):
				avatar_motion.erase(id)
		_light_clock -= delta
		if _light_clock <= 0 and not landing:
			refresh_lights()
			_light_clock = .10
	for p in particles:
		p.life -= delta
		p.pos += p.velocity * delta
		p.velocity.y += 170 * delta
	particles = particles.filter(func(p): return p.life > 0)
	queue_redraw()

func tile_at_mouse() -> Vector2i:
	return Vector2i(((get_local_mouse_position() + camera) / TILE).floor())

func burst(x: int, y: int, item: String) -> void:
	var c := Color(state.items.get(item, {}).get("color", "8a9a80"))
	for i in range(10):
		if particles.size() >= 180:
			break
		particles.append({"pos": Vector2(x + .5, y + .5) * TILE, "velocity": Vector2(randf_range(-75, 75), randf_range(-125, -35)), "life": .58, "color": c.lightened(randf_range(-.15, .18)), "size": 2 if i % 3 == 0 else 3})

func _draw() -> void:
	if not state or size.x < 1 or size.y < 1:
		return
	var biome: String = state.meta.get("biome", "forest")
	draw_background(biome)
	if landing:
		landing_ground()
	else:
		draw_tiles()
		draw_light_glows()
		for drop in state.drops.values():
			var pos := Vector2(drop.x, drop.y) * TILE - camera + Vector2(0, sin(clock * 3 + float(hash(drop.id) % 6)) * 2)
			if not Rect2(Vector2(-32, -32), size + Vector2(64, 64)).has_point(pos):
				continue
			draw_circle(pos, 12, Color(.95, .86, .60, .10))
			draw_texture_rect(art.icon(drop.item, state.items[drop.item]), Rect2(pos - Vector2(9, 9), Vector2(18, 18)), false)
		for id in state.players:
			if state.display_positions.has(id):
				avatar(state.visual_player(id), state.display_positions[id] * TILE - camera, id == state.player_id)
		draw_target()
		for p in particles:
			draw_rect(Rect2(p.pos - camera, Vector2(p.size, p.size)), Color(p.color, clampf(p.life / .58, 0, 1)))
	draw_ambient(biome)
	draw_weather(biome)

func draw_background(biome: String) -> void:
	var top := Color("64b6e0")
	var horizon := Color("d3edc8")
	if biome == "desert":
		top = Color("89bee2")
		horizon = Color("ffe0a4")
	elif biome == "snow":
		top = Color("88c7e8")
		horizon = Color("e2f5ee")
	for i in range(24):
		var color := top.lerp(horizon, float(i) / 23.0)
		draw_rect(Rect2(0, i * size.y / 24.0, size.x, size.y / 24.0 + 1), color)
	var sun := Vector2(size.x * .77 - camera.x * .022, 100 - camera.y * .032)
	var sunlight := Color("ffe2a2") if biome == "desert" else Color("fff2b3")
	for i in range(3):
		draw_circle(sun, 58 - i * 12, Color(sunlight, .025 + i * .012))
	draw_circle(sun, 23 if biome == "desert" else 19, sunlight)
	draw_circle(sun, 13, Color("fff6cf"))
	for i in range(16):
		var p := Vector2(posmod(i * 197 + 59, int(size.x)), 20 + posmod(i * 83, 120))
		if biome == "snow":
			draw_rect(Rect2(p, Vector2(2, 2)), Color(.96, .99, 1, .24 + .07 * sin(clock * .6 + i)))
	draw_birds(biome)
	for i in range(6):
		var x := fposmod(i * 311 + 70 - camera.x * .045 + clock * 1.4, size.x + 240) - 120
		var y: float = 55 + posmod(i * 39, 139) - camera.y * .018
		cloud(Vector2(x, y), Color(horizon.lightened(.25), .48 if biome == "desert" else .58))
	if biome == "desert":
		mesas(.05, size.y * .49, Color("d3af99"), 93, 31)
		mesas(.12, size.y * .67, Color("be9984"), 88, 13)
		mountains(.21, size.y * .84, Color("a48769"), 48, 17)
		for i in range(10):
			var x := fposmod(i * 193 + 52 - camera.x * .29, size.x + 220) - 110
			cactus(Vector2(x, size.y * .92 - camera.y * .09), 45 + posmod(i * 43, 76), Color("84a175"))
	elif biome == "snow":
		snow_ridge(.045, size.y * .57, Color("add2e0"), 145, 10)
		snow_ridge(.10, size.y * .71, Color("8eb8cf"), 102, 61)
		mountains(.18, size.y * .83, Color("79a5bb"), 47, 17)
		for layer in range(2):
			for i in range(12):
				var x := fposmod(i * 143 + posmod(i * 49, 70) - camera.x * (.20 + layer * .15), size.x + 260) - 130
				tree(Vector2(x, size.y * (.87 + layer * .05) - camera.y * .09), 90 + posmod(i * 51, 100), Color("92bbaa") if layer == 0 else Color("78a08e"), true)
	else:
		mountains(.045, size.y * .48, Color("a4c8ba"), 82, 31)
		mountains(.10, size.y * .63, Color("85b79b"), 80, 65)
		mountains(.18, size.y * .78, Color("70a57e"), 43, 17)
		var forest_floor := clampf(21 * TILE - camera.y, size.y * .6, size.y * .94)
		for layer in range(2):
			for i in range(14):
				var x := fposmod(i * 137 + posmod(i * 49, 70) - camera.x * (.20 + layer * .15), size.x + 260) - 130
				var base := Vector2(x, forest_floor + 46 + layer * 23)
				var color := Color("82b292") if layer == 0 else Color("679a7d")
				var tree_height: float = 120 + posmod(i * 51, 105)
				if i % 3 == 0:
					tree(base, tree_height, color)
				else:
					broadleaf_tree(base, tree_height, color)

func cloud(pos: Vector2, color: Color) -> void:
	pos = pos.round()
	draw_rect(Rect2(pos, Vector2(104, 6)), color)
	draw_rect(Rect2(pos + Vector2(18, -7), Vector2(71, 7)), color)
	draw_rect(Rect2(pos + Vector2(37, -12), Vector2(31, 5)), color)
	draw_rect(Rect2(pos + Vector2(12, 6), Vector2(75, 2)), Color(color, color.a * .5))

func mountains(parallax: float, base: float, color: Color, amplitude: float, seed_value: int) -> void:
	var points := PackedVector2Array([Vector2(-20, size.y), Vector2(-20, base)])
	for x in range(-20, int(size.x) + 41, 20):
		var wx := x + camera.x * parallax
		var y := base - sin(wx * .005 + seed_value) * amplitude - sin(wx * .012 + seed_value) * amplitude * .4 - camera.y * .055
		points.append(Vector2(x, round(y / 3) * 3))
	points.append(Vector2(size.x + 40, size.y))
	draw_colored_polygon(points, color)

func mesas(parallax: float, base: float, color: Color, amplitude: float, seed_value: int) -> void:
	var points := PackedVector2Array([Vector2(-40, size.y)])
	for x in range(-40, int(size.x) + 81, 40):
		var wx := x + camera.x * parallax
		var height := maxf(.18, sin(wx * .008 + seed_value)) * amplitude
		points.append(Vector2(x, round((base - height - camera.y * .05) / 8) * 8))
	points.append(Vector2(size.x + 80, size.y))
	draw_colored_polygon(points, color)
	for i in range(3):
		draw_rect(Rect2(0, base - i * 14 - camera.y * .05, size.x, 2), Color(color.darkened(.1), .17))

func snow_ridge(parallax: float, base: float, color: Color, amplitude: float, seed_value: int) -> void:
	mountains(parallax, base, color, amplitude, seed_value)
	for i in range(7):
		var x := fposmod(i * 263 + seed_value * 11 - camera.x * parallax, size.x + 340) - 170
		var h: float = amplitude * (.65 + .2 * sin(i * 4.2))
		var y := base - camera.y * .055
		draw_colored_polygon(PackedVector2Array([Vector2(x - 110, y + 55), Vector2(x, y - h), Vector2(x + 118, y + 55)]), color)
		draw_colored_polygon(PackedVector2Array([Vector2(x, y - h), Vector2(x - 34, y - h + 44), Vector2(x - 12, y - h + 36), Vector2(x + 5, y - h + 54), Vector2(x + 17, y - h + 35), Vector2(x + 39, y - h + 50)]), color.lightened(.35))

func tree(base: Vector2, h: float, color: Color, snowy: bool = false) -> void:
	base = base.round()
	draw_rect(Rect2(base.x - 3, base.y - h, 6, h), color.darkened(.15))
	for j in range(4):
		var top := base.y - h + j * h * .16
		var half: float = 17 + j * 8
		var points := PackedVector2Array([Vector2(base.x, top), Vector2(base.x - half, top + h * .28), Vector2(base.x - half * .6, top + h * .26), Vector2(base.x - half - 6, top + h * .36), Vector2(base.x + half + 6, top + h * .36), Vector2(base.x + half * .65, top + h * .25), Vector2(base.x + half, top + h * .28)])
		draw_colored_polygon(points, color)
		if snowy:
			draw_colored_polygon(PackedVector2Array([Vector2(base.x, top), Vector2(base.x - half * .60, top + h * .20), Vector2(base.x - 2, top + h * .16), Vector2(base.x + half * .65, top + h * .21)]), color.lightened(.33))
		else:
			draw_line(Vector2(base.x - half * .6, top + h * .24), Vector2(base.x - 4, top + h * .19), color.lightened(.07), 3)

func cactus(base: Vector2, h: float, color: Color) -> void:
	draw_rect(Rect2(base.x - 6, base.y - h, 12, h), color)
	draw_rect(Rect2(base.x - 4, base.y - h - 4, 8, 4), color)
	draw_rect(Rect2(base.x - 24, base.y - h * .57, 21, 8), color)
	draw_rect(Rect2(base.x - 24, base.y - h * .8, 8, h * .23), color)
	draw_rect(Rect2(base.x + 3, base.y - h * .37, 24, 8), color)
	draw_rect(Rect2(base.x + 19, base.y - h * .61, 8, h * .24), color)
	draw_rect(Rect2(base.x - 3, base.y - h + 6, 2, h - 6), color.lightened(.14))

func landing_ground() -> void:
	var ground: float = round(size.y * .79)
	draw_rect(Rect2(0, ground, size.x, size.y - ground), Color("99714f"))
	draw_rect(Rect2(0, ground, size.x, 5), Color("acd579"))
	draw_rect(Rect2(0, ground + 5, size.x, 3), Color("70a66b"))
	for i in range(65):
		var x: float = i * 26
		draw_rect(Rect2(x, ground - 4 - posmod(i * 37, 11), 2, 12), Color("bedf8b"))
	for i in range(4):
		tree(Vector2(75 + i * 130, ground), float(140 + posmod(i * 41, 90)), Color("7aaa6b"))
	var rect := Rect2(360, ground - 120, 160, 120)
	draw_rect(rect, Color("a08357"))
	for y in range(int(rect.position.y), int(ground), 12):
		draw_line(Vector2(360, y), Vector2(520, y), Color("725a3f"), 2)
		draw_line(Vector2(362, y + 2), Vector2(518, y + 2), Color("b89967"), 1)
	draw_rect(Rect2(366, ground - 120, 7, 120), Color("594d3a"))
	draw_rect(Rect2(509, ground - 120, 7, 120), Color("594d3a"))
	draw_rect(Rect2(480, ground - 181, 20, 47), Color("737f7c"))
	draw_rect(Rect2(478, ground - 182, 24, 6), Color("98a397"))
	draw_colored_polygon(PackedVector2Array([Vector2(345, ground - 120), Vector2(440, ground - 168), Vector2(535, ground - 120)]), Color("374d46"))
	draw_line(Vector2(345, ground - 119), Vector2(535, ground - 119), Color("77907a"), 3)
	draw_rect(Rect2(423, ground - 65, 34, 65), Color("354235"))
	draw_rect(Rect2(427, ground - 62, 26, 62), Color("5e5b3b"))
	draw_circle(Vector2(450, ground - 30), 2, Color("d9bb76"))
	for window_x in [379, 487]:
		draw_rect(Rect2(window_x - 3, ground - 88, 28, 36), Color("554a36"))
		draw_rect(Rect2(window_x, ground - 85, 22, 29), Color("e5c387"))
		draw_rect(Rect2(window_x + 10, ground - 85, 2, 29), Color("796746"))
		draw_rect(Rect2(window_x, ground - 72, 22, 2), Color("796746"))
	draw_rect(Rect2(351, ground - 4, 178, 6), Color("7e8c7c"))
	for i in range(5):
		var p := Vector2(565 + i * 18, ground - 14)
		draw_line(p, p + Vector2(0, -26), Color("a7aa69"), 2)
		draw_rect(Rect2(p.x - 3, p.y - 30, 7, 11), Color("e3c06d"))

func refresh_lights() -> void:
	lights.clear()
	light_grid.clear()
	var low := Vector2i((camera / TILE).floor()) - Vector2i(6, 6)
	var high := Vector2i(((camera + size) / TILE).ceil()) + Vector2i(6, 6)
	for y in range(maxi(0, low.y), mini(state.height, high.y + 1)):
		for x in range(maxi(0, low.x), mini(state.width, high.x + 1)):
			var id: String = state.tiles.get(Vector2i(x, y), "")
			var definition: Dictionary = state.items.get(id, {})
			if definition.get("light", false) or id in ["core", "crystal"]:
				var radius: float = definition.get("light_radius", 4.0 if id == "torch" else 2.3)
				lights.append({"pos": Vector2(x + .5, y + .5), "radius": radius, "color": Color("9fe9d1") if id in ["core", "crystal", "lumen_lamp"] else Color(definition.get("color", "f7c981")).lightened(.1)})
	# Build a bounded light field once every 100 ms, then use constant-time tile lookups.
	# Adjacent lamps merge using the strongest light instead of washing the scene out.
	for light in lights:
		var radius: float = light.radius
		var center := Vector2i(light.pos)
		for y in range(maxi(low.y, center.y - int(radius)), mini(high.y, center.y + int(radius)) + 1):
			for x in range(maxi(low.x, center.x - int(radius)), mini(high.x, center.x + int(radius)) + 1):
				var distance := (Vector2(x + .5, y + .5) - Vector2(light.pos)).length()
				if distance < radius:
					var strength := pow(1.0 - distance / radius, .8) * .57
					var key := Vector2i(x, y)
					light_grid[key] = maxf(float(light_grid.get(key, 0)), strength)
	if state.display_positions.has(state.player_id):
		var pos: Vector2 = state.display_positions[state.player_id] + Vector2(0, .7)
		for y in range(int(pos.y) - 3, int(pos.y) + 4):
			for x in range(int(pos.x) - 3, int(pos.x) + 4):
				var strength := maxf(0, 1.0 - Vector2(x + .5, y + .5).distance_to(pos) / 3.0) * .34
				var key := Vector2i(x, y)
				light_grid[key] = maxf(float(light_grid.get(key, 0)), strength)

func draw_light_glows() -> void:
	for light in lights:
		var pos: Vector2 = light.pos * TILE - camera
		if not Rect2(Vector2(-160, -160), size + Vector2(320, 320)).has_point(pos):
			continue
		var pulse := 1.0 + .035 * sin(clock * 3.4 + light.pos.x * 2.1)
		for i in range(3):
			draw_circle(pos, (18 + i * 18) * pulse, Color(light.color, .023 - i * .005))
		draw_circle(pos, 3, Color(light.color.lightened(.3), .4))

func draw_tiles() -> void:
	var low := Vector2i((camera / TILE).floor())
	var high := Vector2i(((camera + size) / TILE).ceil())
	for y in range(maxi(0, low.y), mini(state.height, high.y + 1)):
		for x in range(maxi(0, low.x), mini(state.width, high.x + 1)):
			var key := Vector2i(x, y)
			var id: String = state.tiles.get(key, "")
			var pos := (Vector2(x, y) * TILE - camera).round()
			var rect := Rect2(pos, Vector2(TILE, TILE))
			var light: float = light_grid.get(key, 0)
			if y > 25:
				var cave_color := Color("344752").lightened(light * .25)
				draw_rect(rect, cave_color)
				if (x * 11 + y * 7) % 13 == 0:
					draw_rect(Rect2(pos + Vector2(3, 9), Vector2(20, 2)), cave_color.lightened(.035))
			if id.is_empty():
				continue
			var definition: Dictionary = state.items.get(id, {})
			if definition.get("category", "") == "crop":
				var age := state.now() - float(state.crops.get(key, state.now()))
				var duration: float = definition.get("growth", 90.0)
				var height := 32 * clampf(age / duration, .2, 1)
				draw_texture_rect(art.icon(id, definition), Rect2(pos + Vector2(0, 32 - height), Vector2(32, height)), false, Color("b1c591") if age < duration else Color.WHITE)
			else:
				draw_texture_rect(art.icon(id, definition), rect, false)
			draw_tile_animation(id, definition, pos, key)
			if definition.get("solid", false) and definition.get("texture", "") != "glass" and id not in ["glass", "reinforced_glass", "platform", "water", "ice"]:
				var color := Color(definition.get("color", "7c888b"))
				if not solid_at(key + Vector2i(0, -1)):
					draw_rect(Rect2(pos, Vector2(32, 2)), Color(color.lightened(.28), .74))
				if not solid_at(key + Vector2i(-1, 0)):
					draw_rect(Rect2(pos, Vector2(2, 32)), Color(color.lightened(.08), .7))
				if not solid_at(key + Vector2i(1, 0)):
					draw_rect(Rect2(pos + Vector2(30, 2), Vector2(2, 30)), Color(.04, .08, .08, .24))
				if not solid_at(key + Vector2i(0, 1)):
					draw_rect(Rect2(pos + Vector2(0, 29), Vector2(32, 3)), Color(.03, .06, .07, .30))
			if y > 25:
				var darkness := maxf(0, minf(.54, .08 + (y - 25) * .016) - light)
				draw_rect(rect, Color(.015, .025, .04, darkness))
			if id == "grass" and not state.tiles.has(key + Vector2i(0, -1)):
				for blade in range(3):
					var bx := pos.x + 5 + blade * 10
					var sway := sin(clock * 1.5 + x * .8) * 1.2
					draw_line(Vector2(bx, pos.y), Vector2(bx - 2 + sway, pos.y - 4 - posmod(x * 7 + blade, 5)), Color("b1d887"), 2)
				if x % 11 == 4:
					draw_rect(Rect2(pos + Vector2(21, -5), Vector2(3, 3)), Color("e2c68e"))

func solid_at(key: Vector2i) -> bool:
	var id: String = state.tiles.get(key, "")
	return bool(state.items.get(id, {}).get("solid", false))

func draw_target() -> void:
	if target.x < 0 or target.y < 0 or target.x >= state.width or target.y >= state.height:
		return
	var box := Rect2((Vector2(target) * TILE - camera).round(), Vector2(TILE, TILE))
	var in_reach := false
	if state.display_positions.has(state.player_id):
		var player_pos: Vector2 = state.display_positions[state.player_id]
		in_reach = (player_pos + Vector2(0, .7)).distance_to(Vector2(target) + Vector2(.5, .5)) <= state.movement.reach
	var color := Color("fff0ab") if in_reach and state.can_build() else Color("f29b8b")
	draw_rect(box.grow(-1), Color(color, .07))
	for corner in [box.position, box.position + Vector2(26, 0), box.position + Vector2(0, 26), box.position + Vector2(26, 26)]:
		draw_rect(Rect2(corner, Vector2(6, 2)), color)
		draw_rect(Rect2(corner, Vector2(2, 6)), color)
	if not state.players.has(state.player_id) or not state.players[state.player_id].get("mining"):
		return
	var mining: Dictionary = state.players[state.player_id].mining
	if Vector2i(int(mining.get("x", -1)), int(mining.get("y", -1))) != target:
		return
	var progress := clampf((state.now() - float(mining.start)) / maxf(.01, float(mining.duration)), 0, 1)
	if progress > .16:
		var crack := Color(.06, .09, .10, .72)
		draw_line(box.position + Vector2(17, 4), box.position + Vector2(13, 14), crack, 2)
		draw_line(box.position + Vector2(13, 14), box.position + Vector2(21, 22), crack, 2)
		if progress > .45:
			draw_line(box.position + Vector2(13, 14), box.position + Vector2(4, 17), crack, 2)
		if progress > .72:
			draw_line(box.position + Vector2(21, 22), box.position + Vector2(18, 30), crack, 2)
			draw_line(box.position + Vector2(21, 22), box.position + Vector2(28, 20), crack, 2)
	draw_rect(Rect2(box.position + Vector2(0, 35), Vector2(32, 3)), Color("122722"))
	draw_rect(Rect2(box.position + Vector2(0, 35), Vector2(32 * progress, 3)), Color("e5c477"))

func avatar(p: Dictionary, pos: Vector2, local: bool) -> void:
	if not Rect2(Vector2(-80, -80), size + Vector2(160, 160)).has_point(pos):
		return
	var motion: Dictionary = avatar_motion.get(p.id, {"phase": 0.0, "facing": 1, "grounded": true, "landing": 0.0})
	var moving := absf(float(p.get("vx", 0))) > .12
	var grounded: bool = p.get("grounded", true)
	var step: float = sin(float(motion.phase)) * 4 if moving and grounded else 0.0
	var jump_leg := clampf(float(p.get("vy", 0)) * .25, -3, 3) if not grounded else 0.0
	var facing: int = motion.facing
	var bob := -absf(step) * .25 if moving and grounded else sin(clock * 2.2 + float(hash(p.id) % 9)) * .35
	var squash := float(motion.landing) / .13 * 2
	var torso := pos + Vector2(0, bob + squash)
	var accent := Color("f6cb85") if local else Color("bde5f4")
	var coat := Color("90ba94") if local else Color("94bbd8")
	var appearance: Dictionary = p.get("appearance", {})
	var outfit: String = appearance.get("outfit", "")
	if state.items.has(outfit):
		coat = Color(state.items[outfit].get("color", "90ba94"))
	var emote: String = p.get("emote", "") if float(p.get("emote_until", 0)) > state.now() else ""
	if emote == "dance":
		torso += Vector2(sin(clock * 7) * 2, sin(clock * 14) * 2)
	elif emote == "sit":
		torso.y += 9
	draw_avatar_back(appearance, torso, facing)

	if grounded:
		draw_ellipse_shadow(pos + Vector2(0, 49))
	# Compact explorer silhouette, alternating legs, coat tails and a swinging scarf.
	draw_rect(Rect2(pos + Vector2(-8, 31 + jump_leg), Vector2(6, 16 + step - jump_leg)), Color("344a4d"))
	draw_rect(Rect2(pos + Vector2(2, 31 - jump_leg), Vector2(6, 16 - step + jump_leg)), Color("415d5e"))
	draw_rect(Rect2(pos + Vector2(-10, 45 + step), Vector2(10, 5)), Color("263538"))
	draw_rect(Rect2(pos + Vector2(1, 45 - step), Vector2(10, 5)), Color("263538"))
	draw_rect(Rect2(pos + Vector2(-9, 46 + step), Vector2(8, 1)), Color("64706a"))
	draw_rect(Rect2(pos + Vector2(2, 46 - step), Vector2(8, 1)), Color("64706a"))
	draw_rect(Rect2(torso + Vector2(-13 * facing - 3, 20), Vector2(7, 15)), Color("715b45"))
	draw_rect(Rect2(torso + Vector2(-13 * facing - 2, 21), Vector2(5, 9)), Color("a18a60"))
	draw_rect(Rect2(torso + Vector2(-10, 17), Vector2(20, 20)), coat.darkened(.24))
	draw_rect(Rect2(torso + Vector2(-8, 18), Vector2(16, 17)), coat)
	draw_rect(Rect2(torso + Vector2(-8, 19), Vector2(3, 14)), coat.lightened(.16))
	draw_rect(Rect2(torso + Vector2(3, 27), Vector2(4, 4)), coat.darkened(.2))
	draw_rect(Rect2(torso + Vector2(-9, 34), Vector2(18, 3)), Color("6b6349"))
	draw_rect(Rect2(torso + Vector2(0, 34), Vector2(3, 3)), Color("c7b584"))
	var hand_swing: float = step * .45 if moving else 0.0
	if emote in ["wave", "cheer", "dance"]:
		hand_swing = 12 + sin(clock * 9) * 3
	draw_rect(Rect2(torso + Vector2(5 * facing - 3, 23 - hand_swing), Vector2(6, 10)), coat.lightened(.12))
	draw_rect(Rect2(torso + Vector2(6 * facing - 2, 31 - hand_swing), Vector2(5, 4)), Color("d5b68e"))
	draw_rect(Rect2(torso + Vector2(-7, 3), Vector2(15, 15)), Color("bd9b78"))
	draw_rect(Rect2(torso + Vector2(-5, 5), Vector2(12, 11)), Color("ddc29c"))
	draw_rect(Rect2(torso + Vector2(-9, 0), Vector2(18, 7)), Color("49483b"))
	draw_rect(Rect2(torso + Vector2(-7, 1), Vector2(11, 2)), Color("666247"))
	draw_rect(Rect2(torso + Vector2(-9 if facing > 0 else 5, 5), Vector2(4, 6)), Color("49483b"))
	draw_rect(Rect2(torso + Vector2(facing * 4, 9), Vector2(2, 3)), Color("273337"))
	draw_rect(Rect2(torso + Vector2(facing * 5, 14), Vector2(2, 1)), Color("a9896c"))
	draw_rect(Rect2(torso + Vector2(-9, 17), Vector2(18, 4)), accent)
	draw_rect(Rect2(torso + Vector2(-12 - facing * 5, 19 - step * .2), Vector2(9, 3)), accent.darkened(.17))
	draw_avatar_hat(appearance, torso, facing)
	if not emote.is_empty():
		draw_emote(emote, pos)
	if p.get("held") and state.items.has(p.held):
		var item: String = p.held
		var tool_pos := torso + Vector2(9 * facing - (18 if facing < 0 else 0), 22 - hand_swing)
		if p.get("mining"):
			tool_pos += Vector2(facing * 5 * sin(clock * 18), -8 * absf(sin(clock * 18)))
		draw_set_transform(tool_pos + Vector2(21 if facing < 0 else 0, 0), 0, Vector2(facing, 1))
		draw_texture_rect(art.icon(item, state.items[item]), Rect2(Vector2.ZERO, Vector2(21, 21)), false)
		draw_set_transform(Vector2.ZERO)
	var label: String = p.name + ("  ·  you" if local else "")
	var text_width := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	draw_rect(Rect2(pos + Vector2(-text_width / 2 - 7, -26), Vector2(text_width + 14, 20)), Color(.055, .10, .11, .83))
	draw_string(font, pos + Vector2(-text_width / 2, -11), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("e8ecdc"))

func draw_ellipse_shadow(pos: Vector2) -> void:
	draw_set_transform(pos, 0, Vector2(1, .24))
	draw_circle(Vector2.ZERO, 14, Color(0, 0, 0, .24))
	draw_set_transform(Vector2.ZERO)

func draw_ambient(biome: String) -> void:
	var visibility := 1.0 if landing else clampf(1.0 - maxf(0, camera.y - 420) / 250.0, 0, 1)
	if visibility <= 0:
		return
	for i in range(14 if biome == "snow" else 9):
		var x := fposmod(i * 137 + clock * (3 + i % 3), size.x)
		var y := fposmod(i * 79 + clock * (12 if biome == "snow" else 2), size.y)
		x += sin(clock * .3 + i * 8) * 16
		var color := Color(.86, .94, .94, .34 * visibility) if biome == "snow" else Color(.92, .88, .57, visibility * (.12 + .08 * sin(clock + i)))
		draw_rect(Rect2(x, y, 2, 2), color)

func draw_birds(biome: String) -> void:
	for i in range(5):
		var x := fposmod(i * 321 + clock * (13 + i * 2) - camera.x * .075, size.x + 140) - 70
		var y := 70 + posmod(i * 37, 118) + sin(clock * .7 + i) * 10 - camera.y * .015
		var flap := sin(clock * 5.4 + i * 1.7) * 3
		var color := Color("597884", .5) if biome != "desert" else Color("a68070", .5)
		draw_line(Vector2(x - 6, y - flap), Vector2(x, y), color, 1.5, true)
		draw_line(Vector2(x, y), Vector2(x + 6, y - flap), color, 1.5, true)

func draw_tile_animation(id: String, definition: Dictionary, pos: Vector2, key: Vector2i) -> void:
	if definition.get("fluid", false):
		if state.tiles.get(key + Vector2i(0, -1), "") != id:
			var wave := sin(clock * 2 + key.x * .7) * 1.5
			draw_line(pos + Vector2(0, 2 + wave), pos + Vector2(32, 2 + sin(clock * 2 + (key.x + 1) * .7) * 1.5), Color("d4f9ff", .64), 2)
		for i in range(2):
			var x := fposmod(clock * 5 + key.x * 13 + i * 19, 32)
			var y := 9 + i * 11 + sin(clock + key.x) * 2
			draw_line(pos + Vector2(x, y), pos + Vector2(minf(32, x + 5), y), Color("c0f3ff", .25), 1)
	elif id in ["campfire", "candle"]:
		var base := pos + Vector2(16, 20 if id == "campfire" else 10)
		for i in range(3):
			var phase := fposmod(clock * 1.7 + i * .34 + key.x * .14, 1)
			var spark := base + Vector2(sin(clock * 2.5 + i) * 4, -phase * 20)
			draw_rect(Rect2(spark, Vector2(1.5, 2.5)), Color(1, .88, .54, 1 - phase))
	elif id == "portal":
		var center := pos + Vector2(16, 15)
		for i in range(5):
			var angle := clock * .8 + i * TAU / 5
			var spark := center + Vector2(cos(angle) * 7, sin(angle) * 9)
			draw_rect(Rect2(spark, Vector2(2, 2)), Color("f3e3ff", .55))
	elif id == "fountain":
		for i in range(3):
			var phase := fposmod(clock + i * .31, 1)
			draw_rect(Rect2(pos + Vector2(8 + i * 8, 14 + phase * 13), Vector2(1, 3)), Color("dbf8ff", .7 * (1 - phase)))
	elif id in ["amethyst", "crystal", "amber"]:
		var phase := sin(clock * 2.2 + key.x * 5 + key.y * 2)
		if phase > .8:
			var center := pos + Vector2(8 if id == "amethyst" else 18, 10)
			var color := Color("fcfff4", (phase - .8) * 3)
			draw_line(center - Vector2(3, 0), center + Vector2(3, 0), color, 1)
			draw_line(center - Vector2(0, 3), center + Vector2(0, 3), color, 1)

func draw_avatar_back(appearance: Dictionary, pos: Vector2, facing: int) -> void:
	var item: String = appearance.get("back", "")
	if not state.items.has(item):
		return
	var color := Color(state.items[item].get("color", "ba98d7"))
	if item == "cape":
		var sway := sin(clock * 3) * 3
		draw_colored_polygon(PackedVector2Array([pos + Vector2(-facing * 7, 18), pos + Vector2(-facing * 17, 37), pos + Vector2(-facing * (24 + sway), 39), pos + Vector2(-facing * 14, 18)]), color.darkened(.12))
		draw_line(pos + Vector2(-facing * 13, 20), pos + Vector2(-facing * (21 + sway), 37), color.lightened(.12), 2)
	elif item == "wings":
		var flutter := sin(clock * 2.3) * 2
		for side in [-1, 1]:
			for feather in range(4):
				draw_line(pos + Vector2(side * 6, 24), pos + Vector2(side * (17 + flutter - feather * 2), 8 + feather * 7), color.darkened(.08), 4, true)
				draw_line(pos + Vector2(side * 7, 23), pos + Vector2(side * (16 + flutter - feather * 2), 8 + feather * 7), color.lightened(.15), 1.5, true)
	else:
		draw_rect(Rect2(pos + Vector2(-facing * 17 - 3, 20), Vector2(9, 16)), color.darkened(.2))
		draw_rect(Rect2(pos + Vector2(-facing * 17 - 1, 21), Vector2(7, 13)), color)
		draw_rect(Rect2(pos + Vector2(-facing * 17 + 1, 26), Vector2(3, 5)), color.lightened(.15))

func draw_avatar_hat(appearance: Dictionary, pos: Vector2, facing: int) -> void:
	var item: String = appearance.get("hat", "")
	if not state.items.has(item):
		return
	var color := Color(state.items[item].get("color", "e7c67e"))
	draw_rect(Rect2(pos + Vector2(-10, -3), Vector2(20, 9)), color.darkened(.12))
	draw_rect(Rect2(pos + Vector2(-8, -4), Vector2(15, 8)), color)
	if item == "straw_hat":
		draw_rect(Rect2(pos + Vector2(-14, 4), Vector2(29, 3)), color.lightened(.1))
		draw_rect(Rect2(pos + Vector2(-9, 2), Vector2(19, 2)), Color("b49265"))
	elif item == "miner_helmet":
		draw_circle(pos + Vector2(facing * 7, 2), 3, Color("fff2b3"))
		draw_circle(pos + Vector2(facing * 7, 2), 1.5, Color("ffffe6"))
	else:
		draw_rect(Rect2(pos + Vector2(6 if facing > 0 else -17, 4), Vector2(12, 3)), color.darkened(.05))

func draw_emote(emote: String, pos: Vector2) -> void:
	var color := Color("fff0b7")
	var center := pos + Vector2(0, -44 + sin(clock * 3) * 1.5)
	draw_circle(center, 12, Color("315165", .88))
	if emote == "heart":
		color = Color("f4a5bb")
		draw_circle(center + Vector2(-3, -2), 4, color)
		draw_circle(center + Vector2(3, -2), 4, color)
		draw_colored_polygon(PackedVector2Array([center + Vector2(-7, -1), center + Vector2(0, 7), center + Vector2(7, -1)]), color)
	elif emote == "cheer":
		for i in range(5):
			var angle := i * TAU / 5 - PI * .5
			draw_line(center, center + Vector2(cos(angle), sin(angle)) * 7, color, 3)
	elif emote == "dance":
		draw_line(center + Vector2(2, -6), center + Vector2(2, 5), color, 2)
		draw_circle(center + Vector2(-1, 5), 3, color)
		draw_line(center + Vector2(2, -6), center + Vector2(7, -4), color, 2)
	else:
		var label := "Z" if emote == "sit" else "Hi"
		draw_string(font, center + Vector2(-7, 4), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, color)

func draw_weather(biome: String) -> void:
	if landing or camera.y > 610:
		return
	if biome == "snow":
		for i in range(36):
			var x := fposmod(i * 93 + clock * (7 + i % 4), size.x + 30) - 15
			var y := fposmod(i * 67 + clock * (13 + i % 7), size.y + 20) - 10
			x += sin(clock + i) * 7
			draw_circle(Vector2(x, y), 1 if i % 3 else 1.5, Color("f5fffa", .55 if i % 2 else .33))
	elif biome == "forest":
		for i in range(5):
			var x := fposmod(i * 271 - clock * 8, size.x + 40) - 20
			var y := fposmod(i * 89 + clock * 5, size.y)
			draw_set_transform(Vector2(x, y), sin(clock + i) * .6)
			draw_rect(Rect2(-2, -1, 4, 2), Color("b8d590", .45))
			draw_set_transform(Vector2.ZERO)

func broadleaf_tree(base: Vector2, height: float, color: Color) -> void:
	base = base.round()
	var crown := base - Vector2(0, height * .68)
	draw_rect(Rect2(base - Vector2(4, height * .77), Vector2(8, height * .77)), color.darkened(.25))
	draw_line(base - Vector2(0, height * .34), crown + Vector2(-22, 14), color.darkened(.22), 5)
	draw_line(base - Vector2(0, height * .43), crown + Vector2(25, -4), color.darkened(.22), 4)
	for i in range(5):
		var center := crown + Vector2(sin(i * 2.5) * height * .19, cos(i * 2.1) * height * .12)
		var radius := height * (.17 + .018 * sin(i))
		var points := PackedVector2Array()
		for corner in range(12):
			var angle := corner * TAU / 12
			var pos := center + Vector2(cos(angle), sin(angle)) * radius
			points.append((pos / 3).round() * 3)
		draw_colored_polygon(points, color.lightened(i * .014))
		for patch in range(3):
			var pos := center + Vector2(-radius * .55 + patch * radius * .35, -radius * .42 - sin(patch * 2) * radius * .15)
			draw_rect(Rect2(pos.round(), Vector2(8 + patch * 4, 3)), Color(color.lightened(.15), .38))
