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
async def Download(Table, Storage_folder, Date, Attachments, Max_size):
	# Wikimedia wants a User-Agent identifying the application
	Headers = {"User-Agent": "HarmoniaBot/0.1"}
	Downloaded_filenames = []
	Oversized_files = []
	if not os.path.exists(Storage_folder):
		os.makedirs(Storage_folder)
	async with aiohttp.ClientSession() as Session:
		for Attachment in Attachments:
			try:
				async with Session.get(Attachment["URL"], headers=Headers) as Response:
					if Response.status != 200:
						print(f"[Attachments] Warning: Response.status =", Response.status)
						continue
					File_size = int(Response.headers.get("Content-Length", 0))
					# Max_size > 0 to check if a size limit is set
					# File_size > 0 in case the site don’t send the Content-Length header
					if Max_size > 0 and File_size > 0 and File_size > Max_size:
						Oversized_files.append(Attachment["URL"])
						continue
					File_path = os.path.join(Storage_folder, Attachment["Destination_filename"])
					with open(File_path, "wb") as File:
						File.write(await Response.read())
					Downloaded_filenames.append(Attachment["Destination_filename"])
			except Exception as Error:
				print(f"[Attachments] Warning: {Error}")
	if Oversized_files:
		print(f"[Attachments] Warning: Oversized file\n{Oversized_files}")
	return Downloaded_filenames

async def Download_from_Discord(Table, Message):

	Storage_folder = Config["history"].get("storage_folder")
	Other_source_folder = os.path.join(Storage_folder, "other_sources")
	Date = Message.created_at.astimezone(ZoneInfo("Europe/Paris")).strftime('%Y%m%d')
	Downloaded_filenames = []
	Attachments = []

	for Attachment in Message.attachments:
		Base_name, File_ext = os.path.splitext(Attachment.filename)
		# Em dashes would conflict with the handling of duplicates, but Discord already removes them
		#Base_name = Base_name.replace("—", "_")
		Base_name = f"{Date}—" + Base_name
		Destination_filename = f"{Base_name}{File_ext}"
		File_pattern = os.path.join(Storage_folder, f"{Base_name}*{File_ext}")
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
				Stored_new_path = os.path.join(Storage_folder, Stored_new_name)
				os.rename(Stored_old_path, Stored_new_path)
				DB_manager.History_update_filename(Table,
						Stored_old_name, Stored_new_name
				)
				Destination_filename = f"{Base_name}—2{File_ext}"
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
					# Destination_filename could be AAAAMMJJ—Name_on_Discord—Number_DELETED.ext
					Parts[-1] = Parts[-1].replace("_DELETED", "")
					# If the filename matches AAAAMMJJ—Name_on_Discord—Number.ext
					if len(Parts) == 3 and Parts[-1].isdigit():
						Duplicates_suffixes.append(int(Parts[-1]))
				Suffix = max(Duplicates_suffixes) + 1
				Destination_filename = f"{Base_name}—{Suffix}{File_ext}"

		# Check if the filename is already present in the other_sources folder, as it may have
		# been downloaded from another source than Discord.
		# Discord can change filenames, so those received from Discord will not necessarily match
		# the original filenames. And since on_message() from Discord_manager.py brings us here when
		# we have yet no trace of the original filename, then checking here will miss some files.
		# Nevertheless, checking here will work for the vast majority of files, and avoids writing
		# them twice on the disk. Thus slightly reducing its wear.
		Discord_filename = Attachment.filename
		Other_source_file_path = os.path.join(Other_source_folder, Discord_filename)
		if os.path.exists(Other_source_file_path):
			Destination_path = os.path.join(Storage_folder, Destination_filename)
			shutil.move(Other_source_file_path, Destination_path)
			Downloaded_filenames.append(Destination_filename)
			continue
		else:
			Attachments.append({
				"URL": Attachment.url,
				"Destination_filename": Destination_filename
			})

	if len(Attachments) > 0:
		# Max_size = 0 because Discord sets its own limit on attachments’ size (today it’s 10 MB)
		Downloaded_filenames = await Download(Table, Storage_folder, Date, Attachments, 0)
	return Downloaded_filenames

def Delete(Table, Keep, Attachments):
	Updated_filenames = []
	Storage_folder = Config["history"].get("storage_folder")
	if not os.path.exists(Storage_folder):
		print(f"Warning: The folder where the attachments were stored isn’t accessible.")
		return
	for Filename in Attachments:
		# File already deleted: don’t tag it twice, instead keep it as it is
		if Keep and "_DELETED" in Filename:
			Updated_filenames.append(Filename)
			continue
		File_path = os.path.join(Storage_folder, Filename)
		if Keep:
			if os.path.exists(File_path):
				Base_name, File_ext = os.path.splitext(Filename)
				New_filename = f"{Base_name}_DELETED{File_ext}"
				New_file_path = os.path.join(Storage_folder, New_filename)
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
