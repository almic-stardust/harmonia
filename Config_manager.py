# -*- coding: utf-8 -*-

import sys
import yaml

with open("Config.yaml", "r") as File:
	# Config is a variable, so this file is named Config_manager.py
	Config = yaml.safe_load(File)

if not Config.get("mysqlclient"):
	print("[Config file] Error: the MariaDB/MySQL parameters aren’t specified.")
	sys.exit(1)

if Config.get("history") and Config["history"].get("active"):
	if Config["history"].get("active") == True:
		if not Config["history"].get("db_table"):
			print("[Config file] Error: the history is actived, but the DB table isn’t specified.")
			sys.exit(1)
		if not Config["history"].get("storage_folder"):
			print("[Config file] Error: the history is actived, but the storage folder isn’t specified.")
			sys.exit(1)

if Config.get("irc_bridges"):
	# Modify from: irc_chan = {discord_chan: X, webhook: Y}
	# 		   to: irc_chan = {discord_chan: X, webhook: Y, irc_chan: "irc_chan"}
	for IRC_chan in Config["irc_bridges"].keys():
		Config["irc_bridges"][IRC_chan]["irc_chan"] = f"#{IRC_chan}"
else:
	Config["irc_bridges"] = {}

if Config.get("users"):
	Config["users"]["irc_to_discord"] = {}
	Config["users"]["discord_to_irc"] = {}
else:
	Config["users"] = {
		"irc_to_discord": {},
		"discord_to_irc": {}
	}
if Config.get("irc_users"):
	for IRC_user, User_infos in Config["irc_users"].items():
		# Ensure User_infos is a dict
		if not isinstance(User_infos, dict):
			User_infos = {}
		# Fetch optional Discord username and avatar
		Config["users"]["irc_to_discord"][IRC_user] = User_infos
		# Use IRC nick for users who have not requested a different display name on Discord
		Discord_display_name = User_infos.get("discord_display_name") or IRC_user
		Config["users"]["irc_to_discord"][IRC_user]["discord_display_name"] = Discord_display_name
		# Reverse map Discord to IRC
		Config["users"]["discord_to_irc"][Discord_display_name] = IRC_user
	del Config["irc_users"]
