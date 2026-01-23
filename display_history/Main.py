# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from Config_manager import Config
import DB_manager

Display_history = FastAPI()
Display_history.mount("/static", StaticFiles(directory="static"), name="static")
Templates = Jinja2Templates(directory="templates")

History_table = Config["history"]["db_table"]

# Server_id and Chan_id are 19-digit Discord identifiers. Their size conflits with Pydantic (used by
# FastAPI), which enforces a 32-bit limit for integers by default. Since these are juste identifiers
# and not numbers to be computed, we use strings.
@Display_history.get("/chan/{Server_id}/{Chan_id}", response_class=HTMLResponse)
def Chan_page(Request_object: Request, Server_id: str, Chan_id: str):
	Messages = DB_manager.History_messages_to_display(History_table, Server_id, Chan_id)
	Next_cursor = (Messages[-1]["date_creation"] if Messages else None)
	# Reverse for chronological display
	Messages.reverse()
	return Templates.TemplateResponse(
		"Chan.html", {
			"request": Request_object,
			"Server_id": Server_id,
			"Chan_id": Chan_id,
			"Messages": Messages,
			"Next_cursor": Next_cursor,
		},
	)

@Display_history.get("/api/messages")
def API_messages(Server_id: str, Chan_id: str, Before: str|None = None):
	Messages = DB_manager.History_messages_to_display(History_table, Server_id, Chan_id, Before)
	Next_cursor = (Messages[-1]["date_creation"] if Messages else None)
	Messages.reverse()
	return {
		"Messages": Messages,
		"Next_cursor": Next_cursor,
	}
