extends RefCounted
## Same fixed-step collision and movement rules as server/physics.py.
static func collides(p: Vector2, state) -> bool:
	var m: Dictionary = state.movement
	if not is_finite(p.x) or not is_finite(p.y): return true
	if p.x < m.width / 2.0 or p.x > state.width - m.width / 2.0 or p.y < 0 or p.y + m.height > state.height: return true
	for x in range(floori(p.x - m.width / 2.0), floori(p.x + m.width / 2.0 - .0001) + 1):
		for y in range(floori(p.y), floori(p.y + m.height - .0001) + 1):
			var item: String = state.tiles.get(Vector2i(x,y), "")
			if state.items.get(item, {}).get("solid", false): return true
	return false

static func step(p: Dictionary, state, intent: Dictionary, delta: float) -> void:
	var m: Dictionary = state.movement
	var axis := int(intent.axis)
	var energy := clampf(float(p.get("energy", 100.0)), 0, 100)
	var sprint: bool = intent.get("sprint", false) and axis != 0 and energy + 1e-8 >= m.sprint_drain * delta
	p.energy = maxf(0, energy - m.sprint_drain * delta) if sprint else minf(100, energy + m.energy_recovery * delta)
	var speed: float = m.sprint_speed if sprint else m.speed
	p.coyote = m.coyote if p.grounded else maxf(0, p.get("coyote", 0.0) - delta)
	p.jump_buffer = m.jump_buffer if intent.get("jump", false) else maxf(0, p.get("jump_buffer", 0.0) - delta)
	var accel: float = m.acceleration * (1.0 if p.grounded else m.air_control)
	var amount: float = (accel if axis else m.friction) * delta
	p.vx += clampf(axis * speed - p.vx, -amount, amount)
	if p.jump_buffer > 0 and p.coyote > 0:
		p.vy = -m.jump
		p.jump_buffer = 0.0
		p.coyote = 0.0
		p.grounded = false
	p.launch_timer = maxf(0, float(p.get("launch_timer", 0.0))-delta)
	if not intent.get("jump_held", true) and p.vy < -m.jump_cut and p.launch_timer == 0: p.vy = -m.jump_cut
	p.vy = minf(20, p.vy + m.gravity * delta)
	var steps := maxi(1, ceili(maxf(absf(p.vx), absf(p.vy)) * delta / .15))
	for substep in range(steps):
		for coord in ["x", "y"]:
			var velocity: String = "vx" if coord == "x" else "vy"
			var distance: float = p[velocity] * delta / steps
			if distance == 0: continue
			var old: float = p[coord]
			var destination := Vector2(old + distance, p.y) if coord == "x" else Vector2(p.x, old + distance)
			if not collides(destination, state):
				p[coord] = old + distance
			else:
				var low := 0.0
				var high := 1.0
				for iteration in range(12):
					var middle := (low + high) / 2.0
					var probe := Vector2(old + distance * middle, p.y) if coord == "x" else Vector2(p.x, old + distance * middle)
					if collides(probe, state): high = middle
					else: low = middle
				p[coord] = old + distance * low
				p[velocity] = 0.0
	p.grounded = p.vy >= 0 and collides(Vector2(p.x, p.y + .02), state)

	if p.grounded and state.tiles.get(Vector2i(floori(p.x), floori(p.y+m.height-.25)), "") == "spring":
		p.vy = -17.0
		p.grounded = false
		p.launch_timer = .6
