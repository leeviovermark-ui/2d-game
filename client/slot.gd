extends Button
## A real draggable slot; right-click splits half into an empty inventory slot.
signal dragged(from: int, to: int, count: int)
signal split_requested(from: int, count: int)
var index := 0
var stack
var definition := {}
var art: ForgeArt
var hotbar := false
var selected := false
var draggable := false
var splittable := false
var font: Font = preload("res://assets/fonts/DejaVuSans.ttf")

func _ready() -> void:
	custom_minimum_size = Vector2(58,58)
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND

func set_stack(value, defs: Dictionary) -> void:
	stack = value
	definition = defs.get(stack.id, {}) if stack else {}
	tooltip_text = (definition.get("name", "") + "\n" + definition.get("description", "") + ("\nRight-click to split" if splittable else "")) if stack else "Empty slot"
	queue_redraw()

func _draw() -> void:
	var box := Rect2(Vector2.ZERO,size)
	draw_rect(box,Color("1c2b2e") if not selected else Color("35413a"))
	draw_rect(box.grow(-.5),Color("c7b77f") if selected else (Color("758879") if is_hovered() else Color("3d4d4b")),false,2 if selected else 1)
	if stack and art:
		draw_texture_rect(art.icon(stack.id,definition),Rect2((size-Vector2(32,32))/2,Vector2(32,32)),false)
		if stack.n > 1:
			var n := str(int(stack.n))
			draw_string(font,Vector2(size.x-5-font.get_string_size(n,HORIZONTAL_ALIGNMENT_LEFT,-1,12).x,size.y-6),n,HORIZONTAL_ALIGNMENT_LEFT,-1,12,Color("e6e8d8"))
	if hotbar:
		draw_string(font,Vector2(5,14),str(index+1) if index < 9 else "0",HORIZONTAL_ALIGNMENT_LEFT,-1,10,Color("adbaac"))

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		if event.pressed and splittable and stack and stack.n > 1:
			split_requested.emit(index,ceili(stack.n/2.0))
			accept_event()

func _preview() -> Control:
	var preview := TextureRect.new()
	if stack:
		preview.texture = art.icon(stack.id,definition)
	preview.custom_minimum_size = Vector2(36,36)
	return preview

func _get_drag_data(_at: Vector2):
	if not stack or not draggable:
		return null
	set_drag_preview(_preview())
	return {"slot": index, "count": int(stack.n)}

func _can_drop_data(_at: Vector2, data) -> bool:
	return draggable and data is Dictionary and data.has("slot") and data.slot != index

func _drop_data(_at: Vector2, data) -> void:
	dragged.emit(data.slot,index,data.count)
