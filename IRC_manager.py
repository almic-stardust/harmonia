# -*- coding: utf-8 -*-

import pydle
import asyncio
import time
import re
import random
import uuid

from Config_manager import Config
import Gears
import Discord_manager

IRC_shutting_down = asyncio.Event()
Expected_chans = set()
for Bridge in Config["irc_bridges"]:
	IRC_chan = Config["irc_bridges"][Bridge]["irc_chan"]
	Expected_chans.add(IRC_chan)
Instance = None

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

def Split_into_IRC_messages(Message):
	# IRC has a variable message length: 512 - (control bytes + len(nick+user+host+channel))
	# Control bytes = 14 | Safety buffer in case of unexpected syntax added by a server = 10
	# Worst case scenario for the variable parts: nick = 20 | user = 20 | host = 63 | channel = 32
	# Source https://ircv3.net/specs/extensions/multiline
	# Maximum allowed message length: 512 - (14+10+20+20+63+32) = 353
	IRC_message_limit = 353
	Lines = []
	Message = Translate_Discord_formatting_to_IRC(Message)
	# Messages on Discord can contain several lines. When that’s the case, start by splitting the
	# Discord message along the breaking lines, before possibly splitting each line again if it
	# exceeds the limit
	for Line in Message.splitlines():
		Current_fragment = ""
		# Split the line into words using spaces as separators, then add the words one by one until
		# the limit is reached.
		# IRC limits messages by bytes, so the length must be measured after UTF-8 encoding. The
		# same strings will be encoded many times, but encoding such strings is very fast, and this
		# function runs only when messages are sent. Let’s leave micro-optimizations for later
		for Word in Line.split(" "):
			# The candidate string resulting from adding the next word to the current fragment
			if not Current_fragment:
				Candidate = Word
			else:
				Candidate = Current_fragment + " " + Word
			# The candidate string fits within the limit, so add the word to the current fragment
			if len(Candidate.encode("utf-8")) <= IRC_message_limit:
				Current_fragment = Candidate
			# Either the current fragment has reached the limit, or maybe even the current word
			# exceeds the limit by itself
			else:
				# First, if the current fragment isn’t empty, flush it
				if Current_fragment:
					Lines.append(Current_fragment)
					Current_fragment = ""
				# If the word itself exceeds the limit, split it
				if len(Word.encode("utf-8")) > IRC_message_limit:
					Remaining = Word
					while Remaining:
						Word_fragment = Remaining
						# Shrink the fragment until its UTF-8 byte length fits within the limit
						while len(Word_fragment.encode("utf-8")) > IRC_message_limit:
							Word_fragment = Word_fragment[:-1]
						Lines.append(Word_fragment)
						# Remove the fragment from the remaining text
						Remaining = Remaining[len(Word_fragment):]
				# Start a new fragment, beginning with the word that did not fit
				else:
					Current_fragment = Word
		# Add the last fragment, containing the remainder of the message
		if Current_fragment:
			Lines.append(Current_fragment)
	return Lines

###############################################################################
# pydle-related stuff
###############################################################################

async def Run_IRC_loop():

	global Instance
	Reconnect_delay = 5
	Max_reconnect_delay = 300

	while not IRC_shutting_down.is_set():

		New_instance = Connection_handler(
			nickname=Config["irc_info"]["nick"],
			username=Config["irc_info"]["username"],
			realname=Config["irc_info"]["real_name"]
		)
		try:
			await New_instance.connect(
				hostname=Config["irc_info"]["server"],
				tls=True, tls_verify=False
			)
			# Assign the global variable only after the connection has succeeded, to avoid the
			# possibility of an incorrect state, where calls to Get_instance() will find that
			# Instance isn’t None but .connected() returns False
			Instance = New_instance
			# Reset delay after successful connection
			Reconnect_delay = 5
			print(f"[IRC] Connected with instance {New_instance.Instance_ID}")
			# Wait until disconnection or shutdown
			await Gears.Wait_for_events(
					New_instance.Disconnection.wait(),
					IRC_shutting_down.wait()
			)
			# If shutdown was requested, exit loop
			if IRC_shutting_down.is_set():
				break
		except Exception as Error:
			# If shutdown was requested, don’t treat as a real error
			if IRC_shutting_down.is_set():
				print("[IRC] Connection aborted due to shutdown")
				break
			print(f"[IRC] Connection error: {Error}")
		# If New_instance dies, ensure the global instance is cleared
		finally:
			if Instance is New_instance:
				Instance = None

		# Handle reconnection (only if not shutting down)
		if not IRC_shutting_down.is_set():
			print(f"[IRC] Disconnected. Reconnecting in {Reconnect_delay:.1f}s…")
			await asyncio.sleep(Reconnect_delay)
			# Exponential backoff with jitter, to prevent synchronized reconnection attempts. If
			# there’s a problem on the IRC network and clients are disconnected, the network servers
			# don’t need many clients trying to reconnect simultaneously.
			if Reconnect_delay < Max_reconnect_delay:
				Reconnect_delay = random.uniform(Reconnect_delay, Reconnect_delay * 2)
			# Once the maximum delay is reached, continue to set a random delay, but within a
			# limited window
			else:
				Reconnect_delay = random.uniform(Max_reconnect_delay, Max_reconnect_delay + 30)

	print("[IRC] Run_IRC_loop() exited cleanly.")

def Get_instance():
	global Instance
	if Instance is None:
		print("[IRC] Error: No IRC instance")
		return
	return Instance

# Get Connected Instance
def GCI():
	Current_instance = Get_instance()
	if not Current_instance:
		 return
	if not Current_instance.connected:
		 print("[IRC] Error: IRC not connected")
		 return
	return Current_instance

###############################################################################
# pydle class
###############################################################################

class Connection_handler(pydle.Client):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.Instance_ID = uuid.uuid4()
		self.Disconnection = asyncio.Event()
		self.Send_lock = asyncio.Lock()
		self.Last_send = 0

	async def on_connect(self):
		await super().on_connect()
		for Bridge in Config["irc_bridges"]:
			await self.join(Config["irc_bridges"][Bridge]["irc_chan"])
		if Config["irc_info"].get("password"):
			await self.Safe_message("NickServ",
					f"identify {Config['irc_info']['nick']} {Config['irc_info']['password']}"
			)
			print("[IRC] Identified with nickserv")
		asyncio.create_task(self.Ensure_chans())

	async def on_disconnect(self, Expected):
		await super().on_disconnect(Expected)
		self.Disconnection.set()
		if IRC_shutting_down.is_set():
			return
		print(f"[IRC] Instance {self.Instance_ID} disconnected.")

	async def Shutdown_IRC(self):
		print("[IRC] Disconnecting…")
		IRC_shutting_down.set()
		await self.quit(Config["irc_info"].get("quit_message", "Something clever"))

	async def Ensure_chans(self):
		global Expected_chans
		while not IRC_shutting_down.is_set():
			# Check every day
			await asyncio.sleep(86400)
			for IRC_chan in Expected_chans:
				if IRC_chan not in self.channels:
					print(f"[IRC] Recovering: rejoining {IRC_chan}")
					await self.join(IRC_chan)

	# Wrap the raw handler to avoid crashes, but continue to log errors
	async def on_raw(self, Message):
		try:
			await super().on_raw(Message)
		except KeyError as Error:
			print(f"[IRC] on_raw exception: {Error}")

	async def on_nicknameinuse(self, Nick):
		await super().on_nicknameinuse(Nick)
		await self.set_nickname(self.nickname + "_")

	def _destroy_user(self, Nick, Chan=None):
		try:
			super()._destroy_user(Nick, Chan)
		except KeyError:
			print(f"[WARN] Tried to destroy unknown user {Nick} in {Chan}")
		except Exception as Error:
			print(f"[ERROR] Unexpected error in _destroy_user: {Error}")
			raise

	async def on_message(self, Chan, Author, Message):
		await super().on_message(Chan, Author, Message)
		# The bot ignores its own messages
		if Author == self.nickname:
			return
		if Message.startswith("!quit") and Author == Config["irc_info"]["bot_owner"]:
			import Harmonia
			await Harmonia.Stop_bot()
			return
		print(f"[I] <{Author}> {Message}")
		await Discord_manager.Relay_IRC_message(Chan, Author, Message)

	async def Safe_message(self, Chan, Message):
		if not self.connected:
			print(f"[IRC] Error: attempt to send on disconnected instance {self.instance_id}")
			return
		async with self.Send_lock:
			for Line in Message.splitlines():
				# No need to send a blank line
				if Line.strip():
					Elapsed = time.monotonic() - self.Last_send
					# Libera allows one message to be sent every two seconds
					# https://libera.chat/guides/faq#flood-exemptions-for-bots
					if Elapsed < 2:
						await asyncio.sleep(2 - Elapsed)
					await self.message(Chan, Line)
					self.Last_send = time.monotonic()

	async def Relay_Discord_message(self, Chan, Author, Message):
		await self.Safe_message(Chan, f"<\x02{Author}\x02> {Message}")
