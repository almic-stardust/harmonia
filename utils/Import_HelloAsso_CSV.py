#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import fnmatch
import csv
import datetime

from Config_manager import Config
import DB_manager

if len(sys.argv) == 1 or not fnmatch.fnmatch(sys.argv[1], "*csv"):
	print("Error: Missing CSV file.\nUsage: Import_HelloAsso_CSV.py File.csv")
	sys.exit(1)
Filename = sys.argv[1]
if not os.path.exists(Filename):
	print(f"Error: File {Filename} not found.")
	sys.exit(1)

def Parse_date(Date):
	Date = str(Date).strip()
	Formats = ["%d/%m/%Y",	"%d/%m/%Y %H:%M"]
	Error = ""
	for Format in Formats:
		try:
			return datetime.datetime.strptime(Date, Format)
		except Exception as e:
			Error = e
			continue
	print(f"Error while parsing date: {Error}")
	return None

def Parse_contribution(Value):
	if Value is None:
		return 0
	Value = str(Value).strip()
	if Value in ("", "Gratuit"):
		return 0
	try:
		# HelloAsso exports follow French numeric conventions
		Value = Value.replace(",", ".")
		# Handles thousands (one can dream)
		Value = Value.replace(" ", "")
		return int(float(Value))
	except (TypeError, ValueError) as Error:
		print(f"Error while parsing contribution: {Error}")
		return 0

with open(Filename, newline="", encoding="utf-8-sig") as CSV_file:

	Users_table = Config["users"]["db_table"]
	Output = ""
	CSV_content = csv.DictReader(CSV_file, delimiter=";")

	Normalized_lines = []
	for Line in CSV_content:
		Normalized_line = {}
		for Key, Value in Line.items():
			# Key.lower() to avoid Pseudo vs pseudo
			Normalized_line[Key.lower()] = Value
		Normalized_lines.append(Normalized_line)
	# The CSV of HelloAsso are sorted from newest to oldest date, but in the BD it’s preferable to
	# register users from oldest to newest
	Normalized_lines.reverse()

	for Line in Normalized_lines:
		Mail = Line.get("email", "").strip().lower()
		if not Mail:
			Mail = Line.get("email payeur", "").strip().lower()
		First_name = Line.get("prénom adhérent", "").strip().capitalize()
		Last_name = Line.get("nom adhérent", "").strip().capitalize()
		Pseudo = Line.get("pseudo", "").strip()
		Date = Parse_date(Line.get("date de la commande"))
		Contribution = Parse_contribution(Line.get("montant tarif"))
		User_infos = {
				"Pseudo": Pseudo,
				"Mail": Mail,
				"First_name": First_name,
				"Last_name": Last_name,
				"Last_renewal": Date,
				"Contribution": Contribution
		}

		User_ID = DB_manager.Users_check_presence(Users_table, User_infos)
		if User_ID:
			User_infos = DB_manager.Users_fetch_user(Users_table, User_ID)
			Output += f"{User_infos['Pseudo']} ({User_infos['ID']})\n"
			# Membership renewed
			if not User_infos["Last_renewal"] or User_infos["Last_renewal"] < Date:
				User_infos["Medium"] = "HelloAsso"
				User_infos["Last_renewal"] = Date
				User_infos["Contribution"] = Contribution
				User_infos["Mail"] = Mail
			# In case a file from a previous year is imported
			if Date < User_infos["First_membership"]:
				User_infos["First_membership"] = Date
			DB_manager.Users_manage_user(Users_table, "Update", User_infos)
		else:
			if not User_infos["Pseudo"]:
				Pseudo_from_name = User_infos['First_name'] + "." + User_infos['Last_name'][0]
				Pseudo_from_mail = User_infos["Mail"].split("@")[0].capitalize()
				Pseudo_from_mail = Pseudo_from_mail.split("+")[0]
				Pseudo_from_mail = Pseudo_from_mail.split("-")[0]
				if User_infos["First_name"] and User_infos["Last_name"]:
					User_infos["Pseudo"] = Pseudo_from_name
				elif User_infos["Mail"]:
					User_infos["Pseudo"] = Pseudo_from_mail
				elif User_infos["First_name"]:
					User_infos["Pseudo"] = User_infos["First_name"]
				else:
					Pseudo = None
			Output += f"→→→→→→→→→→ New: {User_infos['Pseudo']}\n"
			# Complete the dictionary, in addition to what we got from the CSV
			User_infos["ML_pseudo"] = None
			User_infos["Wiki_pseudo"] = None
			User_infos["IRC_pseudo"] = None
			User_infos["Forum_pseudo"] = None
			User_infos["Discord_pseudo"] = None
			User_infos["Discord_expiration"] = None
			User_infos["Avatar"] = None
			User_infos["First_membership"] = Date
			User_infos["Medium"] = "HelloAsso"
			DB_manager.Users_manage_user(Users_table, "Add", User_infos)

	print(Output)
