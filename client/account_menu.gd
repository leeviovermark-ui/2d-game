extends RefCounted
## Account controls only send proof of ownership to the current server.
var ui
var fields := {}
var result: Label
var recovery_code := ""

func open() -> void:
	var body: VBoxContainer = ui.begin_modal("Your explorer account","account",610,670)
	body.add_child(ui.label(ui.state.player_name + "  /  PASSWORD & SAVED SESSIONS",11,ui.ACCENT))
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(scroll)
	var content: VBoxContainer = ui.column(scroll,12)
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	fields.clear()
	var summary: Label = ui.label("Checking account settings with the server…",12,ui.MUTED)
	summary.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(summary)
	fields.summary = summary
	content.add_child(ui.label("CURRENT PASSWORD",10,ui.MUTED))
	var current: LineEdit = ui.input("Required to change account security",true)
	current.max_length = 128
	content.add_child(current)
	fields.current = current
	content.add_child(ui.label("NEW PASSWORD",10,ui.MUTED))
	var next: LineEdit = ui.input("At least 8 characters",true)
	next.max_length = 128
	content.add_child(next)
	fields.next = next
	var confirm: LineEdit = ui.input("Confirm the new password",true)
	confirm.max_length = 128
	content.add_child(confirm)
	fields.confirm = confirm
	content.add_child(ui.button("Change password",func():
		if current.text.length() < 8:
			set_result("Enter your current password first.")
			return
		if next.text.length() < 8:
			set_result("Choose a new password with at least 8 characters.")
			return
		if next.text != confirm.text:
			set_result("The new passwords do not match.")
			return
		ui.intent.emit("account_password",{"current_password":current.text,"new_password":next.text})
		clear_passwords()
		set_result("Saving your new password…"),true))
	content.add_child(ui.label("Changing your password signs out other saved sessions.\nYour current session keeps working.",11,ui.MUTED))
	content.add_child(HSeparator.new())
	content.add_child(ui.label("RECOVERY & SESSION CONTROLS",10,ui.ACCENT))
	content.add_child(ui.button("Generate a new recovery code",func(): secure_action("account_recovery_rotate")))
	content.add_child(ui.button("Sign out all other saved sessions",func(): secure_action("account_sessions_clear")))
	content.add_child(ui.label("Both actions require your current password above. A new recovery\ncode replaces the previous code and is valid for one year.",11,ui.MUTED))
	content.add_child(ui.button("Sign out & forget this device",func():
		ui.intent.emit("account_logout",{})
		ui.clear_session()))
	result = ui.label("",12,ui.ACCENT)
	result.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	result.custom_minimum_size.y = 35
	content.add_child(result)
	ui.intent.emit("account_info",{})

func secure_action(kind: String) -> void:
	if str(fields.current.text).length() < 8:
		set_result("Enter your current password above before continuing.")
		fields.current.grab_focus()
		return
	ui.intent.emit(kind,{"password":fields.current.text})
	clear_passwords()
	set_result("Checking your password with the server…")

func clear_passwords() -> void:
	for key in ["current","next","confirm"]:
		if fields.has(key) and is_instance_valid(fields[key]): fields[key].clear()

func set_result(text: String) -> void:
	if is_instance_valid(result): result.text = text

func apply(data: Dictionary) -> void:
	if data.get("action") == "info" and fields.has("summary") and is_instance_valid(fields.summary):
		fields.summary.text = "Recovery code " + ("configured" if data.get("recovery_configured",false) else "not configured") + "  ·  " + str(data.get("saved_sessions",0)) + " saved session(s)"
	set_result(str(data.get("text","Account settings updated.")))
	if data.has("recovery_code"): show_code(str(data.recovery_code),float(data.get("recovery_expires",0)))

func show_code(code: String, expires := 0.0) -> void:
	if code.is_empty(): return
	recovery_code = code
	var body: VBoxContainer = ui.begin_modal("Keep your way back safe","recovery_code",630,490)
	body.add_child(ui.label("YOUR ONE-TIME ACCOUNT RECOVERY CODE",10,ui.ACCENT))
	var description: Label = ui.label("Save this code somewhere private. It lets you reset your password\non this server without an email address. Anyone with the code\ncan take over your account.",13,ui.INK)
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.add_child(description)
	var value: LineEdit = ui.input("")
	value.text = code
	value.editable = false
	value.select_all_on_focus = true
	body.add_child(value)
	body.add_child(ui.label("Valid for one year. Generating a new code replaces this one.",11,ui.MUTED))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation",10)
	body.add_child(row)
	row.add_child(ui.button("Copy recovery code",func():
		DisplayServer.clipboard_set(code)
		ui.notify("Recovery code copied. Store it somewhere private."),true))
	row.add_child(ui.button("Save recovery code",func(): save_code(code,expires)))
	body.add_child(ui.button("I have saved it — enter the world",func():
		recovery_code = ""
		ui.close_modal()))
	body.add_child(ui.label("The game does not save this code automatically. Your account\npassword and game progress are separate from this device.",11,ui.MUTED))

func save_code(code: String, expires: float) -> void:
	var explorer: String = ui.state.player_name if ui.game_enabled else ui.front_menu.name_hint
	var text: String = "WORLDFORGE account recovery\nExplorer: " + explorer + "\nServer: " + ui.front_menu.endpoint + "\nRecovery code: " + code + "\nKeep this file private. Anyone with this code can reset your password.\n"
	if expires > 0: text += "Expires: " + Time.get_datetime_string_from_unix_time(int(expires)) + " UTC\n"
	if OS.has_feature("web"):
		JavaScriptBridge.eval("(()=>{const b=new Blob(["+JSON.stringify(text)+"],{type:'text/plain'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download='WORLDFORGE-recovery.txt';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);})()")
		ui.notify("Recovery file downloaded. Keep it somewhere private.")
	else:
		var dialog := FileDialog.new()
		dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
		dialog.access = FileDialog.ACCESS_FILESYSTEM
		dialog.current_file = "WORLDFORGE-recovery.txt"
		ui.root.add_child(dialog)
		dialog.file_selected.connect(func(path):
			var file := FileAccess.open(path,FileAccess.WRITE)
			if file: file.store_string(text)
			dialog.queue_free())
		dialog.canceled.connect(func(): dialog.queue_free())
		dialog.popup_centered(Vector2i(700,450))
