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

async def Message_added(Table, Server_id, Chan, Message):
	# Don’t record the content of the bot’s log chan
	#if Config.get("log_chan") == str(Chan):
	#	return
	Replied_message_id = 0
	if Message.reference and Message.reference.resolved:
		Replied_message_id = Message.reference.resolved.id
	DB_manager.History_addition(Table,
			Message.created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None),
			Server_id, Chan.id, Message.id,
			Replied_message_id,
			Message.author.name, Message.content
	)

def Message_edited(Table, Keep, Server_id, Message_id, New_content):
	DB_manager.History_edition(Table, Keep,
			Message_id, datetime.datetime.now().isoformat(), New_content
	)

def Message_deleted(Table, Keep, Server_id, Message_id):
	DB_entry = DB_manager.History_fetch_message(Table, Message_id)
	if DB_entry:
		DB_manager.History_deletion(Table, Keep,
				Message_id, datetime.datetime.now().isoformat()
		)
	else:
		print(f"[History] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
