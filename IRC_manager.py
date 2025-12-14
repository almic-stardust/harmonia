import pydle
import re
import textwrap

from Config_manager import Config
import Discord_manager

###############################################################################
# pydle class
###############################################################################

class Connection(pydle.Client):

	Instance = None

	async def on_connect(self):
		await super().on_connect()
		await self.join(Config["irc"]["chan"])
		print("[IRC] Connected to server and channel")
		if Config["irc"].get("password"):
			await self.message("NickServ",
					f"identify {Config['irc']['nick']} {Config['irc']['password']}")
			print("[IRC] Identified with nickserv")

	async def on_nicknameinuse(self, nickname):
		await super().on_nicknameinuse(nickname)
		await self.set_nickname(self.nickname + "_")

	async def on_message(self, Chan, Author, Message):
		await super().on_message(Chan, Author, Message)
		# The bot ignores its own messages
		if Author == self.nickname:
			return
		if Message.startswith('!quit') and Author == Config["irc"]["bot_owner"]:
			await Discord_manager.Stop_bot(self)
			return
		print(f"[I] <{Author}> {Message}")
		await Discord_manager.Relay_IRC_message(Chan, Author, Message)

	async def Relay_Discord_message(self, Author, Message):
		# Maximum allowed message length (512 bytes - overhead for metadata)
		Max_length = 400
		# Messages on Discord can contain several lines. When it’s the case, split the message into
		# lines, and send each line individually on IRC
		Lines = Message.splitlines()
		for Line in Lines:
			# Use textwrap to split the current line into parts, without breaking words
			Parts = textwrap.wrap(Line, width=Max_length)
			for Part in Parts:
				Part = Discord_manager.Translate_Discord_formatting_to_IRC(Part)
				await self.message(Config["irc"]["chan"], f"<\x02{Author}\x02> {Part}")

###############################################################################
# Other functions
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
