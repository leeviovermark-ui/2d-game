extends Control
## Visible tiles only; decorative parallax has no gameplay or persistent state.
var state: ForgeState
var art: ForgeArt
var camera := Vector2.ZERO
var target := Vector2i(-1, -1)
var clock := 0.0
var particles: Array = []
var landing := true
const TILE := 32.0
var font: Font = preload("res://assets/fonts/DejaVuSans.ttf")

func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func _process(delta: float) -> void:
	clock += delta
	if state and state.display_positions.has(state.player_id):
		var pos: Vector2 = state.display_positions[state.player_id]
		var desired := Vector2(pos.x*TILE-size.x*.44, pos.y*TILE-size.y*.64)
		desired.x = clampf(desired.x, 0, maxf(0, state.width*TILE-size.x))
		desired.y = clampf(desired.y, 0, maxf(0, state.height*TILE-size.y))
		camera = camera.lerp(desired, 1.0-exp(-delta*9.0))
	elif landing:
		camera = Vector2(0, 105)
	for p in particles:
		p.life -= delta
		p.pos += p.velocity*delta
		p.velocity.y += 140*delta
	particles = particles.filter(func(p): return p.life > 0)
	queue_redraw()

func tile_at_mouse() -> Vector2i:
	return Vector2i(((get_local_mouse_position()+camera)/TILE).floor())

func burst(x: int, y: int, item: String) -> void:
	var c := Color(state.items.get(item, {}).get("color", "8a9a80"))
	for i in range(9):
		particles.append({"pos": Vector2(x+.5, y+.5)*TILE, "velocity": Vector2(randf_range(-65,65), randf_range(-110,-30)), "life": .6, "color": c})

func _draw() -> void:
	if not state:
		return
	var biome: String = state.meta.get("biome", "forest")
	var sky := Color("203c40") if biome == "forest" else (Color("464846") if biome == "desert" else Color("31464e"))
	draw_rect(Rect2(Vector2.ZERO, size), sky)
	# Calm sky; deliberate bands echo painted pixel landscapes.
	for i in range(12):
		draw_rect(Rect2(0, i*size.y/12.0, size.x, size.y/12.0+1), sky.lightened(i*.012))
	var sun := Vector2(size.x*.76-camera.x*.025, 116-camera.y*.035)
	draw_circle(sun, 43, Color(0.93,.88,.66,.045))
	draw_circle(sun, 32, Color(0.93,.88,.66,.08))
	draw_circle(sun, 23, Color("d9d6b0"))
	draw_circle(sun+Vector2(-8,-6), 22, sky)
	for i in range(24):
		var p := Vector2(posmod(i*197+59, int(size.x)), 35+posmod(i*83, 145))
		draw_rect(Rect2(p, Vector2(2,2)), Color(.8,.85,.73,.28))
	for i in range(5):
		var x := fposmod(i*330+110-camera.x*.07, size.x+250)-100
		var y := 83+posmod(i*39, 122)
		draw_rect(Rect2(x,y,110,4), Color(.64,.72,.65,.09))
		draw_rect(Rect2(x+20,y-5,60,5), Color(.64,.72,.65,.07))
	mountains(.045, size.y*.48, Color("385353"), 90, 31)
	mountains(.10, size.y*.60, Color("304d4b"), 95, 65)
	mountains(.18, size.y*.73, Color("284642"), 48, 17)
	for layer in range(2):
		var parallax := .20+layer*.17
		var base := size.y*(.82+layer*.05)-camera.y*.12
		for i in range(18):
			var x := float(i*117+posmod(i*49,70))-camera.x*parallax
			x = fposmod(x, size.x+220)-100
			var h := 90.0+posmod(i*51,105)
			tree(Vector2(x,base), h, Color("24443c") if layer == 0 else Color("203d34"))
	if landing:
		landing_ground()
	else:
		draw_tiles()
		for drop in state.drops.values():
			var pos := Vector2(drop.x,drop.y)*TILE-camera+Vector2(0,sin(clock*3+float(hash(drop.id)%6))*2)
			draw_circle(pos, 12, Color(.9,.82,.55,.10))
			draw_texture_rect(art.icon(drop.item,state.items[drop.item]), Rect2(pos-Vector2(9,9), Vector2(18,18)), false)
		for id in state.players:
			avatar(state.players[id], state.display_positions[id]*TILE-camera, id == state.player_id)
		if target.x >= 0 and target.y >= 0:
			var box := Rect2(Vector2(target)*TILE-camera, Vector2(TILE,TILE))
			var in_reach := false
			if state.players.has(state.player_id):
				var p: Dictionary = state.players[state.player_id]
				in_reach = Vector2(p.x,p.y+.7).distance_to(Vector2(target)+Vector2(.5,.5)) <= state.movement.reach
			var color := Color("d6cf97") if in_reach and state.can_build() else Color("a57769")
			draw_rect(box.grow(-1), Color(color, .09))
			for corner in [box.position, box.position+Vector2(26,0), box.position+Vector2(0,26), box.position+Vector2(26,26)]:
				draw_rect(Rect2(corner,Vector2(6,2)), color)
				draw_rect(Rect2(corner,Vector2(2,6)), color)
			if state.players.has(state.player_id) and state.players[state.player_id].mining:
				var m: Dictionary = state.players[state.player_id].mining
				var progress := clampf((state.now()-m.start)/m.duration,0,1)
				draw_rect(Rect2(box.position+Vector2(0,35),Vector2(32,3)), Color("122722"))
				draw_rect(Rect2(box.position+Vector2(0,35),Vector2(32*progress,3)), Color("e5c477"))
		for p in particles:
			draw_rect(Rect2(p.pos-camera,Vector2(3,3)), Color(p.color,p.life/.6))
	# Subtle foreground flecks; low density and low motion.
	for i in range(12):
		var x := fposmod(i*137+clock*(2+i%3), size.x)
		var y := size.y*.5+sin(clock*.3+i*8)*size.y*.22
		draw_rect(Rect2(x,y,2,2), Color(.85,.83,.49,.15+.12*sin(clock+i)))

func mountains(parallax: float, base: float, color: Color, amplitude: float, seed_value: int) -> void:
	var points := PackedVector2Array([Vector2(-20,size.y),Vector2(-20,base)])
	for x in range(-20,int(size.x)+41,20):
		var wx := x+camera.x*parallax
		var y := base-sin(wx*.005+seed_value)*amplitude-sin(wx*.012+seed_value)*amplitude*.4-camera.y*.055
		points.append(Vector2(x,round(y/3)*3))
	points.append(Vector2(size.x+40,size.y))
	draw_colored_polygon(points,color)

func tree(base: Vector2, h: float, color: Color) -> void:
	draw_rect(Rect2(base.x-3,base.y-h,6,h),color.darkened(.08))
	for j in range(4):
		var top := base.y-h+j*h*.16
		var half := 17+j*8
		draw_colored_polygon(PackedVector2Array([Vector2(base.x,top),Vector2(base.x-half,top+h*.36),Vector2(base.x+half,top+h*.36)]),color)

func landing_ground() -> void:
	var ground := size.y*.77
	draw_rect(Rect2(0,ground,size.x,size.y-ground),Color("453f32"))
	draw_rect(Rect2(0,ground,size.x,5),Color("739266"))
	for i in range(65):
		var x := i*26
		draw_rect(Rect2(x,ground-4-posmod(i*37,11),2,12),Color("8c9f67"))
	for i in range(4):
		tree(Vector2(75+i*130,ground),float(140+posmod(i*41,90)),Color("335e46"))
	var rect := Rect2(360,ground-120,160,120)
	draw_rect(rect,Color("786345"))
	for y in range(int(rect.position.y),int(ground),12):
		draw_line(Vector2(360,y),Vector2(520,y),Color("5d513b"),2)
	draw_colored_polygon(PackedVector2Array([Vector2(345,ground-120),Vector2(440,ground-167),Vector2(535,ground-120)]),Color("343f38"))
	draw_rect(Rect2(423,ground-63,34,63),Color("2b3730"))
	draw_rect(Rect2(379,ground-85,26,31),Color("dbb572"))
	draw_rect(Rect2(487,ground-85,20,31),Color("bdac70"))
	draw_line(Vector2(392,ground-85),Vector2(392,ground-54),Color("594f36"),3)
	for i in range(5):
		var p := Vector2(565+i*18,ground-14)
		draw_line(p,p+Vector2(0,-26),Color("a7aa69"),2)
		draw_rect(Rect2(p.x-3,p.y-30,7,11),Color("c1b16b"))

func draw_tiles() -> void:
	var low := Vector2i((camera/TILE).floor())
	var high := Vector2i(((camera+size)/TILE).ceil())
	for y in range(maxi(0,low.y),mini(state.height,high.y+1)):
		for x in range(maxi(0,low.x),mini(state.width,high.x+1)):
			var id: String = state.tiles.get(Vector2i(x,y), "")
			if id.is_empty():
				if y > 26:
					draw_rect(Rect2(Vector2(x,y)*TILE-camera,Vector2(TILE,TILE)),Color("293737"))
				continue
			var pos := (Vector2(x,y)*TILE-camera).round()
			var rect := Rect2(pos,Vector2(TILE,TILE))
			if id == "crop":
				var age := state.now()-float(state.crops.get(Vector2i(x,y),state.now()))
				var growth := clampf(age/90.0,.2,1)
				var height := 32*growth
				draw_texture_rect(art.icon(id,state.items[id]), Rect2(pos+Vector2(0,32-height),Vector2(32,height)),false, Color("b6b97c") if age < 90 else Color.WHITE)
			else:
				draw_texture_rect(art.icon(id,state.items[id]),rect,false)
				if id == "wood":
					draw_rect(rect.grow(-4),Color(.1,.13,.1,.15))
				if y > 26:
					draw_rect(rect,Color(0.025,.05,.05,minf(.6,(y-26)*.022)))
				if id == "torch" or id == "core" or id == "crystal":
					draw_circle(pos+Vector2(16,16),50 if id == "torch" else 27, Color(.92,.73,.4,.035) if id == "torch" else Color(.5,.84,.78,.04))
			if id == "grass" and not state.tiles.has(Vector2i(x,y-1)):
				for blade in range(3):
					var bx := pos.x+5+blade*10
					draw_line(Vector2(bx,pos.y),Vector2(bx-2,pos.y-4-posmod(x*7+blade,5)),Color("8ba770"),2)

func avatar(p: Dictionary, pos: Vector2, local: bool) -> void:
	pos = pos.round()
	var moving := absf(p.vx) > .1
	var step := sin(clock*13)*3 if moving else 0.0
	var facing := -1 if p.vx < -.1 else 1
	var accent := Color("d8b175") if local else Color("8eafbc")
	draw_ellipse_shadow(pos+Vector2(0,49))
	# Explorer silhouette: boots, trousers, sage coat, scarf, hair, tiny backpack.
	draw_rect(Rect2(pos+Vector2(-9,31+step),Vector2(7,16-step)),Color("273c3f"))
	draw_rect(Rect2(pos+Vector2(2,31-step),Vector2(7,16+step)),Color("314b4c"))
	draw_rect(Rect2(pos+Vector2(-10,45+step),Vector2(10,5)),Color("273032"))
	draw_rect(Rect2(pos+Vector2(1,45-step),Vector2(10,5)),Color("273032"))
	draw_rect(Rect2(pos+Vector2(-10,17),Vector2(20,20)),Color("6e9274") if local else Color("607e95"))
	draw_rect(Rect2(pos+Vector2(-13*facing-3,20),Vector2(6,16)),Color("856b4e"))
	draw_rect(Rect2(pos+Vector2(-9,23),Vector2(6,12)),Color("87a489") if local else Color("7996ac"))
	draw_rect(Rect2(pos+Vector2(5,24),Vector2(6,11)),Color("cbb48f"))
	draw_rect(Rect2(pos+Vector2(-7,3),Vector2(15,16)),Color("d4b993"))
	draw_rect(Rect2(pos+Vector2(-9,0),Vector2(18,7)),Color("494738"))
	draw_rect(Rect2(pos+Vector2(-9,5),Vector2(5,7)),Color("494738"))
	draw_rect(Rect2(pos+Vector2(facing*4,10),Vector2(2,3)),Color("273337"))
	draw_rect(Rect2(pos+Vector2(-9,17),Vector2(18,4)),accent)
	draw_rect(Rect2(pos+Vector2(-15-facing*3,19),Vector2(7,3)),accent.darkened(.14))
	if p.get("held"):
		var item: String = p.held
		var tool_pos := pos+Vector2(11,19)
		if p.get("mining"):
			tool_pos += Vector2(4*sin(clock*18),-5*absf(sin(clock*18)))
		draw_texture_rect(art.icon(item,state.items[item]),Rect2(tool_pos,Vector2(21,21)),false)
	var label: String = p.name + ("  ·  you" if local else "")
	var text_width := font.get_string_size(label,HORIZONTAL_ALIGNMENT_LEFT,-1,12).x
	draw_rect(Rect2(pos+Vector2(-text_width/2-7,-26),Vector2(text_width+14,20)),Color(.055,.10,.11,.86))
	draw_string(font,pos+Vector2(-text_width/2,-11),label,HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("e3e7d6"))

func draw_ellipse_shadow(pos: Vector2) -> void:
	draw_set_transform(pos,0,Vector2(1,.24))
	draw_circle(Vector2.ZERO,14,Color(0,0,0,.2))
	draw_set_transform(Vector2.ZERO)
