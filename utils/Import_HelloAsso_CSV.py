#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import fnmatch
import csv
import datetime

from Config_manager import Config
import DB_manager

if not Config["Enabled_sections"]["Users"]:
	print("Error: For this script to be of any use, the \"users\" section must be enabled in the config file.")
	sys.exit(1)
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

	Users_table = Config["Users"]["DB_table"]
	Users = DB_manager.Users_fetch_users(Users_table)
	CSV_content = csv.DictReader(CSV_file, delimiter=";")
	Output = ""

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
	# Determine the year of this CSV file, assuming that a membership campaign can start at the end
	# of the previous year, but should not extend into the beginning of the following year. So the
	# year of the file should correspond to that of the newest membership.
	Last_date = Parse_date(Normalized_lines[-1].get("date de la commande"))
	File_year = Last_date.year

	for Infos_user in Users.values():
		if File_year in Infos_user["Renewals"]:
			print(f"Error: memberships for year {File_year} already exist in the DB.")
			print("This script must not be run twice on the same CSV file.")
			sys.exit(1)
	print(f"\n>>> Year {File_year} <<<\n")

	for Line in Normalized_lines:
		Mail = Line.get("email", "").strip().lower()
		if not Mail:
			Mail = Line.get("email payeur", "").strip().lower()
		# First names can be compound
		First_name = Line.get("prénom adhérent", "").strip().title()
		# Last names can be compound, or contain spaces or apostrophes
		Last_name = Line.get("nom adhérent", "").strip().title()
		Pseudo = Line.get("pseudo", "").strip()
		Date = Parse_date(Line.get("date de la commande"))
		Contribution = Parse_contribution(Line.get("montant tarif"))
		Infos_user = {
				"Pseudo": Pseudo,
				"Mail": Mail,
				"First_name": First_name,
				"Last_name": Last_name,
				"Contribution": Contribution
		}

		User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
		# Renewal
		if User_ID:
			Infos_user = Users[User_ID]
			Output += f"{Infos_user['Pseudo']} ({Infos_user['ID']})\n"
			# Some infos are updated only if it’s the latest renewal
			Renewals = []
			for Dates in Infos_user["Renewals"].values():
				Renewals.extend(Dates)
			Renewals.sort()
			Last_renewal = Renewals[-1] if len(Renewals) > 0 else None
			if not Last_renewal or Last_renewal < Date:
				Infos_user["Mail"] = Mail
				Infos_user["Last_medium"] = "HelloAsso"
			if Contribution > 0:
				if File_year not in Infos_user["Contributions"]:
					Infos_user["Contributions"][File_year] = Contribution
				# If a member makes multiple contributions in the same file, add them together, and
				# the total becomes the member’s contribution for that year of membership.
				# Handling this case is the reason why this script must not be run twice on the same
				# CSV file.
				else:
					Infos_user["Contributions"][File_year] += Contribution
			# Import regardless of whether it’s the newest CSV file, or one from a previous year
			if File_year not in Infos_user["Renewals"]:
				Infos_user["Renewals"][File_year] = []
			if Date not in Infos_user["Renewals"][File_year]:
				Infos_user["Renewals"][File_year].append(Date)
				Infos_user["Renewals"][File_year].sort()
			DB_manager.Users_manage_user(Users_table, "Update", Infos_user)
		# New member
		else:
			if not Infos_user["Pseudo"]:
				Pseudo_from_name = Infos_user['First_name'] + "." + Infos_user['Last_name'][0]
				Pseudo_from_mail = Infos_user["Mail"].split("@")[0].capitalize()
				Pseudo_from_mail = Pseudo_from_mail.split("+")[0]
				Pseudo_from_mail = Pseudo_from_mail.split("-")[0]
				if Infos_user["First_name"] and Infos_user["Last_name"]:
					Infos_user["Pseudo"] = Pseudo_from_name
				elif Infos_user["Mail"]:
					Infos_user["Pseudo"] = Pseudo_from_mail
				elif Infos_user["First_name"]:
					Infos_user["Pseudo"] = Infos_user["First_name"]
				else:
					Pseudo = None
			Output += f"→→→→→→→→→→ New: {Infos_user['Pseudo']}\n"
			# Complete the dictionary, in addition to what we got from the CSV
			Infos_user["ML_pseudo"] = None
			Infos_user["Wiki_pseudo"] = None
			Infos_user["IRC_pseudo"] = None
			Infos_user["Forum_pseudo"] = None
			Infos_user["Discord_username"] = None
			Infos_user["Pseudo_displayed_on_Discord"] = None
			Infos_user["Discord_expiration_for_IRC"] = 365
			Infos_user["Avatar_URL"] = None
			Infos_user["Renewals"] = {File_year: [Date]}
			Infos_user["Contributions"] = {File_year: Contribution} if Contribution > 0 else None
			Infos_user["Last_medium"] = "HelloAsso"
			DB_manager.Users_manage_user(Users_table, "Add", Infos_user)

	print(Output)
