# -*- coding: utf-8 -*-

import datetime
from zoneinfo import ZoneInfo
import aiohttp
import glob
import os
import re
import smtplib

from Config_manager import Config
import DB_manager

Users_enabled = Config["Enabled_sections"]["Users"]
if Users_enabled:
	Users_table = Config["Users"]["DB_table"]

###############################################################################
# Handling attachments
###############################################################################

async def Download_files(Table, Storage_folder, Date, Files_to_download, Max_size):
	# Wikimedia wants a User-Agent identifying the application
	Headers = {"User-Agent": "HarmoniaBot/0.1"}
	Downloaded_filenames = []
	Oversized_files = []
	if not os.path.exists(Storage_folder):
		os.makedirs(Storage_folder)
	async with aiohttp.ClientSession() as Session:
		for File_to_download in Files_to_download:
			try:
				async with Session.get(File_to_download["URL"], headers=Headers) as Response:
					if Response.status != 200:
						print(f"[History] Warning: Response.status = {Response.status}")
						continue
					File_size = int(Response.headers.get("Content-Length", 0))
					# Max_size > 0 to check if a size limit is set
					# File_size > 0 in case the site don’t send the Content-Length header
					if Max_size > 0 and File_size > 0 and File_size > Max_size:
						Oversized_files.append(File_to_download["URL"])
						continue
					Destination_filename = File_to_download["Destination_filename"]
					File_path = os.path.join(Storage_folder, Destination_filename)
					with open(File_path, "wb") as File:
						File.write(await Response.read())
					Downloaded_filenames.append(Destination_filename)
			except Exception as Error:
				print(f"[History] Warning: {Error}")
	if Oversized_files:
		print(f"[History] Warning: Oversized file\n{Oversized_files}")
	return Downloaded_filenames

def Handle_duplicate_filenames(Table, Storage_folder, Date, Attachments):

	Assignments = []
	Assigned_base_names = {}

	# Group the attachments by the final base name that will be assigned to them.
	# This first pass is necessary because when someone sends a message by copy-pasting several
	# different images, Discord names them all image.png. Therefore they’re duplicates, even though
	# they haven’t been saved on disk yet.
	for Attachment in Attachments:
		Base_name, File_ext = os.path.splitext(Attachment.filename)
		# Em dashes would conflict with the handling of duplicates, but Discord already removes them
		#Base_name = Base_name.replace("—", "_")
		Base_name = f"{Date}—{Base_name}"
		Key = (Base_name, File_ext)
		if Key not in Assigned_base_names:
			Assigned_base_names[Key] = []
		Assigned_base_names[Key].append(Attachment)

	for (Base_name, File_ext), Attachments_list in Assigned_base_names.items():
		Matching_files = set()
		Unnumbered_filename = None
		Existing_suffixes = []

		# Compare the filenames in this message with those already on disk
		File_pattern = os.path.join(Storage_folder, f"{Base_name}*{File_ext}")
		for Path in glob.glob(File_pattern):
			Matching_files.add(os.path.basename(Path))
		for Filename in Matching_files:
			Stem = os.path.splitext(Filename)[0]
			# Stem can have the format YYYYMMDD—Name_on_Discord[—Number]_DELETED.ext
			if Stem.endswith("_DELETED"):
				Stem = Stem.removesuffix("_DELETED")
			Parts = Stem.split("—")
			Prefix_is_date = (
					len(Parts) > 0
					and len(Parts[0]) == 8
					and Parts[0].isdigit()
			)
			# If an existing filename matches the format YYYYMMDD—Name_on_Discord.ext, it means that
			# it has been stored without duplicate so far, and therefore wasn’t numbered. Now it
			# must be renamed, on disk and in the DB, to add "—1" at the end.
			if len(Parts) == 2 and Prefix_is_date:
				Unnumbered_filename = Filename
			# If the filename matches YYYYMMDD—Name_on_Discord—Number.ext
			elif len(Parts) == 3 and Prefix_is_date and Parts[2].isdigit():
				Existing_suffixes.append(int(Parts[2]))

		Numbering_needed = (
				# Duplicates in the same message
				len(Attachments_list) > 1
				# Duplicates present on disk
				or Unnumbered_filename is not None
				or len(Existing_suffixes) > 0
		)
		if not Numbering_needed:
			Assignments.append(
				(Attachments_list[0], f"{Base_name}{File_ext}")
			)
			continue

		if Unnumbered_filename:
			Old_name = Unnumbered_filename
			Old_path = os.path.join(Storage_folder, Old_name)
			Stem = os.path.splitext(Old_name)[0]
			New_name = f"{Base_name}—1{File_ext}"
			# If the file was deleted but kept in storage, it still needs to be numbered
			if Stem.endswith("_DELETED"):
				New_name = f"{Base_name}—1_DELETED{File_ext}"
			New_path = os.path.join(Storage_folder, New_name)
			# Only rename if the file actually exists on disk
			if os.path.exists(Old_path):
				os.rename(Old_path, New_path)
			DB_manager.History_update_filename(Table, Old_name, New_name)
			Existing_suffixes.append(1)

		# Assign a unique number at the end of the base name of the current file, by determining the
		# biggest suffix that has already been assigned (even if one of the duplicate files has been
		# deleted from Discord and not kept in the storage folder).
		# The default value applies when Existing_suffixes remains empty (no duplicates on disk, but
		# two files with the same name uploaded in one message)
		Next_suffix = max(Existing_suffixes, default=0) + 1
		for Attachment in Attachments_list:
			Assignments.append(
				(
					Attachment,
					f"{Base_name}—{Next_suffix}{File_ext}",
				)
			)
			Next_suffix += 1

	return Assignments

async def Download_from_Discord(Table, Message):
	from Discord_manager import Register_destination_in_MPD
	Storage_folder = Config["History"].get("Storage_folder")
	Other_source_folder = os.path.join(Storage_folder, "other_sources")
	Date = Message.created_at.astimezone(ZoneInfo("Europe/Paris")).strftime("%Y%m%d")
	Attachments = []
	Downloaded_filenames = []
	Assignments = Handle_duplicate_filenames(Table, Storage_folder, Date, Message.attachments)
	for Attachment, Destination_filename in Assignments:
		Discord_filename = Attachment.filename

		# When Discord changes the filename, duplicates (see the comment just below) can only be
		# handled in Discord_manager.py
		Register_destination_in_MPD(Discord_filename, Destination_filename)

		# Check if the filename is already present in the other_sources folder, as it may have
		# been downloaded from another source than Discord. And if the attachments are images, the
		# version we receive from Discord has gone through their processing, which can recompress
		# images. Since the original is already on disk, there’s no point in keeping a version
		# potentially degraded by Discord.
		# Discord can change filenames, so those received from Discord won’t necessarily match the
		# original filenames. And since on_message() from Discord_manager.py brings us here at a
		# time when we have yet no trace of the original filename, that means the following check
		# will miss some files. Nevertheless, checking here will work for the majority of files, and
		# avoids writing them twice on disk.

		Other_source_file_path = os.path.join(Other_source_folder, Discord_filename)
		# The file already exists → move it
		if os.path.exists(Other_source_file_path):
			Destination_path = os.path.join(Storage_folder, Destination_filename)
			os.replace(Other_source_file_path, Destination_path)
			Downloaded_filenames.append(Destination_filename)
		# Otherwise → queue it for download
		else:
			Attachments.append({
					"URL": Attachment.url,
					"Destination_filename": Destination_filename
			})

	if len(Attachments) > 0:
		# A temporary list, because the same message may contain files with names changed or not by
		# Discord, and Downloaded_filenames can already contain filenames not changed.
		# Max_size = 0 because Discord sets its own limit on attachments’ size (today it’s 10 MB)
		Temp_list = await Download_files(Table, Storage_folder, Date, Attachments, 0)
		Downloaded_filenames.extend(Temp_list)
	return Downloaded_filenames

def Delete_attachment(Table, Keep, Attachments):
	Updated_filenames = []
	Storage_folder = Config["History"].get("Storage_folder")
	if not os.path.exists(Storage_folder):
		print("[History] Warning: The folder for the attachments isn’t accessible.")
		return
	# Deleting a single attachment → create a list with that single item
	if not isinstance(Attachments, list):
		Attachments = [Attachments]
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

###############################################################################
# Handling messages
###############################################################################

async def Message_added(Table, Author_name, Chan_ID, Message, Text, Relayed):
	# Don’t record the content of the bot’s log chan
	#if Config.get("log_chan") == str(Chan):
	#	return
	# An UTC timestamp, used for the creation_date field, and for the index of the dictionary in the
	# content_history field.
	# The creation_date is redundant, but useful for efficient date comparisons in SQL, avoiding
	# JSON extraction. MariaDB DATETIME doesn’t support timezone offsets, so the time is in UTC
	# without timezone.
	# The creation_field cannot be automatically created by MariaDB, because the bot might be
	# retrieving old messages.
	Date = Message.created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
	# Set 0 if it’s a DM
	Server_ID = Message.guild.id if Message.guild else 0
	Replied_message_ID = 0
	if Message.reference and Message.reference.resolved:
		Replied_message_ID = Message.reference.resolved.id
	if len(Message.attachments) > 0:
		Attachments_filenames = await Download_from_Discord(Table, Message)
	else:
		Attachments_filenames = []
	DB_manager.History_addition(Table,
			Date, Server_ID, Chan_ID, Message.id,
			Replied_message_ID,
			Author_name, Text, Attachments_filenames, Relayed
	)

def Message_edited(Table, Message):
	Infos_message = DB_manager.History_fetch_message(Table, Message.id)
	if not Infos_message:
		print("[History] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
		return
	Keep = True
	if Users_enabled:
		Infos_user = {"Pseudo": Infos_message["User"]}
		User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
		if User_ID:
			Users = DB_manager.Users_fetch_users(Users_table)
			Infos_user = Users[User_ID]
			Keep = Infos_user["History_keep_all"]
	Date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	New_text = Message.content
	Updated_filenames = []
	Deleted = []
	Old_attachments = Infos_message["Attachments"]
	if Old_attachments:
		New_attachments = []
		Updated_filenames = []
		for Attachment in Message.attachments:
			New_attachments.append(Attachment.filename)
		for Attachment in Old_attachments:
			# If a file has already been deleted, no need to process it a second time.
			if "_DELETED" in Attachment:
				Updated_filenames.append(Attachment)
				continue
			# The comparaison must be on the filenames sent on Discord: revert the modifications
			# made when a filename is stored in the DB
			Base_name, File_ext = os.path.splitext(Attachment)
			# Remove leading date prefix
			Base_name = re.sub(r"^\d{8}—", "", Base_name)
			# Remove trailing copy index (—number)
			Base_name = re.sub(r"—\d+$", "", Base_name)
			Normalized_old_name = Base_name + File_ext
			if Normalized_old_name in New_attachments:
				Updated_filenames.append(Attachment)
			else:
				Deleted_files = Delete_attachment(Table, Keep, Attachment)
				Updated_filenames.extend(Deleted_files)
				Deleted.extend(Deleted_files)
	DB_manager.History_edition(Table, Keep, Message.id, Date, New_text, Updated_filenames, Deleted)

def Message_deleted(Table, Message_ID):
	Date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	Infos_message = DB_manager.History_fetch_message(Table, Message_ID)
	if not Infos_message:
		print("[History] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
		return
	Keep = True
	if Users_enabled:
		Infos_user = {"Pseudo": Infos_message["User"]}
		User_ID = DB_manager.Users_check_presence(Users_table, Infos_user)
		if User_ID:
			Users = DB_manager.Users_fetch_users(Users_table)
			Infos_user = Users[User_ID]
			Keep = Infos_user["History_keep_all"]
	Updated_filenames = []
	Attachments_filenames = Infos_message["Attachments"]
	if Attachments_filenames:
		Updated_filenames = Delete_attachment(Table, Keep, Attachments_filenames)
	DB_manager.History_deletion(Table, Keep, Message_ID, Date, Updated_filenames)
