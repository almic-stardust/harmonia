# -*- coding: utf-8 -*-

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from Config_manager import Config
import DB_manager

Display_history = FastAPI()
Display_history.mount("/static", StaticFiles(directory="static"), name="static")
History_table = Config["history"]["db_table"]

# Server_ID and Chan_ID are 19-digit Discord identifiers. Their size conflits with Pydantic (used by
# FastAPI), which enforces a 32-bit limit for integers by default. Since these are juste identifiers
# and not numbers to be computed, we use strings.
@Display_history.get("/chan/{Server_ID}/{Chan_ID}")
def Chan_page(Server_ID: str, Chan_ID: str):
	return FileResponse("static/Chan.html")

@Display_history.get("/api/messages")
def API_messages(Server_ID: str, Chan_ID: str, Before: str|None = None):
	Messages = DB_manager.History_messages_to_display(History_table, Server_ID, Chan_ID, Before)
	Next_cursor = Messages[-1]["date_creation"] if Messages else None
	Messages.reverse()
	return {
		"Messages": Messages,
		"Next_cursor": Next_cursor
	}
