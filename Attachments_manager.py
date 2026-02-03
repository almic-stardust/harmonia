# -*- coding: utf-8 -*-

import datetime
from zoneinfo import ZoneInfo
import aiohttp
import glob
import os
import shutil
import smtplib
import email.utils
from email.mime.text import MIMEText

from Config_manager import Config
import DB_manager

# Attachments is a variable, so this file is named Attachments_manager.py
async def Download(Table, Source, Date, Attachments, Max_size):
	# Wikimedia wants a User-Agent identifying the application
	Headers = {"User-Agent": "HarmoniaBot/0.1"}
	if Source == "Discord":
		Storage_dir = Config["history"].get("storage_folder")
	else:
		Storage_dir = Config["history"].get("storage_folder") + "/other_sources"
	Attachments_filenames = []
	Oversized_files = []
	if not os.path.exists(Storage_dir):
		os.makedirs(Storage_dir)
	async with aiohttp.ClientSession() as Session:
		for Attachment in Attachments:
			try:
				async with Session.get(Attachment["URL"], headers=Headers) as Response:
					if Response.status != 200:
						print(f"[Attachments] Warning: Response.status =", Response.status)
						continue
					File_size = int(Response.headers.get("Content-Length", 0))
					# Max_size > 0 to check if a size limit is set
					# File_size > 0 because some sites don’t send the Content-Length header
					if Max_size > 0 and File_size > 0 and File_size > Max_size:
						Oversized_files.append(Attachment["URL"])
					Base_name, File_ext = os.path.splitext(Attachment["Filename"])
					Base_name = Base_name.replace("—", "_")
					Base_name = f"{Date}—" + Base_name
					Filename = f"{Base_name}{File_ext}"
					File_pattern = os.path.join(Storage_dir, f"{Base_name}*{File_ext}")
					Matching_files = glob.glob(File_pattern)
					if Matching_files:
						# If there’s only one file, rename it to add “—1” at the end of its base
						# name, and put “—2” in the base name of the current file
						if len(Matching_files) == 1:
							Stored_old_path = Matching_files[0]
							Stored_old_name = os.path.basename(Stored_old_path)
							Stored_old_base_name = os.path.splitext(Stored_old_path)[0]
							Stored_new_name = f"{Base_name}—1{File_ext}"
							# If the file was deleted but kept in storage
							if Stored_old_base_name.endswith("_DELETED"):
								Stored_new_name = f"{Base_name}—1_DELETED{File_ext}"
							Stored_new_path = os.path.join(Storage_dir, Stored_new_name)
							os.rename(Stored_old_path, Stored_new_path)
							DB_manager.History_update_filename(Table,
									Stored_old_name, Stored_new_name
							)
							Filename = f"{Base_name}—2{File_ext}"
						# If there’s several duplicates, they will already have the format
						# AAAAMMJJ—Name_on_Discord—Number[_DELETED].ext, therefore no need to rename
						# them.
						# Assign a unique number at the end of the base name of the current file, by
						# determining the biggest suffix that has already been assigned (even if one
						# of the duplicate files has been deleted from Discord and not kept in the
						# storage folder).
						else:
							Duplicates_suffixes = []
							for File in Matching_files:
								Parts = os.path.splitext(os.path.basename(File))[0].split("—")
								# Filename could be AAAAMMJJ—Name_on_Discord—Number_DELETED.ext
								Parts[-1] = Parts[-1].replace("_DELETED", "")
								# If the filename matches AAAAMMJJ—Name_on_Discord—Number.ext
								if len(Parts) == 3 and Parts[-1].isdigit():
									Duplicates_suffixes.append(int(Parts[-1]))
							Suffix = max(Duplicates_suffixes) + 1
							Filename = f"{Base_name}—{Suffix}{File_ext}"
					File_path = os.path.join(Storage_dir, Filename)
					with open(File_path, "wb") as File:
						File.write(await Response.read())
					Attachments_filenames.append(Filename)
			except Exception as Error:
				print(f"[Attachments] Warning: {Error}")
	if Oversized_files:
		print(f"[Attachments] Warning: Oversized file\n{Oversized_files}")
	return Attachments_filenames

async def Download_from_Discord(Table, Message):
	Date = Message.created_at.astimezone(ZoneInfo("Europe/Paris")).strftime('%Y%m%d')
	Attachments = []
	for Attachment in Message.attachments:
		Attachments.append({
			"Filename": Attachment.filename,
			"URL": Attachment.url
		})
	# Max_size = 0 because Discord sets its own limit on the size of attachments (today it’s 10 MB)
	Attachments_filenames = await Download(Table, "Discord", Date, Attachments, 0)
	return Attachments_filenames

async def Download_from_IRC(Table, URLs):
	Date = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime('%Y%m%d')
	Max_size = 52428800 # 50 MB
	Attachments = []
	for URL in URLs:
		Filename = os.path.basename(URL.split("?")[0])
		# Nothing to download cause URL path does not end with a filename
		if not Filename:
			continue
		Attachments.append({
			"Filename": Filename,
			"URL": URL
		})
	Attachments_filenames = await Download(Table, "IRC", Date, Attachments, Max_size)
	return Attachments_filenames

def Delete(Table, Keep, Attachments):
	Updated_filenames = []
	Storage_dir = Config["history"].get("storage_folder")
	if not os.path.exists(Storage_dir):
		print(f"Warning: The folder where the attachments were stored isn’t accessible.")
		return
	for Filename in Attachments:
		# File already deleted: don’t tag it twice, instead keep it as it is
		if Keep and "_DELETED" in Filename:
			Updated_filenames.append(Filename)
			continue
		File_path = os.path.join(Storage_dir, Filename)
		if Keep:
			if os.path.exists(File_path):
				Base_name, File_ext = os.path.splitext(Filename)
				New_filename = f"{Base_name}_DELETED{File_ext}"
				New_file_path = os.path.join(Storage_dir, New_filename)
				os.rename(File_path, New_file_path)
			else:
				print(f"Warning: File {Filename} not found.")
				# To avoid losing all reference, keep the filename in the DB but mark it invalid
				New_filename = f"INVALID_{Filename}"
			Updated_filenames.append(New_filename)
		else:
			try:
				os.remove(File_path)
			except OSError as Error:
				print(f"Warning: can’t delete file {Filename}: {Error}")
	return Updated_filenames
