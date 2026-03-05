# -*- coding: utf-8 -*-

import pydle
import re
import textwrap

from Config_manager import Config
import Discord_manager

###############################################################################
# Handling messages
###############################################################################

def Translate_IRC_colors_to_Discord(Message):
	mIRC_colors = {
		"00": "black",
		"01": "navy",
		"02": "green",
		"03": "red",
		"04": "brown",
		"05": "purple",
		"06": "olive",
		"07": "yellow",
		"08": "lime",
		"09": "teal",
		"10": "aqua",
		"11": "blue",
		"12": "fuchsia",
		"13": "gray",
		"14": "silver",
		"15": "white",
	}
	mIRC_color_pattern = r"\x03(\d{1,2})(?:,(\d{1,2}))?"
	def Replace_colors(Match):
		FG_color = Match.group(1)
		BG_color = Match.group(2)
		FG_name = mIRC_colors.get(FG_color.zfill(2), "default")
		BG_name = mIRC_colors.get(BG_color.zfill(2), "default")
		return f"[{FG_name} on {BG_name}]"
	# Replace mIRC codes with Discord-compatible formatting
	return re.sub(mIRC_color_pattern, Replace_colors, Message)

def Translate_IRC_formatting_to_Discord(Message):
	# Map IRC control codes to Discord MarkDown
	Message = Message.strip()
	Replacements = [
		(r"\x02(.*?)\x02", r"**\1**"),  # Bold
		(r"\x1D(.*?)\x1D", r"*\1*"),	# Italic
		(r"\x1F(.*?)\x1F", r"__\1__"),  # Underline
		(r"\x0F", "")]					# Reset formatting (remove it)
	for Pattern, Replacement in Replacements:
		Message = re.sub(Pattern, Replacement, Message)
	return Message

def Split_into_IRC_messages(Message):
	# Maximum allowed message length (512 bytes - overhead for metadata)
	IRC_message_length = 400
	Lines = []
	# Messages on Discord can contain several lines. When that’s the case, start by splitting the
	# Discord message along the breaking lines, before possibly splitting each line again if it
	# exceeds the limit of an IRC message
	for Line in Message.splitlines():
		# Use textwrap to split the current line, without breaking words
		Line = Discord_manager.Translate_Discord_formatting_to_IRC(Line)
		Lines.extend(textwrap.wrap(Line, IRC_message_length))
	return Lines

###############################################################################
# pydle class
###############################################################################

class Connection_handler(pydle.Client):

	Instance = None
	Current_delay = 5
	Max_reconnect_delay = 300
	Shutting_down = False

	async def on_connect(self):
		await super().on_connect()
		self.Current_delay = 5
		for Bridge in Config["irc_bridges"]:
			await self.join(Config["irc_bridges"][Bridge]["irc_chan"])
		print("[IRC] Connected to server and chans")
		if Config["irc_info"].get("password"):
			await self.message("NickServ",
					f"identify {Config['irc']['nick']} {Config['irc']['password']}")
			print("[IRC] Identified with nickserv")

	async def Shutdown(self):
		self.Shutting_down = True
		print("[IRC] Shutting down…")
		await self.quit(Config["irc_info"].get("quit_message", "Something clever"))

	async def on_disconnect(self, expected):
		await super().on_disconnect(expected)
		if self.Shutting_down:
			return
		Next_delay = self.Current_delay
		print(f"[IRC] Disconnected. Reconnecting in {Next_delay}s")
		await self.eventloop.sleep(Next_delay)
		try:
			await self.connect(
				Config["irc_info"]["server"],
				tls=True, tls_verify=False
			)
		except Exception as Error:
			print(f"[IRC] Reconnect failed: {Error}")
		if Next_delay < self.Max_reconnect_delay:
			# Add random jitter to the delay to avoid synchronized retries (many clients hitting the
			# server at the same moment)
			self.Current_delay = random(Next_delay, Next_delay*2)
		else:
			self.Current_delay = self.Max_reconnect_delay

	async def on_nicknameinuse(self, nickname):
		await super().on_nicknameinuse(nickname)
		await self.set_nickname(self.nickname + "_")

	async def on_message(self, Chan, Author, Message):
		await super().on_message(Chan, Author, Message)
		# The bot ignores its own messages
		if Author == self.nickname:
			return
		if Message.startswith("!quit") and Author == Config["irc_info"]["bot_owner"]:
			await Discord_manager.Stop_bot(self)
			return
		print(f"[I] <{Author}> {Message}")
		await Discord_manager.Relay_IRC_message(Chan, Author, Message)

	async def Send_message(self, Chan, Author, Message):
		await self.message(Chan, f"<\x02{Author}\x02> {Message}")
