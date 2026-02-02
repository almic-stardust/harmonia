# -*- coding: utf-8 -*-

import sys
import yaml

with open("Config.yaml", "r") as File:
	# Config is a variable, so this file is named Config_manager.py
	Config = yaml.safe_load(File)

if Config.get("irc_users"):
	Config["users"] = {}
	Config["users"]["irc_to_discord"] = Config["irc_users"]
	Config["users"]["discord_to_irc"] = {
		Data['discord_username']: Key
		for Key, Data in Config["irc_users"].items()
	}
	del Config["irc_users"]
else:
	Config["users"] = {}
	Config["users"]["irc_to_discord"] = {}
	Config["users"]["discord_to_irc"] = {}

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
