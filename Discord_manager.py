# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import time
import asyncio
import aiohttp
import os
import re

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

Users_buffers = {}
History_table = Config["history"]["db_table"]
# TODO I’ll deal with that later
History_keep_all = True
HTTP_session = None

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

	await History.Message_added(History_table, Author_name, Chan, Message)

	# The bot ignores its own messages (including what it posted via a webhook)
	if Author == bot.user or Message.webhook_id is not None:
		return

	# Exempt commands from buffering
	if Is_command(Message):
		# Forward the message to the bot’s command handler
		await bot.process_commands(Message)
		return

	Content = Message.clean_content.strip()
	# If the Discord message has attachments, add their URLs at the end of the message send on IRC
	if Message.attachments:
		# If there’s no message, no need to put a | before the URLs
		if Content:
			Content += " | "
		Content += " | ".join(Attachment.url for Attachment in Message.attachments)
	print(f"[D] <{Author_name}> {Content}")

	# To prevent (or rather limit) flood towards IRC
	Now = time.monotonic()
	Buffer = Users_buffers.setdefault(Author.id, {"messages": [], "task": None})
	Buffer["messages"].append((Now, Content))
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

async def Relay_IRC_message(IRC_chan, Author_name, Message):

	Storage_dir = Config["history"].get("storage_folder") + "/other_sources"
	Files_for_Discord = []

	Pattern_any_URL = r"(https?://\S+)"
	Pattern_image_URL = r"(https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?)"
	Images_URLs = re.findall(Pattern_image_URL, Message)
	if Images_URLs:
		Attachments = await Attachments_manager.Download_from_IRC(History_table, Images_URLs)
		if Attachments:
			for File in Attachments:
				File_path = os.path.join(Storage_dir, File)
				Files_for_Discord.append(discord.File(File_path))
			# Remove images URLs from message body
			Message = re.sub(Pattern_image_URL, "", Message).strip()
	# Replace any remaining URLs with HTML links
	else:
		Message = re.sub(Pattern_any_URL, r'<a href="\1">\1</a>', Message)
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
		await Webhook.send(Message,
				username=Author_name,
				avatar_url=Avatar,
				files=Files_for_Discord
		)
	else:
		Message = f"<**{Author_name}**> {Message}"
		Chan = bot.get_channel(Config["discord"]["chan"])
		if not Chan:
			Chan = await bot.fetch_channel(Config["discord"]["chan"])
		await Chan.send(Message, files=Files_for_Discord)

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
