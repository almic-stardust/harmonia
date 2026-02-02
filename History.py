# -*- coding: utf-8 -*-

import datetime
import os
import re

from Config_manager import Config
import DB_manager
import Attachments_manager

async def Message_added(Table, Author_name, Chan, Message):
	# Don’t record the content of the bot’s log chan
	#if Config.get("log_chan") == str(Chan):
	#	return

	# Set 0 if it’s a DM
	Server_ID = Message.guild.id if Message.guild else 0
	Replied_message_ID = 0
	if Message.reference and Message.reference.resolved:
		Replied_message_ID = Message.reference.resolved.id
	if len(Message.attachments) > 0:
		Attachments_filenames = await Attachments_manager.Download_from_Discord(Table, Message)
	else:
		Attachments_filenames = []
	DB_manager.History_addition(Table,
			# Time in UTC without timezone (MariaDB DATETIME doesn’t support timezone offsets)
			Message.created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None),
			Server_ID, Chan.id, Message.id,
			Replied_message_ID,
			Author_name, Message.content, Attachments_filenames
	)

def Message_edited(Table, Keep, Message):
	DB_entry = DB_manager.History_fetch_message(Table, Message.id)
	if not DB_entry:
		print(f"[History] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
		return
	Content = Message.content
	Updated_filenames = []
	Old_attachments = DB_entry[7] if DB_entry[7] else []
	if Old_attachments:
		New_attachments = []
		Updated_filenames = []
		# Must be a list because Attachments_manager.Delete() is also used by Message_deleted()
		Removed_attachments = []
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
				Removed_attachments.append(Attachment)
		if Removed_attachments:
			Updated_filenames += Attachments_manager.Delete(Table, Keep, Removed_attachments)
			Content = f"The file {Removed_attachments[0]} was deleted.\n\n{Content}"
	DB_manager.History_edition(Table, Keep,
			Message.id, datetime.datetime.now().isoformat(), Content, Updated_filenames
	)

def Message_deleted(Table, Keep, Message_ID):
	DB_entry = DB_manager.History_fetch_message(Table, Message_ID)
	if not DB_entry:
		print(f"[History] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
		return
	Updated_filenames = []
	Attachments_filenames = DB_entry[7] if DB_entry[7] else []
	if Attachments_filenames:
		Updated_filenames = Attachments_manager.Delete(Table, Keep, Attachments_filenames)
	DB_manager.History_deletion(Table, Keep,
			Message_ID, datetime.datetime.now().isoformat(), Updated_filenames
	)
