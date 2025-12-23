# -*- coding: utf-8 -*-

import sys
import yaml

with open("Config.yaml", "r") as File:
	Config = yaml.safe_load(File)

if not Config.get("mysqlclient"):
	print("Error: The basic MariaDB/MySQL parameters aren’t defined in the configuration file.")
	sys.exit(1)
if not Config.get("db_additional"):
	print("Error: The additional DB parameters aren’t defined in the configuration file.")
	sys.exit(1)
if not Config["db_additional"].get("history_table"):
	print("Error: The table for the history isn’t defined in the configuration file.")
	sys.exit(1)
