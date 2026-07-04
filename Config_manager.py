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
		"Server",
	),
}

for Section, Keys in Required.items():
	if Section not in Config:
		print(f"[Config] Error: section {Section} is missing.")
		sys.exit(1)
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: the section \"{Section}\" is present, but its key \"{Key}\" is missing or empty.")
			if Section == "Discord" and Key == "Token":
				print("See https://discordpy.readthedocs.io/en/stable/discord.html")
			sys.exit(1)

###############################################################################
# Optional sections
###############################################################################

Optional = {
	"Mail": (
		"Server",
		"Bot_address",
	),
	"Users": (
		"DB_table",
	),
	"Polls": (
		"DB_table",
	),
}

for Section, Keys in Optional.items():
	Config["Enabled_sections"][Section] = False
	if Section not in Config:
		continue
	if Config[Section] is None:
		print(f"[Config] Error: section \"{Section}\" is present but empty.")
		sys.exit(1)
	Config["Enabled_sections"][Section] = True
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: the section \"{Section}\" is present, but its key \"{Key}\" is missing or empty.")
			sys.exit(1)

###############################################################################
# Special cases
###############################################################################

Config["Enabled_sections"]["History"] = False
if "History" in Config and Config["History"].get("Enable"):
	Config["Enabled_sections"]["History"] = True
	for Key in ("DB_table", "Storage_folder", "Storage_url"):
		if Key not in Config["History"] or Config["History"][Key] in (None, ""):
			print(f"[Config] Error: the history is enabled, but key \"{Key}\" is missing or empty.")
			sys.exit(1)

Config["Enabled_sections"]["IRC"] = False
if "IRC" in Config:
	Config["Enabled_sections"]["IRC"] = True
	# The keys "password" and "quit_message" are optional
	for Key in ("Bot_owner", "Server", "Nick", "Username", "Real_name"):
		if Key not in Config["IRC"] or Config["IRC"][Key] in (None, ""):
			print(f"[Config] Error: the section \"IRC\" is present, but its key \"{Key}\" is missing or empty.")
			sys.exit(1)

Config["Enabled_sections"]["IRC_bridges"] = False
if Config["Enabled_sections"]["IRC"]:
	if "IRC_bridges" in Config:
		Config["Enabled_sections"]["IRC_bridges"] = True
		for IRC_chan, Infos_chan in Config["IRC_bridges"].items():
			if "Discord_chan" not in Infos_chan or Infos_chan["Discord_chan"] in (None, ""):
				print(f"[Config] Error: key \"Discord_chan\" is missing or empty for \"{IRC_chan}\".")
				sys.exit(1)
			# Modify from: IRC_chan = {Discord_chan: X, Webhook: Y}
			# 		   to: IRC_chan = {Discord_chan: X, Webhook: Y, IRC_chan: "IRC_chan"}
			Config["IRC_bridges"][IRC_chan]["IRC_chan"] = f"#{IRC_chan}"
	else:
		Config["IRC_bridges"] = {}
