# -*- coding: utf-8 -*-

import sys
import yaml

with open("Config.yaml", "r") as File:
	# Config is a variable, so this file is named Config_manager.py
	Config = yaml.safe_load(File) or {}
Config["enabled_sections"] = {}

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
	"discord": (
		"bot_owner",
		"token",
		"bot_name",
		"server",
	),
}

for Section, Keys in Required.items():
	if Section not in Config:
		print(f"[Config] Error: section {Section} is missing.")
		sys.exit(1)
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: the section \"{Section}\" is present, but its key \"{Key}\" is missing or empty.")
			if Section == "discord" and Key == "token":
				print("See https://discordpy.readthedocs.io/en/stable/discord.html")
			sys.exit(1)

###############################################################################
# Optional sections
###############################################################################

Optional = {
	"mail": (
		"server",
		"bot_address",
	),
	"users": (
		"db_table",
	),
	"polls": (
		"db_table",
	),
}

for Section, Keys in Optional.items():
	Config["enabled_sections"][Section] = False
	if Section not in Config:
		continue
	if Config[Section] is None:
		print(f"[Config] Error: section \"{Section}\" is present but empty.")
		sys.exit(1)
	Config["enabled_sections"][Section] = True
	for Key in Keys:
		if Key not in Config[Section] or Config[Section][Key] in (None, ""):
			print(f"[Config] Error: the section \"{Section}\" is present, but its key \"{Key}\" is missing or empty.")
			sys.exit(1)

###############################################################################
# Special cases
###############################################################################

Config["enabled_sections"]["history"] = False
if "history" in Config and Config["history"].get("enable"):
	Config["enabled_sections"]["history"] = True
	for Key in ("db_table", "storage_folder", "storage_url"):
		if Key not in Config["history"] or Config["history"][Key] in (None, ""):
			print(f"[Config] Error: the history is enabled, but key \"{Key}\" is missing or empty.")
			sys.exit(1)

Config["enabled_sections"]["irc"] = False
if "irc" in Config:
	Config["enabled_sections"]["irc"] = True
	# The keys "password" and "quit_message" are optional
	for Key in ("bot_owner", "server", "nick", "username", "real_name"):
		if Key not in Config["irc"] or Config["irc"][Key] in (None, ""):
			print(f"[Config] Error: the section \"irc\" is present, but its key \"{Key}\" is missing or empty.")
			sys.exit(1)

Config["enabled_sections"]["irc_bridges"] = False
if Config["enabled_sections"]["irc"]:
	if "irc_bridges" in Config:
		Config["enabled_sections"]["irc_bridges"] = True
		for IRC_chan, Infos_chan in Config["irc_bridges"].items():
			if "discord_chan" not in Infos_chan or Infos_chan["discord_chan"] in (None, ""):
				print(f"[Config] Error: key \"discord_chan\" is missing or empty for \"{IRC_chan}\".")
				sys.exit(1)
			# Modify from: irc_chan = {discord_chan: X, webhook: Y}
			# 		   to: irc_chan = {discord_chan: X, webhook: Y, irc_chan: "irc_chan"}
			Config["irc_bridges"][IRC_chan]["irc_chan"] = f"#{IRC_chan}"
	else:
		Config["irc_bridges"] = {}
