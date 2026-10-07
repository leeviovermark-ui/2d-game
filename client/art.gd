extends RefCounted
class_name ForgeArt
## Original procedural pixel artwork. No downloaded game assets.
var textures := {}

func icon(id: String, definition: Dictionary) -> Texture2D:
	if textures.has(id):
		return textures[id]
	var image := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	var c := Color(definition.get("color", "79888b"))
	var category: String = definition.get("category", "block")
	if category == "tool":
		for x in range(3, 12):
			pixel(image, x, 14-x+3, Color("8c6c47"))
			pixel(image, x+1, 14-x+3, Color("b19361"))
		for x in range(3, 15):
			pixel(image, x, 3+int(abs(x-8)/4.0), c)
			pixel(image, x, 4+int(abs(x-8)/4.0), c.darkened(.25))
	elif id == "core":
		for y in range(1, 15):
			for x in range(1, 15):
				if abs(x-8)+abs(y-7) < 7:
					pixel(image, x, y, c.lightened(.3) if x < 8 else c.darkened(.2))
		for y in range(4, 11):
			pixel(image, 8, y, Color("e8ebc4"))
	elif category == "seed" or id == "grain" or id == "fiber":
		for k in range(3):
			for y in range(5, 14):
				pixel(image, 5+k*3, y, c.darkened(.25))
			for y in range(3, 10, 2):
				pixel(image, 4+k*3, y, c)
				pixel(image, 6+k*3, y+1, c.lightened(.1))
	elif id == "torch":
		fill(image, Rect2i(7, 7, 2, 8), Color("8f7250"))
		fill(image, Rect2i(4, 3, 8, 7), c.darkened(.3))
		fill(image, Rect2i(6, 4, 4, 5), c.lightened(.3))
		fill(image, Rect2i(5, 2, 6, 1), Color("525759"))
	elif id == "bench":
		fill(image, Rect2i(1, 5, 14, 3), c)
		fill(image, Rect2i(3, 8, 2, 7), c.darkened(.25))
		fill(image, Rect2i(11, 8, 2, 7), c.darkened(.25))
		fill(image, Rect2i(5, 3, 4, 2), Color("9da6a1"))
	elif id == "chest":
		fill(image, Rect2i(1, 4, 14, 11), c.darkened(.25))
		fill(image, Rect2i(2, 5, 12, 8), c)
		fill(image, Rect2i(2, 8, 12, 1), c.darkened(.4))
		fill(image, Rect2i(7, 7, 2, 3), Color("e6c584"))
	elif id == "furnace":
		fill(image, Rect2i(2, 2, 12, 13), c.darkened(.2))
		fill(image, Rect2i(3, 3, 10, 4), c)
		fill(image, Rect2i(5, 8, 6, 5), Color("283334"))
		fill(image, Rect2i(6, 10, 4, 3), Color("dfac68"))
	elif id == "crop":
		for y in range(3, 16):
			pixel(image, 7, y, c)
			pixel(image, 10, y, c.darkened(.2))
		for y in range(2, 10, 2):
			fill(image, Rect2i(4, y, 4, 2), c.lightened(.2))
			fill(image, Rect2i(10, y+1, 3, 2), c)
	elif category == "material":
		for y in range(4, 13):
			for x in range(3, 14):
				if abs(x-8)+abs(y-8) < 8:
					pixel(image, x, y, c.lightened(.15) if y < 7 else c.darkened(.1))
	else:
		for y in range(16):
			for x in range(16):
				var n := posmod(x*37+y*73+x*y*11, 31)
				var shade := c.lightened(.09) if n < 6 else (c.darkened(.1) if n > 25 else c)
				if x == 0 or y == 15:
					shade = c.darkened(.18)
				if id == "grass" and y < 3:
					shade = Color("88a86b").darkened(y*.05)
				elif id == "grass" and y > 3:
					shade = Color("796144").darkened(float(n)/160.0)
				elif id in ["wood", "planks"]:
					if (x % 6 == 0 and id == "wood") or (y % 5 == 0 and id == "planks"):
						shade = c.darkened(.3)
				elif id == "brick" and (y % 8 == 0 or (x+int(y/8)*8) % 16 == 0):
					shade = c.darkened(.32)
				elif id.ends_with("ore") and n < 6:
					shade = Color("242c2f") if id == "coal_ore" else Color("ca9f74")
				elif id == "glass":
					shade.a = .55 if x > 1 and y > 1 else .85
				elif id == "leaves":
					shade.a = 0.0 if n < 4 else .92
				pixel(image, x, y, shade)
	var texture := ImageTexture.create_from_image(image)
	textures[id] = texture
	return texture

func pixel(image: Image, x: int, y: int, c: Color) -> void:
	if x >= 0 and y >= 0 and x < 16 and y < 16:
		image.set_pixel(x, y, c)

func fill(image: Image, rect: Rect2i, c: Color) -> void:
	for y in range(rect.position.y, rect.end.y):
		for x in range(rect.position.x, rect.end.x):
			pixel(image, x, y, c)
