# -*- coding: utf-8 -*-

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from Config_manager import Config
import DB_manager

Display_history = FastAPI()

def Get_history_tables(Server_ID):
	"""Return the history and channel tables for an enabled project."""
	# Duplication from the Gear module, to avoid a dependency on it
	Projects_by_server = {
			int(Project["Discord_server"]): Project
			for Project in Config["Projects"]
	}
	try:
		Project = Projects_by_server.get(int(Server_ID))
	except (TypeError, ValueError):
		raise HTTPException(
				status_code=404,
				detail="Invalide server ID."
		)
	if not Project or not Project["History"]["Enable"]:
		raise HTTPException(
				status_code=404,
				detail="The history isn’t activated for this project."
		)
	return (
			Project["History"]["Table"],
			Project["History"]["Chans_table"]
	)

@Display_history.get("/api/server/{Server_ID}/chans")
def API_chans(Server_ID: str):
	History_table, History_chans_table = Get_history_tables(Server_ID)
	Chans = DB_manager.Get_chans_for_server(History_table, History_chans_table)
	return {"Chans": Chans}

# Server_ID and Chan_ID are 19-digit Discord identifiers. Their size conflits with Pydantic (used by
# FastAPI), which enforces a 32-bit limit for integers by default. Since these are juste identifiers
# and not values used for arithmetic, we use strings.
@Display_history.get("/chan/{Server_ID}/{Chan_ID}")
def Chan_page(Server_ID: str, Chan_ID: str):
	try:
		Get_history_tables(Server_ID)
	except HTTPException:
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
	History_table, _ = Get_history_tables(Server_ID)
	Messages = DB_manager.History_messages_to_display(History_table, Chan_ID, Before)
	Next_cursor = Messages[-1]["creation_date"] if Messages else None
	Messages.reverse()
	return {
			"Messages": Messages,
			"Next_cursor": Next_cursor
	}
