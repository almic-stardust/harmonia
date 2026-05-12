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

	for User_infos in Users.values():
		if File_year in User_infos["Renewals"]:
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
		User_infos = {
				"Pseudo": Pseudo,
				"Mail": Mail,
				"First_name": First_name,
				"Last_name": Last_name,
				"Contribution": Contribution
		}

		User_ID = DB_manager.Users_check_presence(Users_table, User_infos)
		# Renewal
		if User_ID:
			User_infos = Users[User_ID]
			Output += f"{User_infos['Pseudo']} ({User_infos['ID']})\n"
			# Some infos are updated only if it’s the latest renewal
			Renewals = []
			for Dates in User_infos["Renewals"].values():
				Renewals.extend(Dates)
			Renewals.sort()
			Last_renewal = Renewals[-1] if len(Renewals) > 0 else None
			if not Last_renewal or Last_renewal < Date:
				User_infos["Mail"] = Mail
				User_infos["Last_medium"] = "HelloAsso"
			if Contribution > 0:
				if File_year not in User_infos["Contributions"]:
					User_infos["Contributions"][File_year] = Contribution
				# If a member makes multiple contributions in the same file, add them together, and
				# the total becomes the member’s contribution for that year of membership.
				# Handling this case is the reason why this script must not be run twice on the same
				# CSV file.
				else:
					User_infos["Contributions"][File_year] += Contribution
			# Import regardless of whether it’s the newest CSV file, or one from a previous year
			if File_year not in User_infos["Renewals"]:
				User_infos["Renewals"][File_year] = []
			if Date not in User_infos["Renewals"][File_year]:
				User_infos["Renewals"][File_year].append(Date)
				User_infos["Renewals"][File_year].sort()
			DB_manager.Users_manage_user(Users_table, "Update", User_infos)
		# New member
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
			User_infos["Renewals"] = {File_year: [Date]}
			User_infos["Contributions"] = {File_year: Contribution} if Contribution > 0 else None
			User_infos["Last_medium"] = "HelloAsso"
			DB_manager.Users_manage_user(Users_table, "Add", User_infos)

	print(Output)
