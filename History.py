# -*- coding: utf-8 -*-

import datetime
import os
import re

#from Config_manager import Config
import DB_manager
import Attachments_manager

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
		Attachments_filenames = await Attachments_manager.Download_from_Discord(Table, Message)
	else:
		Attachments_filenames = []
	DB_manager.History_addition(Table,
			Date, Server_ID, Chan_ID, Message.id,
			Replied_message_ID,
			Author_name, Text, Attachments_filenames, Relayed
	)

def Message_edited(Table, Keep, Message):
	Infos_message = DB_manager.History_fetch_message(Table, Message.id)
	if not Infos_message:
		print(f"[History] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
		return
	Date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	New_text = Message.content
	Updated_filenames = []
	Old_attachments = Infos_message["Attachments"]
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
		if len(Removed_attachments) > 0:
			Updated_filenames += Attachments_manager.Delete(Table, Keep, Removed_attachments)
			New_text = f"The file {Removed_attachments[0]} was deleted.\n\n{New_text}"
	DB_manager.History_edition(Table, Keep, Message.id, Date, New_text, Updated_filenames)

def Message_deleted(Table, Keep, Message_ID):
	Date = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
	Infos_message = DB_manager.History_fetch_message(Table, Message_ID)
	if not Infos_message:
		print(f"[History] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
		return
	Updated_filenames = []
	Attachments_filenames = Infos_message["Attachments"]
	if Attachments_filenames:
		Updated_filenames = Attachments_manager.Delete(Table, Keep, Attachments_filenames)
	DB_manager.History_deletion(Table, Keep, Message_ID, Date, Updated_filenames)
