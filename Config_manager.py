# -*- coding: utf-8 -*-

import sys
import yaml

with open("Config.yaml", "r") as File:
	# Config is a variable, so this file is named Config_manager.py
	Config = yaml.safe_load(File) or {}
Config["Enabled_sections"] = {}

###############################################################################
# Required sections
###############################################################################

Required = {
	"mysqlclient": (
		"host",
		"user",
		"password",
		"database",
	),
	"Discord": (
		"Bot_owner",
		"Token",
		"Bot_name",
	),
}

for Section, Keys in Required.items():
	if Section not in Config:
		print(f"[Config] Error: Section “{Section}” is missing.")
		sys.exit(1)
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: The section “{Section}” is present, but its key “{Key}” is missing or empty.")
			if Section == "Discord" and Key == "Token":
				print("See https://discordpy.readthedocs.io/en/stable/discord.html")
			sys.exit(1)

###############################################################################
# Optional sections
###############################################################################

if "Server_timezone" not in Config:
	Config["Server_timezone"] = "UTC"

Optional = {
	"Mail": (
		"Server",
		"Bot_address",
	),
	"Users": (
		"Table",
	),
	"Localization": (
		"Default_language",
		"Available_languages",
	),
	"Polls": (
		"Table",
	),
}

for Section, Keys in Optional.items():
	Config["Enabled_sections"][Section] = False
	if Section not in Config:
		continue
	if Config[Section] is None:
		print(f"[Config] Error: Section “{Section}” is present but empty.")
		sys.exit(1)
	Config["Enabled_sections"][Section] = True
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: The section “{Section}” is present, but its key “{Key}” is missing or empty.")
			sys.exit(1)

###############################################################################
# Special cases
###############################################################################

# History is configured independently for each Discord server
Servers = Config.get("Discord_servers", [])
if not isinstance(Servers, list) or not Servers:
    print('[Config] Error: You must define as least one Discord server (as a YAML list)')
    sys.exit(1)
Server_names = set()
Server_servers = set()
for Index, Server in enumerate(Servers):
    Server_label = f"Servers[{Index}]"
    if not isinstance(Server, dict):
        print(f"[Config] Error: “{Server_label}” must be a mapping.")
        sys.exit(1)
    for Key in ("Name", "Discord_ID", "History"):
        if Key not in Server or Server[Key] in (None, ""):
            print(f"[Config] Error: “{Server_label}” is missing required key “{Key}”.")
            sys.exit(1)
    Name = str(Server["Name"])
    if Name in Server_names:
        print(f"[Config] Error: Duplicate server name “{Name}”.")
        sys.exit(1)
    Server_names.add(Name)
    try:
        Server_ID = int(Server["Discord_ID"])
    except (TypeError, ValueError):
        print(f"[Config] Error: “{Server_label}.Discord_ID” must be a Discord server ID.")
        sys.exit(1)
    if Server_ID <= 0 or Server_ID in Server_servers:
        print(f"[Config] Error: Invalid or duplicate Discord server ID in “{Server_label}”.")
        sys.exit(1)
    Server["Discord_ID"] = Server_ID
    Server_servers.add(Server_ID)
    if not isinstance(Server["History"], dict):
        print(f"[Config] Error: “{Server_label}.History” must be a mapping.")
        sys.exit(1)
    History = Server["History"]
    History.setdefault("Enable", False)
    if History["Enable"]:
        for Key in ("Sync_old", "Table", "Chans_table", "Storage_folder", "Storage_url"):
            if Key not in History or History[Key] in (None, ""):
                print(f"[Config] Error: History is enabled for server “{Name}”, but key “{Key}” is missing or empty.")
                sys.exit(1)
        for Key in ("Table", "Chans_table"):
            if not str(History[Key]).isidentifier():
                print(f"[Config] Error: “{Server_label}.History.{Key}” must be a valid SQL table identifier.")
                sys.exit(1)

Config["Enabled_sections"]["IRC"] = False
if "IRC" in Config:
	Config["Enabled_sections"]["IRC"] = True
	# The keys "password" and "quit_message" are optional
	for Key in ("Bot_owner", "Server", "Nick", "Username", "Real_name"):
		if Key not in Config["IRC"] or Config["IRC"][Key] in (None, ""):
			print(f"[Config] Error: The section “IRC” is present, but its key “{Key}” is missing or empty.")
			sys.exit(1)

Config["Enabled_sections"]["IRC_bridges"] = False
if Config["Enabled_sections"]["IRC"]:
	if "IRC_bridges" in Config:
		Config["Enabled_sections"]["IRC_bridges"] = True
		for IRC_chan, Infos_chan in Config["IRC_bridges"].items():
			if "Discord_chan" not in Infos_chan or Infos_chan["Discord_chan"] in (None, ""):
				print(f"[Config] Error: Key “Discord_chan” is missing or empty for “{IRC_chan}”.")
				sys.exit(1)
			# Modify from: IRC_chan = {Discord_chan: X, Webhook: Y}
			# 		   to: IRC_chan = {Discord_chan: X, Webhook: Y, IRC_chan: "IRC_chan"}
			Config["IRC_bridges"][IRC_chan]["IRC_chan"] = f"#{IRC_chan}"
	else:
		Config["IRC_bridges"] = {}

###############################################################################
# Localization
###############################################################################

with open("Localization.yaml", "r") as File:
    L10n = yaml.safe_load(File)
