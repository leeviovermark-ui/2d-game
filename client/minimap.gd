extends Control
## Cached terrain map with live multiplayer markers. Toggle with K.
var state: ForgeState
var dirty := true
var texture: ImageTexture
var map_area := Rect2(18,55,488,194)
var font: Font = preload("res://assets/fonts/DejaVuSans.ttf")

func _ready() -> void:
	size = Vector2(524,296)
	mouse_filter = Control.MOUSE_FILTER_STOP
	get_viewport().size_changed.connect(layout)
	layout()

func layout() -> void:
	var viewport := get_viewport().get_visible_rect().size
	size.x = minf(524,viewport.x-40)
	position = Vector2(viewport.x-size.x-20,110)
	map_area.size.x = size.x-36

func world_changed() -> void:
	dirty = true

func _process(_delta: float) -> void:
	if not visible: return
	if dirty:
		dirty = false
		var image := Image.create(state.width,state.height,false,Image.FORMAT_RGBA8)
		image.fill(Color("97d5da"))
		for tile in state.tiles:
			if tile.x >= 0 and tile.x < state.width and tile.y >= 0 and tile.y < state.height:
				var id: String = state.tiles[tile]
				image.set_pixel(tile.x,tile.y,Color(state.items.get(id,{}).get("color","7aa693")))
		texture = ImageTexture.create_from_image(image)
	queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and Rect2(size.x-40,8,32,32).has_point(event.position):
		hide()
		accept_event()

func _draw() -> void:
	draw_style_box(panel_style(),Rect2(Vector2.ZERO,size))
	draw_string(font,Vector2(18,30),state.meta.get("name","WORLD") + "  /  TERRAIN MAP",HORIZONTAL_ALIGNMENT_LEFT,-1,15,Color("effff2"))
	draw_string(font,Vector2(size.x-31,29),"×",HORIZONTAL_ALIGNMENT_LEFT,-1,22,Color("f8d98b"))
	if texture: draw_texture_rect(texture,map_area,false)
	for id in state.display_positions:
		var position: Vector2 = state.display_positions[id]
		var marker := map_area.position + Vector2(position.x/state.width,position.y/state.height) * map_area.size
		draw_circle(marker,5.0 if id==state.player_id else 3.5,Color("fff8aa") if id==state.player_id else Color("c67ef1"))
		if id==state.player_id: draw_arc(marker,7.5,0,TAU,20,Color("28665f"),1.5)
	draw_string(font,Vector2(18,272),"● You    ● Other explorers    ·    K to close",HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("cce7da"))

func panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color("154c55")
	style.border_color = Color("6dc1ac")
	style.set_border_width_all(1)
	style.set_corner_radius_all(12)
	return style
