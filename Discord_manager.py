# -*- coding: utf-8 -*-
# “Discord” is susceptible to be a keyword used elsewhere → this file is named Discord_manager.py

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
import Gears
import History

intents = discord.Intents.default()
# Allows to receive member join/leave events
intents.members = True
# Allows to listen to messages events and provides metadata
intents.messages = True
# Allows to read the content of messages
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

IRC_enabled = Config["Enabled_sections"]["IRC"]
if IRC_enabled:
	import IRC_manager
History_enabled = Config["Enabled_sections"]["History"]
if History_enabled:
	History_table = Config["History"]["DB_table"]
Users_enabled = Config["Enabled_sections"]["Users"]
if Users_enabled:
	Users_table = Config["Users"]["DB_table"]
HTTP_session = None
Users_buffers = {}
Map_pending_downloads = {}

###############################################################################
# General
###############################################################################

async def Init_webhooks():
	global HTTP_session
	HTTP_session = aiohttp.ClientSession()

# Event triggered when the bot has connected to Discord
@bot.event
async def on_ready():
	await Gears.Start_bot()

# Exceptions in the event handlers of discord.py are swallowed, unless explicitly logged.
# As Discord bots are long-running services, it wouldn’t be acceptable for one exception in one
# event to crash or disconnect the bot, or require it to be restarted. That’s why discord.py
# prioritizes fault isolation over strict failure.
# But for development, it’s not convenient. So when not in prod, we enable exceptions in events.
@bot.event
async def on_error(event, *args, **kwargs):
	import traceback
	traceback.print_exc()

@bot.event
async def on_command(Context):
	print(f"Running command: {Context.command}")

# Global command error handler, so that errors are visible instead of being silently ignored
@bot.event
async def on_command_error(Context, Error):
	await Context.send(f"Command error: {Error}")
	if not IRC_enabled:
		return
	Bridge = Get_bridge_by_Discord_chan(Context.channel.id)
	if not Bridge:
		return
	IRC_chan = Bridge["IRC_chan"]
	if not IRC_chan:
		return
	Author = Context.author.display_name
	# Relay on IRC the command that caused the error
	IRC_instance = IRC_manager.GCI()
	if IRC_instance:
		await IRC_instance.Relay_Discord_message(IRC_chan, Author, Context.message.content)
		await IRC_instance.Safe_message(IRC_chan, f"Command error: {Error}")

async def Shutdown_Discord():
	global HTTP_session
	print("[Discord] Disconnecting…")
	if HTTP_session:
		await HTTP_session.close()
		if HTTP_session.closed:
			print("[Discord] HTTP session closed.")
		# Prevent reuse after closing
		HTTP_session = None
	await bot.close()

###############################################################################
# Handling chans
###############################################################################

def Get_bridge_by_Discord_chan(Discord_chan_ID):
	IRC_bridges = Config.get("IRC_bridges")
	if IRC_bridges:
		for Bridge in IRC_bridges:
			if IRC_bridges[Bridge]["Discord_chan"] == Discord_chan_ID:
				return IRC_bridges[Bridge]
	return None

def Get_bridge_by_IRC_chan(IRC_chan):
	# If IRC_chan doesn’t exist in Config["IRC_bridges"] → returns None
	return Config["IRC_bridges"].get(IRC_chan.lstrip("#"))

###############################################################################
# Handling users
###############################################################################

def Discord_expiration_for_IRC_user(IRC_pseudo, Users):
	# For unregistered users, default period is one year
	Expiration_period = 365
	for User_ID in Users:
		Infos_user = Users[User_ID]
		if Infos_user["IRC_pseudo"] == IRC_pseudo:
			Expiration_period = Infos_user["Discord_expiration_for_IRC"]
			break
	return Expiration_period

###############################################################################
# Handling messages
###############################################################################

# Automatically delete messages relayed from IRC to Discord by the bot. Depending on the user’s
# request : either after one month, one year (default), or not at all
@tasks.loop(hours=24)
async def Delete_expired_IRC_messages_from_Discord():
	Users = DB_manager.Users_fetch_users(Users_table)
	try:
		Rows = DB_manager.Messages_potentially_expired(History_table)
		for Row in Rows:
			Expiration_period = Discord_expiration_for_IRC_user(Row["user"], Users)
			# An expiration period of 0 means no expiration
			if Expiration_period == 0:
				continue
			Now = datetime.datetime.now(datetime.timezone.utc)
			Date_creation = Row["creation_date"].replace(tzinfo=datetime.timezone.utc)
			Message_duration = Now - Date_creation
			if Message_duration > datetime.timedelta(days=Expiration_period):
				Chan = bot.get_channel(Row["chan_id"])
				if not Chan:
					Chan = await bot.fetch_channel(Row["chan_id"])
				Message_ID = Row["message_id"]
				try:
					Message = await Chan.fetch_message(Message_ID)
				# If the DB is restored from a backup, it then contains messages that had already
				# been deleted from Discord
				except discord.NotFound:
					print(f"[Discord_m] Expired messages: Message {Message_ID} was already deleted.")
					DB_manager.Mark_message_expired(History_table, Message_ID)
					continue
				# Chans can be deleted or become inaccessible
				except discord.Forbidden:
					print(f"[Discord_m] Expired messages: Message {Message_ID} has become inaccessible.")
					DB_manager.Mark_message_expired(History_table, Message_ID)
					continue
				await Message.delete()
				DB_manager.Mark_message_expired(History_table, Message_ID)
				print(f"[Discord_m] Deleted expired message {Message_ID}.")
	except Exception as Error:
		print(f"[Discord_m] Error for expired messages: {Error}")

# Handling files whose names have been changed by Discord: check once a day if there are files in
# the folder other_sources, and if so, overwrite the Discord version with the original file.
#	The files whose names aren’t modified by Discord will be managed in History.py, but others will
#	remain in the folder other_sources. Original filenames can’t be known from History.py, it’s
#	called by on_message() via History.Message_added(). And handling files with modified names here
#	in Discord_manager.py, either inside on_message() or at the end of Relay_IRC_message(), that
#	comes across a race condition.
@tasks.loop(hours=24)
async def Reconcile_downloaded_files():
	try:
		global Map_pending_downloads
		Storage_folder = Config["History"].get("Storage_folder")
		Other_sources = os.path.join(Storage_folder, "other_sources")
		if not os.path.exists(Storage_folder):
			print(f"[Discord_m] Warning: The folder for the attachments isn’t accessible.")
			return
		if not os.path.exists(Other_sources):
			print(f"[Discord_m] Creating the folder for other sources attachments.")
			os.makedirs(Other_sources)
		# list() prevents runtime modification errors
		for Discord_filename, Filenames_map in list(Map_pending_downloads.items()):
			if not Filenames_map or "Original_filename" not in Filenames_map \
					or "Destination_filename" not in Filenames_map:
				continue
			Original_path = os.path.join(Other_sources, Filenames_map["Original_filename"])
			Destination_path = os.path.join(Storage_folder, Filenames_map["Destination_filename"])
			# Address the rare cases where the task runs precisely when a file with a name modified
			# by Discord is being processed in History.py. If the file has already been downloaded
			# in other_sources, but hasn’t yet passed through Discord, then the task could move the
			# original from other_sources to Storage_folder, just before the version from Discord
			# arrives in Storage_folder.
			# If this confluence of circumstances occurs, don’t deal with this file this time. It’ll
			# be processed during the next execution of the task.
			if not os.path.exists(Destination_path):
				continue
			if os.path.exists(Original_path):
				# Replace the file downloaded from Discord with the original one
				os.replace(Original_path, Destination_path)
			# If the file was in other_sources: once processed, its key is no longer needed.
			# If the file wasn’t there: that means its name wasn’t changed by Discord, and it had
			# already been moved in Storage_folder by History.py. So we can also delete its key.
			del Map_pending_downloads[Discord_filename]
	except Exception as Error:
		print(f"[Discord_m] Reconcile_downloaded_files(): {Error}")

def Split_message(Message):
	# Discord limits message size → split the message into fragments of 2000 characters or less
	Limit = 2000
	Remainder = Message
	Fragments = []
	while len(Remainder) > Limit:
		# Prefer splitting at a newline to preserve formatting
		Where_to_split = Remainder.rfind("\n", 0, Limit)
		# Otherwise → split at the last word boundary
		if Where_to_split == -1:
			Where_to_split = Remainder.rfind(" ", 0, Limit)
		# If no suitable boundary exists → hard split
		if Where_to_split == -1:
			Where_to_split = Limit
		Fragments.append(Remainder[:Where_to_split])
		# Remove leading whitespace created by the split
		Remainder = Remainder[Where_to_split:].lstrip()
	# Add the final fragment (always ≤ Limit, since Message = X fragments of 2000c + a final one)
	if Remainder:
		Fragments.append(Remainder)
	return Fragments

async def Rate_limiter_for_IRC(Buffer_key, Bridge, Author, Author_name):

	await asyncio.sleep(5)
	Buffer = Users_buffers.get(Buffer_key)
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
		IRC_instance = IRC_manager.GCI()
		for Message in Messages_to_relay:
			if IRC_instance:
				await IRC_instance.Relay_Discord_message(Bridge["IRC_chan"], Author_name, Message)
	else:
		# get_channel gets the channel object from the bot’s cache. fetch_channel gets it from
		# Discord, meaning a network request
		Chan = bot.get_channel(Bridge["Discord_chan"])
		if not Chan:
			Chan = await bot.fetch_channel(Bridge["Discord_chan"])
		await Chan.send(
				f"{Author.mention} What you typed resulted in too many messages to relay on IRC in a short time. Therefore nothing was forwarded."
		)

	# Cleanup buffer once decision is made
	Users_buffers.pop(Buffer_key, None)

@bot.event
async def on_message(Message):

	Author = Message.author
	Text = Message.content
	Discord_chan = Message.channel.id
	Bridge = None
	if IRC_enabled:
		Bridge = Get_bridge_by_Discord_chan(Discord_chan)

	# Author.display_name = the server nickname if set, otherwise the global display name if set,
	# otherwise the Discord username
	Author_name = Author.display_name
	# If a user has requested that the bot assign them a specific name on Discord, then this name
	# will be used on Discord, but use the IRC nick for the history and messages transferred to IRC
	if Users_enabled:
		Users = DB_manager.Users_fetch_users(Users_table)
		for User_ID in Users:
			Infos_user = Users[User_ID]
			if Infos_user["Pseudo_displayed_on_Discord"] == Author_name:
				Author_name = Infos_user.get("IRC_pseudo", Author_name)
				break

	Relayed_message = False
	# If the message comes from IRC to Discord, through a webhook
	if Message.webhook_id is not None:
		Relayed_message = True
	if Author == bot.user:
		# If the message comes from IRC to Discord, without a webhook
		if Bridge and Text.startswith("<**"):
			Match = re.match(r"<\*\*(.*?)\*\*>\s*(.*)", Text)
			if Match:
				Relayed_message = True
				Author_name = Match.group(1)
				Text = Match.group(2)
		# It’s the bot, responding to someone or saying something by itself
		else:
			Author_name = Config["Discord"].get("Bot_name", "Bot")

	if History_enabled:
		await History.Message_added(History_table,
				Author_name, Discord_chan, Message, Text, Relayed_message
		)

	# Commands must begin with a letter, don’t react to “!!!” or “!?”
	if re.match(r"^![A-Za-z]+", Text):
		# IRC commands
		if Relayed_message:
			from Commands_manager import IRC_dispatcher
			await IRC_dispatcher(Bridge, Author_name, Text)
		# Discord commands
		else:
			await bot.process_commands(Message)
		return

	# After this point, the bot ignores its own messages
	if Author == bot.user:
		return

	# Don’t relay on IRC what’s already coming from IRC
	if Relayed_message:
		return

	# The message comes from a Discord chan that doesn’t have a bridge to an IRC chan
	if not Bridge:
		return

	# Prepare the message, and relay it from Discord to IRC
	Text = Message.clean_content.strip()
	# If the Discord message has attachments, add their URLs at the end
	if Message.attachments:
		# If there’s no message, no need to put a | before the URLs
		if Text:
			Text += " | "
		# Ensure base ends with exactly one "/"
		URL_base = Config["History"].get("Storage_url").rstrip("/") + "/"
		Urls = []
		for Attachment in Message.attachments:
			Filenames_map = Map_pending_downloads.get(Attachment.filename)
			# If the history isn’t enabled, the files won't be in Map_pending_downloads anyway
			if Filenames_map:
				# URL-encode safely
				URL = URL_base + quote(Filenames_map["Destination_filename"])
			else:
				URL = Attachment.url
			Urls.append(URL)
		Text += " | ".join(Urls)
	print(f"[D] <{Author_name}> {Text}")
	# To prevent (or rather limit) flood towards IRC
	Now = time.monotonic()
	Buffer_key = (Author.id, Discord_chan)
	Buffer = Users_buffers.setdefault(Buffer_key, {"messages": [], "task": None})
	Buffer["messages"].append((Now, Text))
	# Start the rate limiter only once
	if Buffer["task"] is None:
		# Attach the task to discord.py’s managed loop
		Buffer["task"] = bot.loop.create_task(
				Rate_limiter_for_IRC(Buffer_key, Bridge, Author, Author_name)
		)

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

async def Get_avatar_filename(Author_name, Discord_ID=None):
	Avatars_folder = os.path.join(Config["History"].get("Storage_folder"), "avatars")
	if not os.path.exists(Avatars_folder):
		os.makedirs(Avatars_folder)
	Filename = f"{Author_name}.png"
	Avatar_path = os.path.join(Avatars_folder, Filename)
	if os.path.exists(Avatar_path):
		return Filename
	# Generate RoboHash URL: can use username, ID, or any stable seed
	# Styles are available: robohash.org/<Seed>.png?set=setX (1 = robots, default. 2 = monsters)
	Avatar_URL = f"https://robohash.org/{Author_name}.png?size=150x150"
	async with aiohttp.ClientSession() as Session:
		async with Session.get(Avatar_URL) as Response:
			if Response.status == 200:
				with open(Avatar_path, "wb") as f:
					f.write(await Response.read())
	return Filename

async def Relay_IRC_message(IRC_chan, IRC_nick, Message):

	if Gears.Shutting_down.is_set():
		return
	Bridge = Get_bridge_by_IRC_chan(IRC_chan)
	if not Bridge:
		return

	Files_for_Discord = []
	Pattern_image_URL = r"(https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?)"
	Images_URLs = re.findall(Pattern_image_URL, Message)
	if Images_URLs:
		Storage_folder = os.path.join(Config["History"].get("Storage_folder"), "other_sources")
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
		# If history isn’t enabled, relay the links as-is on Discord
		if len(Files_to_download) > 0 and History_enabled:
			# Download the files so that they’ll be already present in the other_sources folder, to
			# avoid keeping a version potentially degraded by Discord
			Downloaded_filenames = await History.Download_files(
					History_table, Storage_folder, Date, Files_to_download, Max_size
			)
			for Filename in Downloaded_filenames:
				File_path = os.path.join(Storage_folder, Filename)
				Files_for_Discord.append(discord.File(File_path))
			# Remove images URLs from message body
			Message = re.sub(Pattern_image_URL, "", Message).strip()

	Message = IRC_manager.Translate_IRC_formatting_to_Discord(Message)

	Webhook_URL = Bridge.get("Webhook")
	if Webhook_URL:
		Webhook = discord.Webhook.from_url(Webhook_URL, session=HTTP_session)
		Author_name = IRC_nick
		Avatar_URL = None
		if Users_enabled:
			Users = DB_manager.Users_fetch_users(Users_table)
			User = None
			for Infos_user in Users.values():
				if Infos_user["IRC_pseudo"] == IRC_nick:
					User = Infos_user
					break
			if User:
				if User["Pseudo_displayed_on_Discord"]:
					Author_name = User["Pseudo_displayed_on_Discord"]
				Avatar_URL = User.get("Avatar_URL")
				if not Avatar_URL:
					Server = bot.get_guild(Config["Discord"]["Server"])
					Discord_user = None
					if User["Discord_username"]:
						Discord_user = discord.utils.get(
								Server.members, name=User["Discord_username"]
						)
					if Discord_user:
						Avatar_URL = Discord_user.display_avatar.url
		# There might be an avatar stored on the server, but only if the history was enabled
		if not Avatar_URL and History_enabled:
			Avatar_filename = await Get_avatar_filename(IRC_nick)
			# Ensure base ends with exactly one "/"
			URL_base = Config["History"].get("Storage_url").rstrip("/") + "/"
			Avatar_URL = URL_base + "avatars/" + quote(Avatar_filename)
		try:
			Sent_message = await Webhook.send(
					Message, username=Author_name, avatar_url=Avatar_URL, files=Files_for_Discord,
					# Doesn’t affect images explicitly uploaded
					suppress_embeds=True,
					# Without that, Discord doesn’t return the created message
					wait=True
			)
		except aiohttp.client_exceptions.ServerDisconnectedError:
			print("[Discord] Error while relaying message: disconnected from server.")
			return
	else:
		Chan = bot.get_channel(Bridge["Discord_chan"])
		if not Chan:
			Chan = await bot.fetch_channel(Bridge["Discord_chan"])
		Message = f"<**{IRC_nick}**> {Message}"
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
	if History_enabled:
		# Check if the text or the attachments have changed
		Text_changed = (Old_message.content or "") != (New_message.content or "")
		Old_files = [File.filename for File in Old_message.attachments]
		New_files = [File.filename for File in New_message.attachments]
		# Compare the filenames, not the attachments objects
		Attachments_changed = set(Old_files) != set(New_files)
		# Don’t record Discord automatic edits (resolving links, webhook normalization, etc)
		if not Text_changed and not Attachments_changed:
			return
		History.Message_edited(History_table, New_message)

@bot.event
async def on_raw_message_delete(Payload):
	if History_enabled:
		History.Message_deleted(History_table, Payload.message_id)
