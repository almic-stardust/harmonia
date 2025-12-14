# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import aiohttp
import re

from Config_manager import Config
import IRC_manager
# TODO history
#import History

intents = discord.Intents.default()
# Allows to receive member join/leave events
intents.members = True
# Allows to listen to messages events and provides metadata
intents.messages = True
# Allows to read the content of messages
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

###############################################################################
# General
###############################################################################

HTTP_session = None
async def Init_webhooks():
	global HTTP_session
	HTTP_session = aiohttp.ClientSession()

async def Stop_bot(IRC_Instance):
	await bot.close()
	if HTTP_session:
		await HTTP_session.close()
	await IRC_Instance.quit(Config["irc"].get("quit_message", "That’s the end of the beans"))
	return

###############################################################################
# Handling messages
###############################################################################

@bot.event
async def on_message(Message):

	Author = Message.author
	# We set 0 if it’s a DM
	Server_id = Message.guild.id if Message.guild else 0
	Chan = Message.channel

	# TODO history
	#await History.Message_added(Server_id, Chan, Message)

	# The bot ignores its own messages (including what it posted via a webhook)
	if Author == bot.user or Message.webhook_id is not None:
		return

	# Initially we have only one bridged chan
	if Message.channel.id != Config["discord"]["chan"]:
		return

	if Message.content.strip() == "!quit" and Author.name == Config["discord"]["bot_owner"]:
		await Stop_bot(IRC_manager.Instance)
		return

	Content = Message.clean_content.strip()
	# If the Discord message has attachments, add their URLs at the end of the message send on IRC
	if Message.attachments:
		Content += " | "
		Content += " ".join(Attachment.url for Attachment in Message.attachments)
	print(f"[D] <{Author.name}> {Content}")

	await IRC_manager.Instance.Relay_Discord_message(Author.name, Content)

	# Forward the message back to the bot’s command handler, to allow messages containing commands
	# to be processed
	await bot.process_commands(Message)

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

async def Relay_IRC_message(IRC_chan, Author, Message):
	Message = IRC_manager.Translate_IRC_formatting_to_Discord(Message)
	Chan = Config["webhooks"].get(IRC_chan.lstrip("#"))
	if Chan:
		Webhook = discord.Webhook.from_url(Chan, session=HTTP_session)
		Username = Author
		Avatar = f"https://robohash.org/{Username}.png"
		User = Config["irc_users"].get(Author)
		if User:
			Username = User["discord_username"]
			# A user could request a specific username on Discord, but without requesting an avatar
			Avatar = User.get("avatar", f"https://robohash.org/{Username}.png")
		await Webhook.send(content=Message, username=Username, avatar_url=Avatar)
	else:
		Chan = bot.get_channel(Config["discord"]["chan"])
		Message = f"<**{Author}**> {Message}"
		await Chan.send(Message)

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

# TODO history
#@bot.event
#async def on_raw_message_edit(Payload):
#	Server_id = Payload.guild_id if bot.get_guild(Payload.guild_id) else 0
#	Chan = await bot.fetch_channel(Payload.channel_id)
#	Message = await Chan.fetch_message(Payload.message_id)
#	#History.Message_edited(Server_id, Payload.message_id, Message.content)
#
#@bot.event
#async def on_raw_message_delete(Payload):
#	Server_id = Payload.guild_id if bot.get_guild(Payload.guild_id) else 0
#	#History.Message_deleted(Server_id, Payload.message_id)

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
