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
	for IRC_chan in Config["irc_bridges"]:
		Config["irc_bridges"][IRC_chan]["irc_chan"] = f"#{IRC_chan}"
else:
	Config["irc_bridges"] = {}
