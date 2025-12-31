# -*- coding: utf-8 -*-

import sys
import datetime
from zoneinfo import ZoneInfo
import json
import aiohttp
import os
import glob
import smtplib
import email.utils
from email.mime.text import MIMEText

from Config_manager import Config
import DB_manager

async def Download_attachments(Table, Message):
	global History_table
	Attachments_filenames = []
	Oversized_files = []
	Max_size = 10485760 # 10 MB
	Storage_dir = Config["history"].get("storage_folder")
	if not os.path.exists(Storage_dir):
		os.makedirs(Storage_dir)
	for Attachment in Message.attachments:
		async with aiohttp.ClientSession() as Session:
			async with Session.get(Attachment.url) as Response:
				if Response.status == 200:
					File_size = int(Response.headers.get("Content-Length", 0))
					if File_size > Max_size:
						Oversized_files.append(Attachment.url)
						Attachments_filenames.append(Attachment.url)
					else:
						Date = Message.created_at.astimezone(ZoneInfo("Europe/Paris")).strftime('%Y%m%d')
						Base_name, File_ext = os.path.splitext(Attachment.filename)
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
							# AAAAMMJJ—Name_on_Discord—Number[_DELETED].ext, therefore no need to
							# rename them.
							# Assign a unique number at the end of the base name of the current
							# file, by determining the biggest suffix that has already been
							# assigned (even if one of the duplicate files has been deleted from
							# Discord and not kept in the storage folder).
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
	if Oversized_files:
		#Notification_for_oversized_files(Oversized_files)
		print("Notification_for_oversized_files")
	Attachments_filenames = json.dumps(Attachments_filenames)
	return Attachments_filenames

def Delete_attachments(Table, Keep, Attachments):
	Updated_filenames = []
	New_filename = None
	Storage_dir = Config["history"].get("storage_folder")
	if not os.path.exists(Storage_dir):
		print(f"Warning: The folder where the attachments were stored isn’t accessible.")
		return
	for Filename in Attachments:
		File_path = os.path.join(Storage_dir, Filename)
		if os.path.exists(File_path):
			if Keep:
				Base_name, File_ext = os.path.splitext(Filename)
				New_filename = f"{Base_name}_DELETED{File_ext}"
				New_file_path = os.path.join(Storage_dir, New_filename)
				os.rename(File_path, New_file_path)
			else:
				try:
					os.remove(File_path)
				except OSError as e:
					print(f"Warning: can’t delete file {Filename}: {e}")
		else:
			# Keep the invalid filename in the DB, to avoid losing all reference
			New_filename = Filename
			print(f"Warning: File {Filename} not found.")
		if New_filename:
			Updated_filenames.append(New_filename)
	return json.dumps(Updated_filenames)

async def Message_added(Table, Author_name, Chan, Message):
	# Don’t record the content of the bot’s log chan
	#if Config.get("log_chan") == str(Chan):
	#	return

	# Set 0 if it’s a DM
	Server_id = Message.guild.id if Message.guild else 0
	Replied_message_id = 0
	if Message.reference and Message.reference.resolved:
		Replied_message_id = Message.reference.resolved.id
	if len(Message.attachments) > 0:
		Attachments = await Download_attachments(Table, Message)
	else:
		Attachments = None
	DB_manager.History_addition(Table,
			Message.created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None),
			Server_id, Chan.id, Message.id,
			Replied_message_id,
			Author_name, Message.content, Attachments
	)

def Message_edited(Table, Keep, Message):
	DB_entry = DB_manager.History_fetch_message(Table, Message.id)
	if DB_entry:
		DB_manager.History_edition(Table, Keep,
				Message.id, datetime.datetime.now().isoformat(), Message.content
		)
	else:
		print(f"[History] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")

def Message_deleted(Table, Keep, Message_id):
	DB_entry = DB_manager.History_fetch_message(Table, Message_id)
	if DB_entry:
		Updated_filenames = []
		Attachments = json.loads(DB_entry[7]) if DB_entry[7] else []
		if Attachments:
			Updated_filenames = Delete_attachments(Table, Keep, Attachments)
		DB_manager.History_deletion(Table, Keep,
				Message_id, datetime.datetime.now().isoformat(), Updated_filenames
		)
	else:
		print(f"[History] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
