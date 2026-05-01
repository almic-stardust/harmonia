#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import fnmatch
import csv
import datetime
from pprint import pprint

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
	if not Date:
		return None
	else:
		try:
			return datetime.datetime.strptime(Date, "%d/%m/%Y %H:%M")
		except Exception as Error:
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
	Users = []
	CSV_content = csv.DictReader(CSV_file, delimiter=";")
	Field_names = []
	for Field_name in CSV_content.fieldnames:
		Field_names.append(Field_name.strip())
	pprint(Field_names)
	for Line in CSV_content:
		Mail = Line.get("Email payeur", "").strip()
		First_name = Line.get("Prénom adhérent", "").strip()
		Last_name = Line.get("Nom adhérent", "").strip()
		Pseudo = Line.get("Pseudo", "").strip()
		if not Pseudo:
			if Mail:
				Pseudo = Mail.split("@")[0]
			elif First_name:
				Pseudo = First_name
			else:
				Pseudo = None
		Last_renewal = Parse_date(Line.get("Date de la commande"))
		Contribution = Parse_contribution(Line.get("Montant tarif"))
		User = [Mail, Pseudo, First_name, Last_name, Last_renewal, Contribution]
		print(User)
