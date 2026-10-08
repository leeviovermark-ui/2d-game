extends RefCounted
class_name ForgeArt
## Original hand-shaped procedural pixel art, cached once per registry item.
var textures := {}

func icon(id: String, definition: Dictionary) -> Texture2D:
	if textures.has(id):
		return textures[id]
	if definition.has("texture"):
		var detailed := detailed_icon(id, definition)
		var cached := ImageTexture.create_from_image(detailed)
		textures[id] = cached
		return cached
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
	image.resize(32, 32, Image.INTERPOLATE_NEAREST)
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
	if x >= 0 and y >= 0 and x < image.get_width() and y < image.get_height():
		image.set_pixel(x, y, c)

func fill(image: Image, rect: Rect2i, c: Color) -> void:
	for y in range(rect.position.y, rect.end.y):
		for x in range(rect.position.x, rect.end.x):
			pixel(image, x, y, c)

func detailed_icon(id: String, definition: Dictionary) -> Image:
	var image := Image.create(32, 32, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	var c := Color(definition.get("color", "9aaca5"))
	var style: String = definition.get("texture", "rock")
	if style in ["rock", "ore", "gem_rock", "brick", "cobble", "mosaic", "planks", "glass", "tile", "metal", "grate", "beam", "water", "soil", "turf", "sand", "snow", "marble"]:
		detailed_block(image, c, style, id)
	elif definition.get("category", "") == "apparel":
		wardrobe(image, c, style)
	elif definition.get("category", "") == "crop":
		crop_sprite(image, c, style)
	elif definition.get("category", "") == "food":
		food_sprite(image, c, style)
	elif style in ["ingot", "cloth", "rope", "paper", "bottle", "seed", "pearl"]:
		material_sprite(image, c, style)
	elif style in ["kiln", "loom", "cooking_pot", "crystal_press"]:
		station_sprite(image, c, style)
	elif style == "pick":
		var small := Image.create(16, 16, false, Image.FORMAT_RGBA8)
		small.fill(Color.TRANSPARENT)
		tool(small, c, id == "amethyst_pick")
		small.resize(32, 32, Image.INTERPOLATE_NEAREST)
		image = small
	elif style == "fishing_rod":
		stroke(image, Vector2i(7, 28), Vector2i(18, 3), c.darkened(.25), 3)
		stroke(image, Vector2i(8, 27), Vector2i(19, 3), c.lightened(.12))
		stroke(image, Vector2i(20, 3), Vector2i(27, 9), Color("dfeee1"))
		stroke(image, Vector2i(27, 9), Vector2i(27, 24), Color("dfeee1"))
		fill(image, Rect2i(25, 24, 3, 2), Color("a6cad3"))
		disc(image, Vector2i(11, 20), 3, Color("698c9b"))
	else:
		decor_sprite(image, c, style)
	return image

func detailed_block(image: Image, c: Color, style: String, id: String) -> void:
	image.fill(c)
	var rng := RandomNumberGenerator.new()
	rng.seed = absi(hash(id))
	if style in ["soil", "turf", "sand", "snow"]:
		var earth := Color("997250") if style == "turf" else c
		image.fill(earth)
		for i in range(35):
			var x := rng.randi_range(0, 31)
			var y := rng.randi_range(2, 31)
			fill(image, Rect2i(x, y, 2 if i % 3 else 3, 1), earth.lightened(rng.randf_range(-.15, .18)))
		if style == "turf":
			fill(image, Rect2i(0, 0, 32, 3), Color("b6d982"))
			fill(image, Rect2i(0, 3, 32, 4), c)
			for x in range(1, 32, 5):
				fill(image, Rect2i(x, 6, 3, 1 + x % 3), c.darkened(.1))
		elif style == "snow":
			fill(image, Rect2i(0, 0, 32, 5), Color("f5fff6"))
			stroke(image, Vector2i(2, 7), Vector2i(15, 8), Color("e7f8f2"))
			stroke(image, Vector2i(15, 23), Vector2i(29, 23), c.darkened(.08))
		elif style == "sand":
			for y in [4, 13, 24]:
				stroke(image, Vector2i(y % 7, y), Vector2i(20 + y % 4, y + 1), c.lightened(.1))
		return
	if style == "marble":
		image.fill(c)
		for line in [7, 23]:
			for x in range(32):
				pixel(image, x, line + int(sin(x * .21) * 3), c.darkened(.18))
				pixel(image, x, line + int(sin(x * .21) * 3) + 1, c.lightened(.07))
		return
	if style == "glass":
		image.fill(Color(c, .18))
		frame(image, Rect2i(0, 0, 32, 32), Color(c, .84))
		frame(image, Rect2i(1, 1, 30, 30), Color(c.lightened(.2), .36))
		stroke(image, Vector2i(5, 20), Vector2i(20, 5), Color("effffc", .54), 2)
		stroke(image, Vector2i(10, 26), Vector2i(27, 9), Color("effffc", .24))
		fill(image, Rect2i(3, 3, 1, 21), Color("f4fff3", .6))
		if id == "reinforced_glass":
			fill(image, Rect2i(15, 0, 2, 32), Color("91b5bd"))
			fill(image, Rect2i(0, 15, 32, 2), Color("91b5bd"))
		return
	if style == "water":
		image.fill(Color(c, .60))
		fill(image, Rect2i(0, 0, 32, 2), Color("c3f6ff", .86))
		for y in [8, 17, 26]:
			fill(image, Rect2i(posmod(y * 3, 13), y, 12, 1), Color("d2fbff", .38))
			fill(image, Rect2i(posmod(y, 9), y + 2, 7, 1), Color("3389b5", .24))
		return
	if style == "planks":
		for y in range(0, 32, 8):
			fill(image, Rect2i(0, y, 32, 1), c.darkened(.29))
			fill(image, Rect2i(0, y + 1, 32, 1), c.lightened(.2))
			var seam := posmod(y * 3 + 9, 27)
			fill(image, Rect2i(seam, y, 1, 8), c.darkened(.27))
			fill(image, Rect2i(seam + 2, y + 3, 4, 1), c.darkened(.12))
			fill(image, Rect2i(4, y + 5, 11, 1), c.lightened(.075))
		return
	if style in ["brick", "cobble", "mosaic", "tile"]:
		image.fill(c.darkened(.3))
		var row_height := 8 if style == "cobble" else (16 if style == "tile" else 11)
		var width := 9 if style in ["mosaic", "cobble"] else (16 if style == "tile" else 19)
		for y in range(0, 32, row_height):
			var shift := 0 if style == "tile" else (width / 2 if (y / row_height) % 2 == 1 else 0)
			for x in range(-width, 33, width):
				var face := c.lightened(rng.randf_range(-.08, .1))
				fill(image, Rect2i(x + shift + 1, y + 1, width - 1, row_height - 1), face)
				fill(image, Rect2i(x + shift + 2, y + 1, width - 3, 1), face.lightened(.2))
				fill(image, Rect2i(x + shift + 1, y + 2, 1, row_height - 3), face.lightened(.1))
				fill(image, Rect2i(x + shift + 2, y + row_height - 1, width - 2, 1), face.darkened(.12))
				if style == "mosaic":
					diamond(image, Vector2i(x + shift + width / 2, y + row_height / 2), 2, c.lightened(.25))
		if id == "moss_brick":
			for x in [2, 10, 23, 28]:
				fill(image, Rect2i(x, (x * 3) % 25, 4, 2), Color("78b273"))
		return
	if style in ["metal", "grate", "beam"]:
		image.fill(Color.TRANSPARENT if style == "grate" else c.darkened(.12))
		if style == "grate":
			for k in range(0, 32, 8):
				fill(image, Rect2i(k, 0, 2, 32), c.darkened(.2))
				fill(image, Rect2i(0, k, 32, 2), c)
		elif style == "beam":
			fill(image, Rect2i(6, 0, 20, 32), c.darkened(.26))
			fill(image, Rect2i(0, 0, 32, 5), c)
			fill(image, Rect2i(0, 27, 32, 5), c)
			stroke(image, Vector2i(7, 5), Vector2i(24, 26), c, 3)
		else:
			fill(image, Rect2i(2, 2, 28, 28), c)
			fill(image, Rect2i(2, 2, 28, 2), c.lightened(.18))
		for p in [Vector2i(3, 3), Vector2i(28, 3), Vector2i(3, 28), Vector2i(28, 28)]:
			disc(image, p, 1, c.darkened(.3))
			pixel(image, p.x, p.y - 1, c.lightened(.24))
		return
	var rock := Color("96a4b0") if style in ["ore", "gem_rock"] else c
	image.fill(rock)
	for i in range(27):
		var p := Vector2i(rng.randi_range(1, 30), rng.randi_range(1, 30))
		fill(image, Rect2i(p, Vector2i(rng.randi_range(1, 4), 1)), rock.lightened(rng.randf_range(-.18, .16)))
	for y in [4, 14, 25]:
		var x := posmod(y * 3, 9)
		stroke(image, Vector2i(x, y), Vector2i(x + 16, y + 1), rock.darkened(.18))
		stroke(image, Vector2i(x + 3, y - 1), Vector2i(x + 15, y - 1), rock.lightened(.10))
	if style in ["ore", "gem_rock"]:
		for center in [Vector2i(8, 9), Vector2i(24, 14), Vector2i(11, 25)]:
			var radius := 5 if style == "gem_rock" else 3
			diamond(image, center, radius, c.darkened(.15))
			diamond(image, center - Vector2i(1, 1), radius - 2, c.lightened(.25))
			pixel(image, center.x - 1, center.y - radius + 1, Color("f8fff5"))

func crop_sprite(image: Image, c: Color, style: String) -> void:
	var leaf := Color("7fb96b")
	if style == "carrot_crop":
		for x in [7, 16, 25]:
			stroke(image, Vector2i(x, 29), Vector2i(x - 2, 15), leaf.darkened(.18), 2)
			for offset in [-6, 0, 6]:
				stroke(image, Vector2i(x, 21), Vector2i(x + offset, 10 - absi(offset) / 2), leaf, 2)
			fill(image, Rect2i(x - 2, 27, 5, 4), c)
	else:
		for p in [Vector2i(9, 19), Vector2i(19, 15), Vector2i(24, 23)]:
			disc(image, p, 7, leaf.darkened(.18))
			disc(image, p - Vector2i(2, 2), 5, leaf)
			var radius := 3 if style == "tomato_crop" else 2
			disc(image, p, radius, c.darkened(.15))
			disc(image, p - Vector2i(1, 1), radius - 1, c.lightened(.16))
		stroke(image, Vector2i(15, 31), Vector2i(15, 12), leaf.darkened(.22), 2)
		stroke(image, Vector2i(15, 24), Vector2i(26, 12), leaf.darkened(.1))

func material_sprite(image: Image, c: Color, style: String) -> void:
	match style:
		"ingot":
			fill(image, Rect2i(4, 13, 25, 12), c.darkened(.25))
			fill(image, Rect2i(6, 8, 20, 12), c)
			fill(image, Rect2i(9, 6, 14, 4), c.lightened(.22))
			fill(image, Rect2i(7, 10, 18, 1), c.lightened(.15))
		"cloth", "paper":
			fill(image, Rect2i(5, 5, 22, 24), c.darkened(.25))
			fill(image, Rect2i(6, 4, 19, 23), c)
			fill(image, Rect2i(8, 5, 17, 1), c.lightened(.2))
			for y in range(9, 25, 4):
				fill(image, Rect2i(9, y, 12, 1), c.darkened(.12))
			if style == "cloth":
				for x in range(7, 25, 3):
					fill(image, Rect2i(x, 26, 1, 3), c.lightened(.14))
		"rope":
			for radius in [11, 8, 5]:
				ring(image, Vector2i(15, 17), radius, c.darkened(.2), 2)
				ring(image, Vector2i(15, 16), radius, c, 1)
			stroke(image, Vector2i(26, 17), Vector2i(27, 29), c.lightened(.18), 2)
		"bottle":
			fill(image, Rect2i(12, 2, 8, 5), Color("b99665"))
			fill(image, Rect2i(12, 6, 8, 6), Color(c, .62))
			fill(image, Rect2i(7, 11, 18, 19), Color(c, .44))
			frame(image, Rect2i(7, 11, 18, 19), c)
			fill(image, Rect2i(10, 13, 2, 13), Color("f0fff8", .8))
			fill(image, Rect2i(9, 23, 14, 5), Color(c.lightened(.14), .75))
		"seed":
			for p in [Vector2i(9, 11), Vector2i(22, 17), Vector2i(10, 25)]:
				diamond(image, p, 4, c.darkened(.15))
				fill(image, Rect2i(p - Vector2i(1, 2), Vector2i(2, 2)), c.lightened(.25))
		"pearl":
			disc(image, Vector2i(16, 17), 10, c.darkened(.18))
			disc(image, Vector2i(15, 15), 8, c)
			disc(image, Vector2i(12, 12), 3, Color("fafffa"))
			stroke(image, Vector2i(13, 25), Vector2i(22, 23), Color("b9ddd6"))

func food_sprite(image: Image, c: Color, style: String) -> void:
	match style:
		"carrot":
			for x in [10, 15, 20]:
				stroke(image, Vector2i(16, 10), Vector2i(x, 2), Color("91bd6d"), 2)
			for y in range(9, 29):
				var half := int((29 - y) * .3)
				fill(image, Rect2i(16 - half, y, half * 2 + 1, 1), c)
			stroke(image, Vector2i(13, 12), Vector2i(16, 25), c.lightened(.22))
		"tomato", "berry":
			for p in ([Vector2i(16, 18)] if style == "tomato" else [Vector2i(10, 19), Vector2i(20, 19), Vector2i(15, 11)]):
				disc(image, p, 10 if style == "tomato" else 6, c.darkened(.15))
				disc(image, p - Vector2i(2, 2), 7 if style == "tomato" else 4, c)
				fill(image, Rect2i(p - Vector2i(4, 4), Vector2i(3, 2)), c.lightened(.3))
			stroke(image, Vector2i(14, 8), Vector2i(18, 4), Color("7bab62"), 2)
			stroke(image, Vector2i(16, 8), Vector2i(8, 7), Color("7bab62"), 2)
		"trout", "baked_trout":
			disc(image, Vector2i(15, 17), 8, c.darkened(.2))
			fill(image, Rect2i(6, 12, 18, 9), c)
			fill(image, Rect2i(7, 14, 16, 2), c.lightened(.25))
			for y in range(10, 25):
				fill(image, Rect2i(25, y, 1 + absi(17 - y) / 2, 1), c)
			pixel(image, 8, 15, Color("263c4b"))
			if style == "baked_trout":
				for x in [11, 16, 21]:
					stroke(image, Vector2i(x, 14), Vector2i(x - 2, 20), c.darkened(.3))
		"vegetable_stew":
			disc(image, Vector2i(16, 15), 11, Color("70645d"))
			disc(image, Vector2i(16, 13), 9, c)
			for p in [Vector2i(11, 11), Vector2i(19, 13), Vector2i(16, 8)]:
				fill(image, Rect2i(p, Vector2i(3, 2)), Color("f1c17e"))
			fill(image, Rect2i(12, 25, 9, 2), Color("928678"))
		_:
			disc(image, Vector2i(16, 19), 11, Color("bf8d60"))
			fill(image, Rect2i(5, 16, 23, 10), Color("ce9d67"))
			disc(image, Vector2i(16, 15), 10, c)
			if style == "berry_pie":
				for x in [9, 15, 21]:
					stroke(image, Vector2i(x, 8), Vector2i(x + 4, 23), Color("ebcc98"), 2)
			else:
				for x in [9, 15, 21]:
					stroke(image, Vector2i(x, 10), Vector2i(x + 2, 16), c.lightened(.3), 2)

func station_sprite(image: Image, c: Color, style: String) -> void:
	if style in ["kiln", "cooking_pot"]:
		fill(image, Rect2i(3, 16, 27, 16), Color("8b7770"))
		fill(image, Rect2i(4, 15, 25, 3), Color("a89887"))
		fill(image, Rect2i(9, 22, 15, 8), Color("443d3d"))
		fill(image, Rect2i(11, 26, 11, 3), Color("ec9b59"))
		fill(image, Rect2i(16, 23, 4, 5), Color("ffdf94"))
		if style == "kiln":
			fill(image, Rect2i(6, 4, 22, 13), c)
			fill(image, Rect2i(9, 1, 15, 4), c.lightened(.15))
			fill(image, Rect2i(11, 7, 12, 6), Color("594d4a"))
		else:
			disc(image, Vector2i(16, 12), 10, c.darkened(.4))
			fill(image, Rect2i(6, 7, 21, 4), Color("c7d0c7"))
			fill(image, Rect2i(3, 12, 5, 3), Color("aab8b9"))
			fill(image, Rect2i(25, 12, 5, 3), Color("aab8b9"))
	elif style == "loom":
		fill(image, Rect2i(4, 2, 3, 30), c.darkened(.2))
		fill(image, Rect2i(25, 2, 3, 30), c.darkened(.2))
		fill(image, Rect2i(3, 2, 26, 3), c)
		fill(image, Rect2i(3, 25, 26, 3), c)
		for x in range(9, 25, 3):
			fill(image, Rect2i(x, 5, 1, 23), Color("e6dab7"))
		fill(image, Rect2i(8, 13, 17, 11), Color("a3c5cf"))
		for y in range(14, 24, 3):
			fill(image, Rect2i(8, y, 17, 1), Color("d5e5da"))
	else:
		fill(image, Rect2i(3, 26, 27, 6), Color("82969f"))
		fill(image, Rect2i(5, 2, 4, 25), Color("9caeb7"))
		fill(image, Rect2i(24, 2, 4, 25), Color("6f8794"))
		fill(image, Rect2i(6, 2, 21, 4), Color("bccdd3"))
		diamond(image, Vector2i(16, 17), 7, c)
		diamond(image, Vector2i(15, 15), 4, c.lightened(.3))
		fill(image, Rect2i(13, 6, 7, 3), Color("d4dad0"))

func wardrobe(image: Image, c: Color, style: String) -> void:
	match style:
		"hat", "cap", "helmet":
			disc(image, Vector2i(16, 15), 10, c.darkened(.2))
			fill(image, Rect2i(7, 10, 18, 12), c)
			fill(image, Rect2i(4, 21, 25, 3), c.lightened(.15))
			fill(image, Rect2i(8, 18, 17, 2), Color("8c785e"))
			if style == "helmet":
				disc(image, Vector2i(16, 16), 4, Color("fff2b8"))
			elif style == "cap":
				fill(image, Rect2i(21, 20, 10, 3), c.darkened(.1))
		"backpack":
			fill(image, Rect2i(9, 3, 15, 3), c.darkened(.3))
			fill(image, Rect2i(6, 6, 21, 24), c.darkened(.22))
			fill(image, Rect2i(8, 7, 17, 21), c)
			fill(image, Rect2i(9, 17, 15, 10), c.lightened(.12))
			fill(image, Rect2i(15, 12, 4, 7), Color("e9d095"))
		"cape":
			for y in range(4, 30):
				var half := 3 + int(y * .3)
				fill(image, Rect2i(16 - half, y, half * 2, 1), c)
			stroke(image, Vector2i(14, 7), Vector2i(10, 29), c.lightened(.2), 2)
			stroke(image, Vector2i(19, 7), Vector2i(23, 29), c.darkened(.2), 2)
		"wings":
			for side in [-1, 1]:
				for i in range(5):
					stroke(image, Vector2i(16, 19), Vector2i(16 + side * (4 + i * 2), 2 + i * 5), c.lightened(i * .03), 3)
		_:
			fill(image, Rect2i(8, 4, 17, 24), c.darkened(.15))
			fill(image, Rect2i(4, 6, 6, 13), c)
			fill(image, Rect2i(24, 6, 5, 13), c)
			fill(image, Rect2i(10, 5, 13, 22), c)
			fill(image, Rect2i(15, 8, 2, 17), c.lightened(.28))
			fill(image, Rect2i(8, 24, 17, 3), Color("b59670"))

func decor_sprite(image: Image, c: Color, style: String) -> void:
	var wood := Color("bb9169")
	var trim := c.darkened(.28)
	match style:
		"fence", "railing", "ladder":
			for x in [5, 24]:
				fill(image, Rect2i(x, 3, 3, 29), trim)
				fill(image, Rect2i(x, 4, 2, 27), c)
			for y in ([9, 21] if style == "fence" else ([5, 13, 21, 29] if style == "ladder" else [7])):
				fill(image, Rect2i(2, y, 29, 3), c)
				fill(image, Rect2i(3, y, 27, 1), c.lightened(.24))
			if style == "railing":
				for x in range(7, 25):
					pixel(image, x, 14 + int(sin((x - 7) * .19) * 3), c.lightened(.14))
		"door", "window":
			fill(image, Rect2i(4, 4, 24, 28), wood.darkened(.27))
			disc(image, Vector2i(16, 9), 11, wood.darkened(.27))
			fill(image, Rect2i(7, 7, 18, 25), Color("527373") if style == "window" else c.darkened(.13))
			if style == "window":
				fill(image, Rect2i(8, 8, 16, 22), Color(c, .55))
				fill(image, Rect2i(15, 4, 2, 28), wood)
				fill(image, Rect2i(6, 19, 21, 2), wood)
				stroke(image, Vector2i(9, 17), Vector2i(15, 9), Color("f3fff3", .8))
			else:
				for x in range(8, 25, 4):
					fill(image, Rect2i(x, 7, 1, 25), c.darkened(.22))
				fill(image, Rect2i(22, 20, 2, 3), Color("f5d18d"))
		"column":
			fill(image, Rect2i(9, 2, 14, 28), c)
			fill(image, Rect2i(11, 4, 2, 24), c.lightened(.23))
			fill(image, Rect2i(20, 4, 2, 24), trim)
			for y in [0, 28]:
				fill(image, Rect2i(5, y, 22, 4), c)
				fill(image, Rect2i(6, y, 20, 1), c.lightened(.2))
		"arch":
			fill(image, Rect2i(3, 10, 3, 22), wood)
			fill(image, Rect2i(26, 10, 3, 22), wood)
			for x in range(3, 29):
				var y := 4 + int(pow(float(x - 16) / 12, 2) * 9)
				fill(image, Rect2i(x, y, 2, 3), wood)
				if x % 3 == 0:
					disc(image, Vector2i(x, y + 1), 3, c)
		"flower", "fern", "cactus":
			fill(image, Rect2i(9, 25, 14, 3), Color("deac88"))
			fill(image, Rect2i(11, 28, 10, 4), Color("bb8764"))
			if style == "cactus":
				fill(image, Rect2i(13, 7, 7, 19), c)
				fill(image, Rect2i(7, 15, 10, 4), c)
				fill(image, Rect2i(7, 9, 3, 8), c)
				fill(image, Rect2i(17, 18, 9, 3), c)
				fill(image, Rect2i(23, 12, 3, 9), c)
				fill(image, Rect2i(14, 9, 1, 14), c.lightened(.23))
			else:
				for p in [Vector2i(9, 16), Vector2i(16, 8), Vector2i(24, 14)]:
					stroke(image, Vector2i(16, 27), p, Color("73a574"), 2)
					if style == "flower":
						for v in [Vector2i(-3, 0), Vector2i(3, 0), Vector2i(0, 3), Vector2i(0, -3)]:
							disc(image, p + v, 2, c)
						disc(image, p, 1, Color("ffdf9a"))
					else:
						for y in range(p.y, 24, 4):
							stroke(image, Vector2i(16, y + 2), Vector2i(9, y - 2), c, 2)
							stroke(image, Vector2i(16, y + 3), Vector2i(23, y - 1), c.lightened(.12), 2)
		"stool", "sofa", "bed":
			if style == "stool":
				fill(image, Rect2i(5, 14, 23, 5), c)
				fill(image, Rect2i(7, 19, 3, 13), trim)
				fill(image, Rect2i(23, 19, 3, 13), trim)
				fill(image, Rect2i(6, 14, 21, 1), c.lightened(.25))
			else:
				fill(image, Rect2i(2, 11, 29, 16), trim)
				fill(image, Rect2i(4, 12, 25, 13), c)
				fill(image, Rect2i(2, 25, 29, 3), wood)
				fill(image, Rect2i(4, 28, 3, 4), wood.darkened(.2))
				fill(image, Rect2i(26, 28, 3, 4), wood.darkened(.2))
				if style == "sofa":
					fill(image, Rect2i(2, 19, 5, 9), c.lightened(.18))
					fill(image, Rect2i(26, 19, 5, 9), c.lightened(.18))
					fill(image, Rect2i(16, 13, 1, 12), trim)
				else:
					fill(image, Rect2i(3, 5, 3, 24), wood)
					fill(image, Rect2i(7, 12, 7, 8), Color("f3e6c9"))
					fill(image, Rect2i(16, 13, 13, 11), c.lightened(.14))
		"cabinet", "barrel":
			fill(image, Rect2i(5, 4, 23, 27), trim)
			fill(image, Rect2i(7, 5, 19, 25), c)
			for x in range(10, 26, 5):
				fill(image, Rect2i(x, 6, 1, 23), c.darkened(.18))
			if style == "barrel":
				for y in [8, 23]:
					fill(image, Rect2i(4, y, 25, 3), Color("8897a0"))
				fill(image, Rect2i(8, 2, 17, 3), c.lightened(.15))
			else:
				fill(image, Rect2i(16, 5, 1, 25), trim)
				for x in [13, 19]:
					fill(image, Rect2i(x, 15, 2, 4), Color("efd096"))
		"clock":
			disc(image, Vector2i(16, 15), 13, trim)
			disc(image, Vector2i(16, 14), 11, c)
			disc(image, Vector2i(16, 14), 8, Color("fff1cd"))
			stroke(image, Vector2i(16, 14), Vector2i(16, 8), Color("655f52"), 2)
			stroke(image, Vector2i(16, 14), Vector2i(21, 17), Color("655f52"), 2)
		"painting", "notice":
			fill(image, Rect2i(2, 3, 29, 24), wood.darkened(.2))
			fill(image, Rect2i(4, 5, 25, 20), Color("9fc4d1") if style == "painting" else Color("9d7a55"))
			if style == "painting":
				disc(image, Vector2i(23, 9), 3, Color("ffe5ac"))
				for x in range(5, 29):
					var y := 13 + int(absf(float(x - 14)) * .6)
					fill(image, Rect2i(x, y, 1, 25 - y), Color("7b9e8c"))
				fill(image, Rect2i(4, 22, 25, 3), Color("548473"))
			else:
				for p in [Vector2i(6, 8), Vector2i(17, 7), Vector2i(13, 17)]:
					fill(image, Rect2i(p, Vector2i(9, 7)), Color("fff0c6"))
					pixel(image, p.x + 4, p.y, Color("ce906b"))
		"sign", "mailbox", "birdhouse":
			fill(image, Rect2i(14, 10, 4, 22), wood.darkened(.17))
			fill(image, Rect2i(5, 7, 24, 13), c)
			fill(image, Rect2i(6, 8, 22, 1), c.lightened(.22))
			if style == "sign":
				fill(image, Rect2i(8, 12, 13, 1), trim)
				fill(image, Rect2i(8, 16, 9, 1), trim)
			elif style == "mailbox":
				fill(image, Rect2i(5, 16, 24, 3), trim)
				fill(image, Rect2i(25, 3, 2, 11), Color("a37966"))
				fill(image, Rect2i(26, 3, 6, 4), Color("ee927c"))
			else:
				for x in range(3, 30):
					var y := int(absi(x - 16) * .5)
					fill(image, Rect2i(x, y, 1, 2), Color("779681"))
				disc(image, Vector2i(17, 13), 3, Color("5a5245"))
		"banner", "rug":
			var top := 3 if style == "banner" else 26
			var h := 23 if style == "banner" else 5
			fill(image, Rect2i(5, top, 23, h), trim)
			fill(image, Rect2i(7, top + 1, 19, h - 2), c)
			if style == "banner":
				fill(image, Rect2i(3, 1, 27, 2), wood)
				diamond(image, Vector2i(16, 14), 5, Color("fff0b1"))
			for x in range(7, 27, 3):
				fill(image, Rect2i(x, top + h, 1, 2), c.lightened(.24))
		"candle", "street_lamp", "lantern", "mushroom", "pearl_lamp":
			if style == "candle":
				fill(image, Rect2i(8, 29, 17, 3), Color("a99a82"))
				fill(image, Rect2i(12, 13, 9, 17), Color("efe3ad"))
				fill(image, Rect2i(13, 14, 2, 14), Color("ffefcd"))
				diamond(image, Vector2i(16, 8), 4, c)
				diamond(image, Vector2i(16, 9), 2, Color("fff6cf"))
			elif style == "mushroom":
				fill(image, Rect2i(13, 16, 8, 16), Color("e3d8b6"))
				disc(image, Vector2i(16, 13), 12, c)
				fill(image, Rect2i(3, 14, 27, 4), c.darkened(.12))
				for p in [Vector2i(8, 10), Vector2i(17, 6), Vector2i(25, 11)]:
					disc(image, p, 2, Color("fff3c6"))
			elif style == "pearl_lamp":
				disc(image, Vector2i(16, 14), 9, c.darkened(.12))
				disc(image, Vector2i(14, 12), 7, c)
				disc(image, Vector2i(11, 9), 2, Color("fafff3"))
				fill(image, Rect2i(11, 23, 11, 4), Color("d2a87a"))
				fill(image, Rect2i(7, 27, 19, 4), Color("a88263"))
			else:
				fill(image, Rect2i(14, 3, 4, 29), Color("7d8991"))
				fill(image, Rect2i(7, 3, 19, 18), Color("667b88"))
				fill(image, Rect2i(10, 6, 13, 12), c)
				fill(image, Rect2i(12, 8, 9, 8), c.lightened(.28))
				fill(image, Rect2i(8, 2, 17, 3), Color("a5b4b8"))
				if style == "street_lamp":
					fill(image, Rect2i(10, 29, 13, 3), Color("9b9c97"))
		"campfire":
			stroke(image, Vector2i(5, 28), Vector2i(27, 24), wood.darkened(.25), 3)
			stroke(image, Vector2i(6, 24), Vector2i(26, 28), wood, 3)
			for p in [Vector2i(10, 20), Vector2i(18, 14), Vector2i(23, 21)]:
				diamond(image, p, 6, c)
				diamond(image, p + Vector2i(0, 2), 3, Color("ffe9a9"))
		"fountain":
			fill(image, Rect2i(3, 26, 27, 6), c.darkened(.2))
			fill(image, Rect2i(5, 25, 23, 3), Color("80cfeb"))
			fill(image, Rect2i(13, 5, 7, 23), c)
			fill(image, Rect2i(7, 13, 19, 4), c.lightened(.14))
			for side in [-1, 1]:
				stroke(image, Vector2i(16, 7), Vector2i(16 + side * 9, 17), Color("caeff8"))
		"aquarium":
			fill(image, Rect2i(2, 4, 29, 27), Color(c, .5))
			frame(image, Rect2i(2, 4, 29, 27), Color("a8bcbd"))
			fill(image, Rect2i(3, 26, 27, 4), Color("d5bf94"))
			disc(image, Vector2i(15, 16), 4, Color("c8cbbd"))
			fill(image, Rect2i(18, 13, 3, 6), Color("c8cbbd"))
			pixel(image, 12, 15, Color("566e7a"))
			stroke(image, Vector2i(25, 27), Vector2i(25, 15), Color("83ac77"), 2)
			for y in [9, 14, 19]:
				pixel(image, 7, y, Color("e0f7f1"))
		"portal":
			ring(image, Vector2i(16, 15), 13, Color("8297a3"), 3)
			ring(image, Vector2i(16, 15), 10, c, 2)
			disc(image, Vector2i(16, 15), 8, Color(c, .3))
			fill(image, Rect2i(5, 28, 23, 4), Color("91a4ad"))
			for p in [Vector2i(16, 4), Vector2i(5, 15), Vector2i(27, 15)]:
				diamond(image, p, 2, Color("e4d9ff"))
		"spring":
			fill(image, Rect2i(3, 5, 27, 4), Color("b7c7c9"))
			fill(image, Rect2i(5, 28, 23, 4), Color("85999f"))
			for y in range(11, 28, 4):
				stroke(image, Vector2i(10, y), Vector2i(23, y + 2), c, 2)
				stroke(image, Vector2i(23, y + 2), Vector2i(10, y + 4), c.darkened(.2))
		_:
			diamond(image, Vector2i(16, 18), 11, c)
			diamond(image, Vector2i(14, 15), 7, c.lightened(.2))

func stroke(image: Image, start: Vector2i, end: Vector2i, c: Color, width: int = 1) -> void:
	var steps := maxi(absi(end.x - start.x), absi(end.y - start.y))
	for step in range(steps + 1):
		var point := Vector2i(Vector2(start).lerp(Vector2(end), float(step) / maxi(1, steps)).round())
		fill(image, Rect2i(point - Vector2i(width / 2, width / 2), Vector2i(width, width)), c)

func disc(image: Image, center: Vector2i, radius: int, c: Color) -> void:
	for y in range(center.y - radius, center.y + radius + 1):
		for x in range(center.x - radius, center.x + radius + 1):
			if Vector2(x - center.x, y - center.y).length_squared() <= radius * radius:
				pixel(image, x, y, c)

func ring(image: Image, center: Vector2i, radius: int, c: Color, width: int = 1) -> void:
	for y in range(center.y - radius, center.y + radius + 1):
		for x in range(center.x - radius, center.x + radius + 1):
			var distance := Vector2(x - center.x, y - center.y).length()
			if distance <= radius and distance > radius - width:
				pixel(image, x, y, c)
