# -*- coding: utf-8 -*-

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from Config_manager import Config
import DB_manager

Display_history = FastAPI()
# Duplication from the Gear module, to avoid a dependency on it
List_of_servers = {}
for Server in Config["Discord_servers"]:
	ID = int(Server["Discord_ID"])
	List_of_servers[ID] = Server

def Get_history_tables(Server_ID):
	try:
		Server = List_of_servers.get(int(Server_ID))
	except (TypeError, ValueError):
		raise HTTPException(
				status_code=404,
				detail="Invalid server ID."
		)
	if not Server or not Server["History"]["Enable"]:
		raise HTTPException(
				status_code=404,
				detail="The history isn’t activated for this server."
		)
	return (
			Server["History"]["Table"],
			Server["History"]["Chans_table"]
	)

@Display_history.get("/api/server/{Server_ID}/chans")
def API_chans(Server_ID: str):
	_, History_chans_table = Get_history_tables(Server_ID)
	Registered_chans = DB_manager.Get_registered_Discord_chans(History_chans_table)
	Chans = []
	for Chan_ID, Infos_chan in Registered_chans.items():
		# Infos_chan[0] = position | Infos_chan[1] = name
		Chan_name = Infos_chan[1]
		Chan_ID = str(Chan_ID)
		if Chan_name:
			Chan_name = f"#{Chan_name}"
		else:
			# If a chan isn’t registered in the DB, use its ID as the fallback name
			Chan_name = Chan_ID
		Chans.append({
				"id": Chan_ID,
				"name": Chan_name,
		})
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
				"<body><h1>The history isn’t activated for this server.</h1></body>"
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
