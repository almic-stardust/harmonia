# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
from discord.ext import tasks
import time
import datetime
from zoneinfo import ZoneInfo
import asyncio
import aiohttp
import os
import re
from urllib.parse import quote

from Config_manager import Config
import DB_manager
import History
import IRC_manager
import Attachments_manager

intents = discord.Intents.default()
# Allows to receive member join/leave events
intents.members = True
# Allows to listen to messages events and provides metadata
intents.messages = True
# Allows to read the content of messages
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

History_table = Config["history"]["db_table"]
# TODO I’ll deal with that later
History_keep_all = True
HTTP_session = None
Users_buffers = {}
Map_pending_downloads = {}

###############################################################################
# General
###############################################################################

async def Init_webhooks():
	global HTTP_session
	HTTP_session = aiohttp.ClientSession()

# Exceptions in the event handlers of discord.py are swallowed, unless explicitly logged.
# As Discord bots are long-running services, it wouldn’t be acceptable for one exception in one
# event to crash or disconnect the bot, or require it to be restarted. That’s why discord.py
# prioritizes fault isolation over strict failure.
# But for development, it’s not convenient. So when not in prod, we enable exceptions in events.
@bot.event
async def on_error(event, *args, **kwargs):
	import traceback
	traceback.print_exc()

async def Stop_bot(IRC_Instance):
	await bot.close()
	if HTTP_session:
		await HTTP_session.close()
	await IRC_Instance.quit(Config["irc"].get("quit_message", "Something clever"))
	return

@bot.command()
async def quit(Context):
	if Context.author.name == Config["discord"]["bot_owner"]:
		await Stop_bot(IRC_manager.Instance)
		return

###############################################################################
# Handling messages
###############################################################################

# Handling files whose names have been changed by Discord: check once a day if there are files in
# the folder other_sources, and if so, overwrite the Discord version with the original file.
#	The files whose names aren’t modified by Discord will be managed in Attachments_manager.py, but
#	others will remain in the folder other_sources. Original filenames can’t be known from
#	Attachments_manager.py, it’s called by on_message() via History.Message_added(). And handling
#	files with modified names here in Discord_manager.py, either inside on_message() or at the end
#	of Relay_IRC_message(), that comes across a race condition.
@tasks.loop(hours=24)
async def Reconcile_downloaded_files():
	global Map_pending_downloads
	Storage_folder = Config["history"].get("storage_folder")
	Other_sources = os.path.join(Storage_folder, "other_sources")
	if not os.path.exists(Storage_folder):
		print(f"[Discord_m] Warning: The folder for the attachments isn’t accessible.")
		return
	if not os.path.exists(Other_sources):
		print(f"[Discord_m] Warning: The folder for other sources attachments isn’t accessible.")
		return
	try:
		# list() prevents runtime modification errors
		for Discord_filename, Filenames_map in list(Map_pending_downloads.items()):
			if not Filenames_map or "Original_filename" not in Filenames_map \
					or "Destination_filename" not in Filenames_map:
				continue
			Original_path = os.path.join(Other_sources, Filenames_map["Original_filename"])
			Destination_path = os.path.join(Storage_folder, Filenames_map["Destination_filename"])
			# Address the rare cases where the task runs precisely when a file with a name modified
			# by Discord is being processed in Attachments_manager.py. If the file has already been
			# downloaded in other_sources, but hasn’t yet passed through Discord, then the task
			# could move the original from other_sources to Storage_folder, just before the version
			# from Discord arrives in Storage_folder.
			# If this confluence of circumstances occurs, don’t deal with this file this time. It’ll
			# be processed during the next execution of the task.
			if not os.path.exists(Destination_path):
				continue
			if os.path.exists(Original_path):
				# Replace the file downloaded from Discord with the original one
				os.replace(Original_path, Destination_path)
			# If the file was in other_sources: once processed, its key is no longer needed.
			# If the file wasn’t there: that means its name wasn’t changed by Discord, and it had
			# already been moved in Storage_folder by Attachments_manager.py. So we can also delete
			# its key.
			del Map_pending_downloads[Discord_filename]
	except Exception as Error:
		print(f"[Discord_m] Warning: Reconcile_downloaded_files(): {Error}")

def Split_message(Message):
	# Discord limits message size = split the message into parts of 2000 characters or less
	Splitted_message = []
	Current_part = ""
	# If the response contains several lines, it must be split into several strings
	Lines = Message.split("\n")
	for Line in Lines:
		# The +1 is for the newline character
		if len(Current_part) + len(Line) + 1 > 2000:
			Splitted_message.append(Current_part)
			# Start a new part
			Current_part = Line
		else:
			if Current_part:
				Current_part += "\n" + Line
			else:
				Current_part = Line
	# Add the remaining part (the string Message = X parts of 2000c + a remaining part)
	if Current_part:
		Splitted_message.append(Current_part)
	return Splitted_message

def Is_command(Message):
	return Message.content.startswith(tuple(bot.command_prefix))

async def Rate_limiter_for_IRC(Author, Author_name):

	await asyncio.sleep(5)
	Buffer = Users_buffers.get(Author.id)
	if not Buffer:
		return
	Messages = []
	for _, Message in Buffer["messages"]:
		Messages.extend(IRC_manager.Split_into_IRC_messages(Message))
	Messages_to_relay = None

	# Discord allows messages of 2000 characters with line breaks, which makes difficult to
	# distinguish between legitimate messages with several paragraphs, and careless copy-pastes. At
	# least the damage will be limited to 10 lines
	if len(Buffer["messages"]) == 1 and len(Messages) <= 10:
		Messages_to_relay = Messages
	# If someone sent up to 3 short messages within 5 seconds
	elif len(Buffer["messages"]) <=3 and len(Messages) <= 3:
		Messages_to_relay = Messages
	else:
		Concatenated_messages = " ".join(Messages)
		Concatenated_messages = IRC_manager.Split_into_IRC_messages(Concatenated_messages)
		# If the concatenation of messages sent by an user within 5 seconds represents no more than
		# 5 IRC messages
		if len(Concatenated_messages) <= 5:
			Messages_to_relay = Concatenated_messages
	if Messages_to_relay:
		for Message in Messages_to_relay:
			await IRC_manager.Instance.Send_message(Author_name, Message)
	else:
		# get_channel gets the channel object from the bot’s cache. fetch_channel gets it from
		# Discord, meaning a network request
		Chan = bot.get_channel(Config["discord"]["chan"])
		if not Chan:
			Chan = await bot.fetch_channel(Config["discord"]["chan"])
		await Chan.send(
				f"{Author.mention} Too many messages in a short time. Nothing was forwarded to IRC."
		)

	# Cleanup buffer once decision is made
	Users_buffers.pop(Author.id, None)

@bot.event
async def on_message(Message):

	Author = Message.author
	Chan = Message.channel
	Text = Message.content

	# Initially we bridge one chan only
	if Message.channel.id != Config["discord"]["chan"]:
		return

	# Author.display_name =	server nickname if set, otherwise global display name if set, otherwise
	# Discord username
	Author_name = Author.display_name
	# If a user has requested that the bot assign them a specific name on Discord, use it on Discord
	# but use their IRC nick in the history and their messages transferred to IRC
	if Config["users"]["discord_to_irc"].get(Author_name):
		Author_name = Config["users"]["discord_to_irc"].get(Author_name)
	# If the message comes from IRC without a webhook
	if Author == bot.user and Text.startswith("<**"):
		Match = re.match(r"<\*\*(.*?)\*\*>\s*(.*)", Text)
		if Match:
			Author_name = Match.group(1)
			Text = Match.group(2)
	await History.Message_added(History_table, Author_name, Chan, Message, Text)

	# The bot ignores its own messages (including what it posted via a webhook)
	if Author == bot.user or Message.webhook_id is not None:
		return
	# Exempt commands from buffering
	if Is_command(Message):
		# Forward the message to the bot’s command handler
		await bot.process_commands(Message)
		return

	# Prepare the message and send it to IRC
	Text = Message.clean_content.strip()
	# If the Discord message has attachments, add their URLs at the end
	if Message.attachments:
		# If there’s no message, no need to put a | before the URLs
		if Text:
			Text += " | "
		Storage_base = Config["history"].get("storage_url")
		# Ensure base ends with exactly one "/"
		Storage_base = Storage_base.rstrip("/") + "/"
		Urls = []
		for Attachment in Message.attachments:
			Filenames_map = Map_pending_downloads.get(Attachment.filename)
			if Filenames_map:
				# URL-encode safely
				URL = Storage_base + quote(Filenames_map["Destination_filename"])
			else:
				URL = Attachment.url
			Urls.append(URL)
		Text += " | ".join(Urls)
	print(f"[D] <{Author_name}> {Text}")
	# To prevent (or rather limit) flood towards IRC
	Now = time.monotonic()
	Buffer = Users_buffers.setdefault(Author.id, {"messages": [], "task": None})
	Buffer["messages"].append((Now, Text))
	# Start the rate limiter only once
	if Buffer["task"] is None:
		# Attach the task to discord.py’s managed loop
		Buffer["task"] = bot.loop.create_task(Rate_limiter_for_IRC(Author, Author_name))

def Translate_Discord_formatting_to_IRC(Message):
	# Map Discord MarkDown to IRC control codes
	Replacements = [
		(r"\*\*(.*?)\*\*", "\x02\\1\x02"),	# Bold
		(r"\*(.*?)\*", "\x1D\\1\x1D"),		# Italic
		(r"__(.*?)__", "\x1F\\1\x1F")		# Underline
	]
	for Pattern, Replacement in Replacements:
		# “count=0” replaces all matches
		Message = re.sub(Pattern, Replacement, Message, count=0)
	return Message

# Register the original filename in Map_pending_downloads
def Register_original_in_MPD(Discord_filename, Original_filename):
	global Map_pending_downloads
	Entry = Map_pending_downloads.setdefault(Discord_filename, {})
	Entry["Original_filename"] = Original_filename

# Register the destination filename in Map_pending_downloads
def Register_destination_in_MPD(Discord_filename, Destination_filename):
	global Map_pending_downloads
	Entry = Map_pending_downloads.setdefault(Discord_filename, {})
	Entry["Destination_filename"] = Destination_filename

async def Relay_IRC_message(IRC_chan, Author_name, Message):

	global Map_pending_downloads
	Files_for_Discord = []
	Pattern_image_URL = r"(https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?)"
	Images_URLs = re.findall(Pattern_image_URL, Message)

	if Images_URLs:
		Storage_folder = os.path.join(Config["history"].get("storage_folder"), "other_sources")
		Date = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y%m%d")
		Max_size = 52428800 # 50 MB
		Files_to_download = []
		for URL in Images_URLs:
			Filename = os.path.basename(URL.split("?")[0])
			Filename = Filename.replace("—", "_")
			Files_to_download.append({
				"URL": URL,
				"Destination_filename": Filename
			})
		if len(Files_to_download) > 0:
			Downloaded_filenames = await Attachments_manager.Download(
					History_table, Storage_folder, Date, Files_to_download, Max_size
			)
			for Filename in Downloaded_filenames:
				File_path = os.path.join(Storage_folder, Filename)
				Files_for_Discord.append(discord.File(File_path))
			# Remove images URLs from message body
			Message = re.sub(Pattern_image_URL, "", Message).strip()

	Message = IRC_manager.Translate_IRC_formatting_to_Discord(Message)

	Chan = Config["webhooks"].get(IRC_chan.lstrip("#"))
	if Chan:
		Webhook = discord.Webhook.from_url(Chan, session=HTTP_session)
		Avatar = f"https://robohash.org/{Author_name}.png"
		User = Config["users"]["irc_to_discord"].get(Author_name)
		if User:
			Author_name = User["discord_username"]
			# A user could request a specific username on Discord, but without requesting an avatar
			Avatar = User.get("avatar", f"https://robohash.org/{Author_name}.png")
		Sent_message = await Webhook.send(
				Message, username=Author_name, avatar_url=Avatar, files=Files_for_Discord,
				# Doesn’t affect images explicitly uploaded
				suppress_embeds=True,
				# Otherwise Discord doesn’t return the created message
				wait=True
		)
	else:
		Message = f"<**{Author_name}**> {Message}"
		Chan = bot.get_channel(Config["discord"]["chan"])
		if not Chan:
			Chan = await bot.fetch_channel(Config["discord"]["chan"])
		Sent_message = await Chan.send(Message, files=Files_for_Discord, suppress_embeds=True)

	if Sent_message and len(Sent_message.attachments) > 0:
		for Index, Attachment in enumerate(Sent_message.attachments):
			# Files_for_Discord was built in the same order since Discord preserves attachment order
			Discord_filename = Attachment.filename
			# In this case, Destination_filename points to the original filename in other_sources
			Original_filename = Files_to_download[Index]["Destination_filename"]
			Register_original_in_MPD(Discord_filename, Original_filename)

@bot.event
async def on_message_edit(Old_message, New_message):
	# Check if the text or the attachments have changed
	Text_changed = (Old_message.content or "") != (New_message.content or "")
	Old_files = [File.filename for File in Old_message.attachments]
	New_files = [File.filename for File in New_message.attachments]
	# Compare the filenames, not the attachments objects
	Attachments_changed = set(Old_files) != set(New_files)
	# Don’t record Discord automatic edits (resolving links, webhook normalization, etc)
	if not Text_changed and not Attachments_changed:
		return
	History.Message_edited(History_table, History_keep_all, New_message)

@bot.event
async def on_raw_message_delete(Payload):
	History.Message_deleted(History_table, History_keep_all, Payload.message_id)

###############################################################################
# Other stuff
###############################################################################

#@bot.event
#async def on_member_remove(Leaver: discord.Member):
#	"""When an user leaves a server"""
#	if Config["discord"].get("log_chan"):
#		Chan = await Get_chan(bot.get_guild(Config["discord"]["server"]), Config["discord"]["log_chan"])
#		if Chan:
#			await Chan.send(f"{Leaver.name} has left the server.")
