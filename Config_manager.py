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

# History is configured independently for each Discord project
Projects = Config.get("Projects", [])
if not isinstance(Projects, list) or not Projects:
    print('[Config] Error: You must define as least one project (as a YAML list)')
    sys.exit(1)

Project_names = set()
Project_servers = set()
for Index, Project in enumerate(Projects):
    Project_label = f"Projects[{Index}]"
    if not isinstance(Project, dict):
        print(f"[Config] Error: “{Project_label}” must be a mapping.")
        sys.exit(1)
    for Key in ("Name", "Discord_server", "History"):
        if Key not in Project or Project[Key] in (None, ""):
            print(f"[Config] Error: “{Project_label}” is missing required key “{Key}”.")
            sys.exit(1)
    Name = str(Project["Name"])
    if Name in Project_names:
        print(f"[Config] Error: Duplicate project name “{Name}”.")
        sys.exit(1)
    Project_names.add(Name)
    try:
        Server_ID = int(Project["Discord_server"])
    except (TypeError, ValueError):
        print(f"[Config] Error: “{Project_label}.Discord_server” must be a Discord server ID.")
        sys.exit(1)
    if Server_ID <= 0 or Server_ID in Project_servers:
        print(f"[Config] Error: Invalid or duplicate Discord server ID in “{Project_label}”.")
        sys.exit(1)
    Project["Discord_server"] = Server_ID
    Project_servers.add(Server_ID)
    if not isinstance(Project["History"], dict):
        print(f"[Config] Error: “{Project_label}.History” must be a mapping.")
        sys.exit(1)
    History = Project["History"]
    History.setdefault("Enable", False)
    if History["Enable"]:
        for Key in ("Sync_old", "Table", "Chans_table", "Storage_folder", "Storage_url"):
            if Key not in History or History[Key] in (None, ""):
                print(f"[Config] Error: History is enabled for project “{Name}”, but key “{Key}” is missing or empty.")
                sys.exit(1)
        for Key in ("Table", "Chans_table"):
            if not str(History[Key]).isidentifier():
                print(f"[Config] Error: “{Project_label}.History.{Key}” must be a valid SQL table identifier.")
                sys.exit(1)
        Config["Enabled_sections"]["History"] = True

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
