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
		await self.join(Config["IRC"]["chan"])
		print("[IRC] Connected to server and channel")

	async def on_nicknameinuse(self, nickname):
		await super().on_nicknameinuse(nickname)
		await self.set_nickname(self.nickname + "_")

	async def on_message(self, target, Author, Message):
		await super().on_message(target, Author, Message)
		# The bot ignores its own messages
		if Author == self.nickname:
			return
		print(f"[I] <{Author}> {Message}")
		await Discord_manager.Send_message(Author, Message)

	async def Send_message(self, Author, Message):
		# Maximum allowed message length (512 bytes - overhead for metadata)
		Max_length = 400
		# Messages on Discord can contain several lines. When it’s the case, split the message into
		# lines, and send each line individually on IRC
		Lines = Message.splitlines()
		for Line in Lines:
			# Use textwrap to split the current line into parts, without breaking words
			Parts = textwrap.wrap(Line, width=Max_length)
			for Part in Parts:
				await self.message(Config["IRC"]["chan"], f"<\x02{Author}\x02> {Part}")
