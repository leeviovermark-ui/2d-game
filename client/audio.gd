extends Node
## Short original synthesized effects. No asset downloads or autoplay music.
var enabled := true
var player: AudioStreamPlayer
var tones := {}

func _ready() -> void:
	player = AudioStreamPlayer.new()
	player.volume_db = -19
	add_child(player)
	for pair in [["mine",175.0],["place",260.0],["collect",630.0],["craft",420.0]]:
		var stream := AudioStreamWAV.new()
		stream.format = AudioStreamWAV.FORMAT_16_BITS
		stream.mix_rate = 22050
		var samples := PackedByteArray()
		var duration := .09 if pair[0] != "craft" else .18
		for i in range(int(22050*duration)):
			var t := i/22050.0
			var envelope := pow(1-t/duration,2)*minf(1,t*600)
			var wave := sin(t*TAU*pair[1]*(1-t*.6))*.65+sin(t*TAU*pair[1]*2)*.15
			var n := int(wave*envelope*20000)
			samples.append(n & 255)
			samples.append((n >> 8) & 255)
		stream.data = samples
		tones[pair[0]] = stream

func play(kind: String) -> void:
	if enabled and tones.has(kind):
		player.stream = tones[kind]
		player.play()
