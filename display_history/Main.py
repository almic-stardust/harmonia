# -*- coding: utf-8 -*-

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from Config_manager import Config
import DB_manager

Display_history = FastAPI()
History_enabled = Config["Enabled_sections"]["History"]
if History_enabled:
	History_table = Config["History"]["Table"]

@Display_history.get("/api/server/{Server_ID}/chans")
def API_chans(Server_ID: str):
	if not History_enabled:
		raise HTTPException(
				status_code=404,
				detail="The history isn’t activated for this project."
		)
	Chans = DB_manager.Get_chans_for_server(History_table, Server_ID)
	return {"Chans": Chans}

# Server_ID and Chan_ID are 19-digit Discord identifiers. Their size conflits with Pydantic (used by
# FastAPI), which enforces a 32-bit limit for integers by default. Since these are juste identifiers
# and not numbers to be computed, we use strings.
@Display_history.get("/chan/{Server_ID}/{Chan_ID}")
def Chan_page(Server_ID: str, Chan_ID: str):
	if not History_enabled:
		return HTMLResponse(
				"<!DOCTYPE html><html lang='en'>"
				"<head><meta charset='UTF-8'><title>History unavailable</title></head>"
				"<body><h1>The history isn’t activated for this project.</h1></body>"
				"</html>",
				status_code=200
		)
	return FileResponse("static/Chan.html")

@Display_history.get("/api/messages")
def API_messages(Server_ID: str, Chan_ID: str, Before: str|None = None):
	if not History_enabled:
		raise HTTPException(
				status_code=404,
				detail="The history isn’t activated for this project."
		)
	Messages = DB_manager.History_messages_to_display(History_table, Server_ID, Chan_ID, Before)
	Next_cursor = Messages[-1]["creation_date"] if Messages else None
	Messages.reverse()
	return {
		"Messages": Messages,
		"Next_cursor": Next_cursor
	}
