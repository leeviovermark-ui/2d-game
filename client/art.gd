extends RefCounted
class_name ForgeArt
## Original hand-shaped procedural pixel art, cached once per registry item.
var textures := {}

func icon(id: String, definition: Dictionary) -> Texture2D:
	if textures.has(id):
		return textures[id]
	var image := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	var c := Color(definition.get("color", "79888b"))
	var category: String = definition.get("category", "block")
	if category == "tool":
		tool(image, c, id == "crystal_pick")
	elif id == "core":
		fill(image, Rect2i(3, 13, 10, 3), Color("465c60"))
		fill(image, Rect2i(5, 12, 6, 1), Color("7c9b98"))
		diamond(image, Vector2i(8, 7), 6, c.darkened(.28))
		diamond(image, Vector2i(7, 6), 4, c.lightened(.17))
		fill(image, Rect2i(7, 3, 2, 7), Color("e2fff0"))
		pixel(image, 4, 5, Color("d2f0d5"))
	elif id in ["torch", "iron_lantern", "lumen_lamp"]:
		lantern(image, c, id)
	elif id in ["wood", "timber_beam"]:
		fill(image, Rect2i(4, 0, 8, 16), c.darkened(.32))
		fill(image, Rect2i(5, 0, 6, 16), c)
		fill(image, Rect2i(6, 0, 2, 16), c.lightened(.18))
		fill(image, Rect2i(10, 0, 1, 16), c.darkened(.16))
		for y in [3, 11]:
			fill(image, Rect2i(7, y, 3, 1), c.darkened(.30))
			pixel(image, 9, y + 1, c.darkened(.30))
		if id == "timber_beam":
			for y in [1, 12]:
				fill(image, Rect2i(3, y, 10, 3), Color("586a6d"))
				fill(image, Rect2i(4, y, 8, 1), Color("9aa6a1"))
	elif id in ["leaves", "hedge"]:
		foliage(image, c, id == "hedge")
	elif id == "flower_pot":
		fill(image, Rect2i(4, 11, 8, 2), Color("c18a62"))
		fill(image, Rect2i(5, 13, 6, 3), Color("986644"))
		fill(image, Rect2i(7, 5, 2, 7), Color("668d58"))
		fill(image, Rect2i(4, 7, 3, 2), Color("91af67"))
		fill(image, Rect2i(9, 8, 3, 2), Color("71935f"))
		for offset in [Vector2i(-2, 0), Vector2i(2, 0), Vector2i(0, -2), Vector2i(0, 2)]:
			fill(image, Rect2i(Vector2i(7, 4) + offset, Vector2i(2, 2)), c)
		fill(image, Rect2i(7, 4, 2, 2), Color("f2d17e"))
	elif category == "seed" or id in ["grain", "fiber", "crop"]:
		plant(image, c, id)
	elif id == "bench" or id == "table":
		fill(image, Rect2i(1, 6, 14, 3), c.darkened(.25))
		fill(image, Rect2i(1, 5, 14, 2), c.lightened(.15))
		fill(image, Rect2i(3, 9, 2, 7), c.darkened(.30))
		fill(image, Rect2i(11, 9, 2, 7), c.darkened(.12))
		fill(image, Rect2i(4, 12, 7, 1), c.darkened(.27))
		if id == "bench":
			fill(image, Rect2i(5, 3, 4, 2), Color("9da6a1"))
			fill(image, Rect2i(11, 2, 2, 3), Color("697e83"))
		else:
			fill(image, Rect2i(7, 3, 3, 2), Color("ded6ac"))
	elif id == "chair":
		fill(image, Rect2i(3, 2, 2, 14), c.darkened(.20))
		fill(image, Rect2i(4, 2, 7, 2), c.lightened(.13))
		fill(image, Rect2i(9, 3, 2, 7), c)
		fill(image, Rect2i(4, 5, 5, 2), c)
		fill(image, Rect2i(3, 9, 10, 3), c)
		fill(image, Rect2i(4, 9, 8, 1), c.lightened(.24))
		fill(image, Rect2i(11, 12, 2, 4), c.darkened(.16))
	elif id == "bookshelf":
		fill(image, Rect2i(1, 1, 14, 15), c.darkened(.35))
		fill(image, Rect2i(2, 2, 12, 12), Color("3f3e35"))
		for y in [3, 9]:
			for x in range(3, 13, 2):
				var book := Color("789b91") if x % 3 == 0 else (Color("c59667") if x % 3 == 1 else Color("977c9f"))
				fill(image, Rect2i(x, y + x % 2, 1, 4 - x % 2), book)
				pixel(image, x, y + 2, Color("d8cb9e"))
		for y in [1, 7, 14]:
			fill(image, Rect2i(1, y, 14, 2), c)
			fill(image, Rect2i(2, y, 12, 1), c.lightened(.18))
	elif id in ["tapestry", "rug"]:
		var top := 2 if id == "tapestry" else 12
		var height := 12 if id == "tapestry" else 3
		fill(image, Rect2i(2, top, 12, height), c.darkened(.3))
		fill(image, Rect2i(3, top + 1, 10, height - 2), c)
		if id == "tapestry":
			diamond(image, Vector2i(8, 8), 3, Color("e5c681"))
			fill(image, Rect2i(1, 1, 14, 1), Color("ab8b5c"))
		for x in range(3, 14, 2):
			pixel(image, x, top + height, Color("d9bc7b"))
	elif id == "chest":
		fill(image, Rect2i(1, 4, 14, 11), c.darkened(.32))
		fill(image, Rect2i(2, 5, 12, 9), c)
		fill(image, Rect2i(2, 5, 12, 1), c.lightened(.24))
		fill(image, Rect2i(2, 8, 12, 1), c.darkened(.4))
		for x in [3, 11]:
			fill(image, Rect2i(x, 5, 2, 9), Color("647477"))
			pixel(image, x, 6, Color("a6b0a6"))
		fill(image, Rect2i(7, 7, 2, 4), Color("e6c584"))
		pixel(image, 8, 9, Color("685342"))
	elif id == "furnace":
		fill(image, Rect2i(2, 2, 12, 14), c.darkened(.35))
		fill(image, Rect2i(3, 3, 10, 4), c)
		fill(image, Rect2i(3, 3, 10, 1), c.lightened(.23))
		fill(image, Rect2i(4, 8, 8, 6), Color("283334"))
		fill(image, Rect2i(5, 10, 6, 3), Color("cc7d47"))
		fill(image, Rect2i(7, 9, 2, 3), Color("f3d084"))
		fill(image, Rect2i(3, 14, 10, 1), c.lightened(.14))
	elif category == "material":
		if id == "iron":
			fill(image, Rect2i(2, 6, 12, 6), c.darkened(.32))
			fill(image, Rect2i(3, 5, 10, 5), c)
			fill(image, Rect2i(4, 4, 8, 2), c.lightened(.26))
		else:
			diamond(image, Vector2i(8, 9), 6, c.darkened(.3))
			diamond(image, Vector2i(7, 7), 4, c)
			fill(image, Rect2i(5, 5, 3, 2), c.lightened(.23))
	else:
		block(image, c, id)
	var texture := ImageTexture.create_from_image(image)
	textures[id] = texture
	return texture

func block(image: Image, c: Color, id: String) -> void:
	image.fill(c)
	if id in ["glass", "reinforced_glass"]:
		image.fill(Color(c, .19))
		frame(image, Rect2i(0, 0, 16, 16), Color(c.lightened(.14), .88))
		fill(image, Rect2i(2, 2, 1, 11), Color(Color("d1ebe0"), .6))
		for x in range(4, 12):
			pixel(image, x, 13 - x, Color(Color("e2f7e9"), .5))
		if id == "reinforced_glass":
			fill(image, Rect2i(7, 0, 2, 16), Color("8caaa9"))
			fill(image, Rect2i(0, 7, 16, 2), Color("8caaa9"))
		return
	if id == "platform":
		# Collision occupies a complete tile; the open brace shows its true footprint.
		image.fill(Color.TRANSPARENT)
		fill(image, Rect2i(0, 0, 16, 4), c)
		fill(image, Rect2i(0, 0, 16, 1), c.lightened(.28))
		for x in range(16):
			pixel(image, x, 4 + int(x / 2.0), c.darkened(.25))
		fill(image, Rect2i(1, 3, 2, 13), c.darkened(.2))
		fill(image, Rect2i(13, 3, 2, 13), c.darkened(.2))
		return
	if id.ends_with("planks"):
		for y in [0, 5, 10, 15]:
			fill(image, Rect2i(0, y, 16, 1), c.darkened(.31))
			if y < 15:
				fill(image, Rect2i(0, y + 1, 16, 1), c.lightened(.13))
				fill(image, Rect2i((y * 3 + 4) % 14, y, 1, 5), c.darkened(.31))
		for y in [3, 8, 13]:
			fill(image, Rect2i((y * 5) % 7, y, 5, 1), c.darkened(.10))
		return
	if id in ["brick", "moss_brick", "slate_brick", "sandstone_brick", "marble", "terracotta"]:
		for y in [0, 8]:
			fill(image, Rect2i(0, y, 16, 1), c.darkened(.37))
			fill(image, Rect2i(0, y + 1, 16, 1), c.lightened(.15))
			var seam := 7 if y == 0 else 1
			fill(image, Rect2i(seam, y, 1, 8), c.darkened(.34))
			fill(image, Rect2i(seam + 1, y + 1, 1, 6), c.lightened(.08))
		fill(image, Rect2i(0, 15, 16, 1), c.darkened(.18))
		if id == "moss_brick":
			for x in [1, 4, 10, 13]:
				fill(image, Rect2i(x, (x * 3) % 11, 3, 2), Color("698b5c"))
		elif id == "marble":
			for x in range(16):
				pixel(image, x, 3 + int(sin(x * .45) * 2), Color("a5b7b4"))
				pixel(image, x, 11 + int(sin(x * .35) * 2), Color("abb8b0"))
		return
	if id in ["dirt", "grass", "sand", "snow"]:
		var base := Color("806448") if id == "grass" else c
		image.fill(base)
		for y in [5, 11, 14]:
			for x in range((y * 3) % 5, 15, 6):
				fill(image, Rect2i(x, y, 2, 1), base.darkened(.17))
				pixel(image, x + 1, y - 1, base.lightened(.12))
		if id == "grass":
			fill(image, Rect2i(0, 0, 16, 2), Color("92b574"))
			fill(image, Rect2i(0, 2, 16, 2), c)
			for x in [1, 6, 11]:
				fill(image, Rect2i(x, 3, 3, 2), c.darkened(.15))
		elif id == "sand":
			for y in [2, 8, 13]:
				fill(image, Rect2i(y % 4, y, 10, 1), c.lightened(.12))
		elif id == "snow":
			fill(image, Rect2i(0, 0, 16, 3), Color("e3efe6"))
			fill(image, Rect2i(1, 3, 9, 1), Color("d2e4df"))
			fill(image, Rect2i(4, 10, 11, 1), c.darkened(.12))
		return
	# Angular cut-rock strata, with ore facets embedded in the stone.
	image.fill(Color("73818a") if id.ends_with("ore") or id == "crystal" else c)
	var rock := Color("73818a") if id.ends_with("ore") or id == "crystal" else c
	for y in [3, 9, 14]:
		var x: int = (y * 5) % 7
		fill(image, Rect2i(x, y, 8, 1), rock.darkened(.19))
		fill(image, Rect2i(x + 1, y - 1, 5, 1), rock.lightened(.1))
		pixel(image, x + 8, y + 1, rock.darkened(.19))
	if id.ends_with("ore"):
		for p in [Vector2i(4, 5), Vector2i(11, 10), Vector2i(5, 13)]:
			diamond(image, p, 2, c.darkened(.15))
			pixel(image, p.x - 1, p.y - 1, c.lightened(.25))
	elif id == "crystal":
		for p in [Vector2i(5, 6), Vector2i(11, 10)]:
			diamond(image, p, 4, c.darkened(.25))
			diamond(image, p - Vector2i(1, 1), 2, c.lightened(.26))
			pixel(image, p.x, p.y - 3, Color("e6fff3"))

func foliage(image: Image, c: Color, hedge: bool) -> void:
	if hedge:
		fill(image, Rect2i(1, 3, 14, 12), c.darkened(.25))
	for center in [Vector2i(5, 5), Vector2i(10, 4), Vector2i(4, 10), Vector2i(11, 10), Vector2i(8, 12)]:
		diamond(image, center, 5, c.darkened(.17))
		diamond(image, center - Vector2i(1, 1), 3, c)
		fill(image, Rect2i(center.x - 2, center.y - 2, 3, 1), c.lightened(.20))
	for p in [Vector2i(2, 7), Vector2i(8, 8), Vector2i(12, 12)]:
		fill(image, Rect2i(p, Vector2i(2, 2)), c.darkened(.33))

func plant(image: Image, c: Color, id: String) -> void:
	if id == "seed":
		for p in [Vector2i(5, 6), Vector2i(10, 9), Vector2i(5, 12)]:
			diamond(image, p, 2, c.darkened(.16))
			pixel(image, p.x, p.y - 1, c.lightened(.25))
		return
	for k in range(3):
		var x := 4 + k * 4
		fill(image, Rect2i(x, 4 + k % 2, 1, 12), Color("84965b") if id != "fiber" else c.darkened(.26))
		for y in range(3 + k % 2, 10, 2):
			fill(image, Rect2i(x - 2, y, 2, 1), c.lightened(.20))
			fill(image, Rect2i(x + 1, y + 1, 2, 1), c)
		pixel(image, x - 1, 12, Color("9eb173"))
	if id == "grain" or id == "fiber":
		fill(image, Rect2i(3, 11, 10, 2), Color("997a50"))

func lantern(image: Image, c: Color, id: String) -> void:
	var frame_color := Color("546c70") if id != "torch" else Color("6a5946")
	fill(image, Rect2i(6, 0, 4, 2), frame_color)
	fill(image, Rect2i(7, 1, 2, 3), frame_color.lightened(.25))
	fill(image, Rect2i(3, 4, 10, 9), frame_color)
	fill(image, Rect2i(5, 5, 6, 7), c.darkened(.15))
	fill(image, Rect2i(6, 6, 4, 5), c.lightened(.22))
	fill(image, Rect2i(7, 7, 2, 3), Color("edf5c6") if id == "lumen_lamp" else Color("fff0b1"))
	fill(image, Rect2i(4, 3, 8, 2), frame_color.lightened(.13))
	fill(image, Rect2i(4, 13, 8, 2), frame_color.lightened(.12))
	if id == "iron_lantern":
		fill(image, Rect2i(7, 5, 1, 8), frame_color)
	elif id == "lumen_lamp":
		diamond(image, Vector2i(8, 8), 3, c.lightened(.35))

func tool(image: Image, c: Color, crystal: bool) -> void:
	for x in range(3, 12):
		pixel(image, x, 17 - x, Color("6d543e"))
		pixel(image, x + 1, 17 - x, Color("b99564"))
	for x in range(2, 15):
		var y := 3 + int(abs(x - 8) / 3.0)
		pixel(image, x, y, c.lightened(.22))
		pixel(image, x, y + 1, c)
		pixel(image, x, y + 2, c.darkened(.3))
	fill(image, Rect2i(8, 5, 2, 3), Color("d4c491"))
	if crystal:
		diamond(image, Vector2i(4, 5), 2, Color("c2f0e2"))
		diamond(image, Vector2i(12, 5), 2, Color("c2f0e2"))

func diamond(image: Image, center: Vector2i, radius: int, c: Color) -> void:
	for y in range(center.y - radius, center.y + radius + 1):
		for x in range(center.x - radius, center.x + radius + 1):
			if absi(x - center.x) + absi(y - center.y) <= radius:
				pixel(image, x, y, c)

func frame(image: Image, rect: Rect2i, c: Color) -> void:
	fill(image, Rect2i(rect.position, Vector2i(rect.size.x, 1)), c)
	fill(image, Rect2i(rect.position.x, rect.end.y - 1, rect.size.x, 1), c)
	fill(image, Rect2i(rect.position, Vector2i(1, rect.size.y)), c)
	fill(image, Rect2i(rect.end.x - 1, rect.position.y, 1, rect.size.y), c)

func pixel(image: Image, x: int, y: int, c: Color) -> void:
	if x >= 0 and y >= 0 and x < 16 and y < 16:
		image.set_pixel(x, y, c)

func fill(image: Image, rect: Rect2i, c: Color) -> void:
	for y in range(rect.position.y, rect.end.y):
		for x in range(rect.position.x, rect.end.x):
			pixel(image, x, y, c)
