extends Node
## Original gentle, synthesized effects. Four voices preserve short overlaps.
const SAMPLE_RATE := 22050
const MAX_VOICES := 4
var voices: Array[AudioStreamPlayer] = []
var tones := {}
var enabled := true:
	set(value):
		enabled = value
		if not enabled:
			for voice in voices:
				voice.stop()

func _ready() -> void:
	for i in range(MAX_VOICES):
		var voice := AudioStreamPlayer.new()
		voice.volume_db = -22
		add_child(voice)
		voices.append(voice)
	# Major intervals, soft attacks and brief tails keep repeated actions pleasant.
	var specifications := {
		"mine": {"notes": [175.0], "duration": .085},
		"place": {"notes": [260.0, 195.0], "duration": .11},
		"collect": {"notes": [659.25, 987.77], "duration": .18},
		"craft": {"notes": [440.0, 554.37, 659.25], "duration": .32},
		"eat": {"notes": [523.25, 659.25, 783.99], "duration": .21},
		"fish": {"notes": [440.0, 739.99, 987.77], "duration": .29},
		"portal": {"notes": [329.63, 440.0, 659.25], "duration": .48},
		"emote": {"notes": [523.25, 659.25, 783.99], "duration": .26},
		"jump": {"notes": [260.0], "duration": .13},
		"footstep": {"notes": [95.0], "duration": .048}
	}
	for kind in specifications:
		var spec: Dictionary = specifications[kind]
		tones[kind] = synthesize(kind, spec.notes, spec.duration)

func synthesize(kind: String, notes: Array, duration: float) -> AudioStreamWAV:
	var samples := PackedByteArray()
	var count := int(SAMPLE_RATE * duration)
	samples.resize(count * 2)
	for i in range(count):
		var t := float(i) / SAMPLE_RATE
		var progress := t / duration
		var wave := 0.0
		if kind in ["craft", "portal"]:
			for note in notes:
				var frequency: float = note
				var phase := t * TAU * frequency
				wave += sin(phase + sin(t * 15.0) * .12) / notes.size()
			if kind == "portal":
				wave = wave * .7 + sin(TAU * (190.0 * t + 420.0 * t * t)) * .15
		else:
			var index := mini(notes.size() - 1, int(progress * notes.size()))
			var frequency: float = notes[index]
			var local_progress := fmod(progress * notes.size(), 1.0)
			var phase := t * TAU * frequency
			if kind == "jump":
				phase = TAU * (260.0 * t + 750.0 * t * t)
			elif kind in ["mine", "place", "footstep"]:
				phase = TAU * frequency * (t - .6 * t * t)
			elif kind in ["eat", "fish"]:
				phase += sin(t * 80.0) * .18
			wave = sin(phase) * .7 + sin(phase * 2.0) * .09
			if notes.size() > 1:
				# Silence both ends of each note to avoid clicks at interval changes.
				wave *= minf(1.0, local_progress * 18.0) * minf(1.0, (1.0 - local_progress) * 12.0)
		var envelope := minf(1.0, t * 450.0) * pow(1.0 - progress, 1.8)
		var sample := int(clampf(wave * envelope, -1, 1) * 18000)
		samples[i * 2] = sample & 255
		samples[i * 2 + 1] = (sample >> 8) & 255
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = SAMPLE_RATE
	stream.data = samples
	return stream

func play(kind: String) -> void:
	if not enabled or not tones.has(kind):
		return
	for voice in voices:
		if not voice.playing:
			voice.volume_db = -31 if kind == "footstep" else (-25 if kind == "mine" else -22)
			voice.stream = tones[kind]
			voice.play()
			return
	# A burst beyond four simultaneous effects is ignored, preserving active tails.
