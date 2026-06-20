# -*- coding: utf-8 -*-
# “DB” is susceptible to be a keyword used elsewhere → this file is named DB_manager.py

import sys
# This actually uses the package mysqlclient, a fork of MySQLdb adding Python 3 support
import MySQLdb
import json
import datetime

from Config_manager import Config

def Connect_DB():
	try:
		Connection = MySQLdb.connect(**Config["mysqlclient"])
		return Connection
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)

def History_update_filename(Table, Old_filename, New_filename):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if there is an entry whose attachments field contains the value of Old_filename
		Cursor.execute(f"""
				SELECT message_id, attachments FROM {Table}
				WHERE JSON_CONTAINS(attachments, %s)""",
				(json.dumps(Old_filename),)
		)
		Result = Cursor.fetchone()
		if not Result:
			print("[DB] Error: There’s already a file with that name in the folder, but it wasn’t registered in the DB for that message")
			return
		Message_ID = Result[0]
		Filenames = json.loads(Result[1])
		Updated_filenames = []
		for Filename in Filenames:
			if Filename == Old_filename:
				Updated_filenames.append(New_filename)
			else:
				Updated_filenames.append(Filename)
		# Convert the list into a string to store it into the DB
		Updated_filenames = json.dumps(Updated_filenames)
		Cursor.execute(f"""
				UPDATE {Table} SET attachments = %s
				WHERE message_id = %s""",
				(Updated_filenames, Message_ID)
		)
		# Autocommit could leave the DB in a partially updated state: a batch of related updates
		# could be only partially applied, because one of them raised an exception. Therefore, it’s
		# preferable to commit every time
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_addition(Table, Date, Server_ID, Chan_ID, Message_ID, Replied_message_ID, Discord_username, Text, Attachments, Relayed):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Retrieve the necessary informations from the DB
		Cursor.execute(f"""
				SELECT message_id FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if Result:
			print("[DB] Warning: this message was already stored in the DB.")
			return
		Centiseconds = round(Date.microsecond / 10000)
		Formatted_date = Date.isoformat(timespec="seconds") + f".{Centiseconds:02d}"
		Content_history = {Formatted_date: {
				"Text": Text
		}}
		Content_history = json.dumps(Content_history)
		if len(Attachments) > 0:
			Attachments = json.dumps(Attachments)
		# If the list is empty, save NULL in the attachments field
		else:
			Attachments = None
		Cursor.execute(f"""
				INSERT INTO {Table} (
					creation_date,
					server_id, chan_id, message_id,
					reply_to,
					user, content_history, attachments, relayed)
				VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
				(
					Date,
					Server_ID, Chan_ID, Message_ID,
					Replied_message_ID,
					Discord_username, Content_history, Attachments, Relayed
				)
		)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_edition(Table, Keep, Message_ID, Date, New_text, Updated_filenames, Deleted):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Retrieve the necessary informations from the DB
		Cursor.execute(f"""
				SELECT user, content_history FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print(f"[DB] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
			return
		Query = f"UPDATE {Table} SET content_history = %s"
		Content_history = json.loads(Result[1])
		if Keep:
			Centiseconds = round(Date.microsecond / 10000)
			Date = Date.isoformat(timespec="seconds") + f".{Centiseconds:02d}"
		else:
			# If Keep is False, there’ll only ever be one entry in the dictionary
			Date = next(iter(Content_history))
		Content_history[Date] = {
				"Text": New_text
		}
		if len(Deleted) > 0:
			Content_history[Date] = {
					"Deleted_attachments": Deleted
			}
		Values = [json.dumps(Content_history)]
		if Updated_filenames:
			Query += ", attachments = %s"
			Values.append(json.dumps(Updated_filenames))
		Query += f"WHERE message_id = {Message_ID}"
		Cursor.execute(Query, Values)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_deletion(Table, Keep, Message_ID, Date, Updated_filenames):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Retrieve the necessary informations from the DB
		Cursor.execute(f"""
				SELECT user FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print(f"[DB] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
			return
		if Keep:
			Query = f"UPDATE {Table} SET deletion_date = %s"
			Values = [Date]
			if Updated_filenames:
				Query += ", attachments = %s"
				Values.append(json.dumps(Updated_filenames))
			Query += f"WHERE message_id = {Message_ID}"
		else:
			Query = f"DELETE FROM {Table} WHERE message_id = {Message_ID}"
		Cursor.execute(Query, Values)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_fetch_message(Table, Message_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				SELECT
					creation_date,
					server_id,
					chan_id,
					message_id,
					reply_to,
					user,
					content_history,
					attachments,
					reactions,
					relayed,
					expired,
					deletion_date
				FROM {Table} WHERE message_id = %s""",
				(Message_ID,))
		Result = Cursor.fetchone()
		Infos_message = None
		if Result:
			if Result[6]:
				Content_history = Result[6]
				# Decode only if the returned object is a string: depending on the driver version,
				# MariaDB may return JSON columns as already-decoded Python objects
				if isinstance(Content_history, str):
					Content_history = json.loads(Content_history)
				Content_history = {
					datetime.datetime.fromisoformat(Date): Text
					for Date, Text in Content_history.items()
				}
			else:
				Content_history = {}
			if Result[7]:
				Attachments = Result[7]
				if isinstance(Attachments, str):
					Attachments = json.loads(Attachments)
			else:
				Attachments = []
			if Result[8]:
				Reactions = Result[8]
				if isinstance(Reactions, str):
					Reactions = json.loads(Reactions)
			else:
				Reactions = {}
			Infos_message = {
					"Creation_date":	Result[0],
					"Server_ID":		Result[1],
					"Chan_ID":			Result[2],
					"Message_ID":		Result[3],
					"Reply_to":			Result[4] if Result[4] else None,
					"User":				Result[5],
					"Content_history":	Content_history,
					"Attachments":		Attachments,
					"Reactions":		Reactions,
					"Relayed":			bool(Result[9]),
					"Expired":			bool(Result[10]),
					"Deletion_date":	Result[11] if Result[11] else None,
			}
		return Infos_message
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_messages_to_display(Table, Server_ID, Chan_ID, Before=None, Limit=50):
	Connection = Connect_DB()
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Query = f"""
			SELECT
				message_id,
				reply_to,
				user,
				content_history,
				attachments,
				reactions,
				creation_date,
				deletion_date
			FROM {Table}
			WHERE server_id = %s
			AND chan_id = %s
			AND deletion_date IS NULL"""
		Values = [Server_ID, Chan_ID]
		if Before is not None:
			Query += " AND creation_date < %s"
			Values.append(Before)
		Query += " ORDER BY creation_date DESC LIMIT %s"
		Values.append(Limit)
		Cursor.execute(Query, Values)
		Result = Cursor.fetchall()
		return list(Result)
	except MySQLdb.Error as error:
		print(f"[DB] Error: {error}")
		raise
	finally:
		Cursor.close()
		Connection.close()

def Get_chans_for_server(Table, Server_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				SELECT DISTINCT chan_id FROM {Table}
				WHERE server_id = %s
				ORDER BY chan_id""",
				(Server_ID,)
		)
		Result = Cursor.fetchall()
		if Result:
			List_chans = []
			IRC_bridges = Config.get("irc_bridges", {})
			for Row in Result:
				Chan_ID = Row[0]
				for IRC_chan in IRC_bridges:
					if IRC_bridges[IRC_chan]["discord_chan"] == Chan_ID:
						Chan_name = IRC_bridges[IRC_chan]["irc_chan"]
				List_chans.append({
						"id": str(Chan_ID),
						"name": Chan_name,
				})
		return List_chans
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Messages_potentially_expired(Table):
	"""Return the messages corresponding to the two expiration periods: after one month, and after
	one year (plus a delay as safety margin)."""
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Messages = []
		Cursor.execute(f"""
				SELECT creation_date, chan_id, message_id, user FROM {Table}
				WHERE relayed = TRUE
				AND expired = FALSE
				AND creation_date BETWEEN UTC_TIMESTAMP() - INTERVAL 13 MONTH
						AND UTC_TIMESTAMP() - INTERVAL 1 MONTH"""
		)
		Result = Cursor.fetchall()
		if Result:
			for Row in Result:
				Messages.append({
						"creation_date": Row[0],
						"chan_id": Row[1],
						"message_id": Row[2],
						"user": Row[3],
				})
		return Messages
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Mark_message_expired(Table, Message_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				UPDATE {Table} SET expired = TRUE
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Users_check_presence(Table, Infos_user):
	"""Check if the identifiers of this user (pseudo, first name, last name, etc) match other
	identifiers already present in the DB."""

	Connection = Connect_DB()
	Cursor = Connection.cursor()
	Fields = {
			"pseudo": "",
			"mail": "",
			"first_name": "",
			"last_name": "",
			"ml_pseudo": "",
			"wiki_pseudo": "",
			"irc_pseudo": "",
			"forum_pseudo": "",
			"discord_username": "",
			"discord_display_name": "",
	}
	if "Pseudo" in Infos_user.keys():
		Fields["pseudo"] = Infos_user["Pseudo"]
	if "Mail" in Infos_user.keys():
		Fields["mail"] = Infos_user["Mail"]
	if "First_name" in Infos_user.keys():
		Fields["first_name"] = Infos_user["First_name"]
	if "Last_name" in Infos_user.keys():
		Fields["last_name"] = Infos_user["Last_name"]
	if "ML_pseudo" in Infos_user.keys():
		Fields["ml_pseudo"] = Infos_user["ML_pseudo"]
	if "Wiki_pseudo" in Infos_user.keys():
		Fields["wiki_pseudo"] = Infos_user["Wiki_pseudo"]
	if "IRC_pseudo" in Infos_user.keys():
		Fields["irc_pseudo"] = Infos_user["IRC_pseudo"]
	if "Forum_pseudo" in Infos_user.keys():
		Fields["forum_pseudo"] = Infos_user["Forum_pseudo"]
	if "Discord_username" in Infos_user.keys():
		Fields["discord_username"] = Infos_user["Discord_username"]
	if "Discord_display_name" in Infos_user.keys():
		Fields["discord_display_name"] = Infos_user["Discord_display_name"]

	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Other_identifiers = {}
		for Column in Fields.keys():
			if not Fields[Column]:
				continue
			for Other_column in Fields.keys():
				Cursor.execute(f"""
						SELECT * FROM {Table}
						WHERE {Other_column} = %s""",
						(Fields[Column],)
				)
				Results = Cursor.fetchall()
				if len(Results) > 0:
					for Result in Results:
						Mail_login = Result[2].split("@")[0]
						Mail_login = Mail_login.split("+")[0]
						# Sometimes used as an alternative recipient delimiter
						Mail_login = Mail_login.split("-")[0]
						# Result[1] = user ID so this line means “Other_identifiers[user ID]”
						Other_identifiers[Result[1]] = {
								"Mail":					Result[2],
								"First_name":			Result[3],
								"Last_name":			Result[4],
								"Pseudos": {
										"Main":			Result[0],
										"Mail_login":	Mail_login,
										"ML":			Result[5],
										"Wiki":			Result[6],
										"IRC":			Result[7],
										"Forum":		Result[8],
										"Discord":		Result[9],
								}
						}

		if len(Other_identifiers) > 0:
			for Candidate_ID in Other_identifiers:
				Infos_candidate = Other_identifiers[Candidate_ID]
				Old_pseudo = Infos_candidate["Pseudos"]["Main"]
				New_pseudo = Infos_user.get("Pseudo")
				if (Infos_candidate.get("First_name") == Infos_user.get("First_name") \
						and Infos_candidate.get("Last_name") == Infos_user.get("Last_name") \
				) or Infos_candidate.get("Mail") == Infos_user.get("Mail"):
					if New_pseudo and New_pseudo != Old_pseudo:
						print(f"[DB] New pseudo? “{Old_pseudo}” vs new “{New_pseudo}”")
					return Candidate_ID

				# Check if there’s a match in the pseudos of the different platforms
				Candidate_values = set()
				for Value in Infos_candidate["Pseudos"].values():
					if Value:
						Candidate_values.add(Value.strip().lower())
				User_values = set()
				for Key in ["Pseudo", "ML_pseudo", "Wiki_pseudo", "IRC_pseudo", "Forum_pseudo", "Discord_username", "Discord_display_name"]:
					Value = Infos_user.get(Key)
					if Value:
						User_values.add(Value.strip().lower())
				for Value in User_values:
					if Value in Candidate_values:
						if New_pseudo and New_pseudo != Old_pseudo:
							print(f"[DB] New pseudo? “{Old_pseudo}” vs “{New_pseudo}”")
						return Candidate_ID

		# If we haven’t found anything
		return None

	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Users_fetch_users(Table):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	Users = {}
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"SELECT * FROM {Table}")
		Results = Cursor.fetchall()
		for Result in Results:
			User_ID = Result[1]
			Dates = json.loads(Result[13]) if Result[13] else {}
			Renewals = {}
			for Year, Dates_for_year in Dates.items():
				Year = int(Year)
				Renewals[Year] = []
				for Date in Dates_for_year:
					Renewals[Year].append(datetime.datetime.fromisoformat(Date))
				Renewals[Year].sort()
			Amounts = json.loads(Result[14]) if Result[14] else {}
			Contributions = {}
			if len(Amounts) > 0:
				for Year, Amount in Amounts.items():
					Contributions[int(Year)] = Amount
			Infos_user = {
					"Pseudo":				Result[0],
					"ID":					User_ID,
					"Mail":					Result[2],
					"First_name":			Result[3],
					"Last_name":			Result[4],
					"ML_pseudo":			Result[5],
					"Wiki_pseudo":			Result[6],
					"IRC_pseudo":			Result[7],
					"Forum_pseudo":			Result[8],
					"Discord_username":		Result[9],
					"Discord_display_name":	Result[10],
					"Discord_expiration":	Result[11],
					"Avatar_URL":			Result[12],
					"Renewals":				Renewals,
					"Contributions":		Contributions,
					"Last_medium":			Result[15],
			}
			Users[User_ID] = Infos_user
		return Users
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Users_manage_user(Table, Action, Infos_user):
	"""This function expects a complete and clean dictionary as input. All necessary checks are
	assumed to have been performed."""
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	Dates = {}
	for Year, Dates_for_year in Infos_user["Renewals"].items():
		Dates[Year] = []
		for Date in Dates_for_year:
			Dates[Year].append(Date.isoformat(sep=" "))
	Renewals = json.dumps(Dates)
	Contributions = json.dumps(Infos_user["Contributions"]) if Infos_user["Contributions"] else None
	if Action == "Add":
		Query = f"""
				INSERT INTO {Table} (
					pseudo,
					mail,
					first_name,
					last_name,
					ml_pseudo,
					wiki_pseudo,
					irc_pseudo,
					forum_pseudo,
					discord_username,
					discord_display_name,
					discord_expiration,
					avatar_url,
					renewals,
					contributions,
					last_medium)
				VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
	if Action == "Update":
		User_ID = Infos_user["ID"]
		Query = f"""
				UPDATE {Table} SET
					pseudo = %s,
					mail = %s,
					first_name = %s,
					last_name = %s,
					ml_pseudo = %s,
					wiki_pseudo = %s,
					irc_pseudo = %s,
					forum_pseudo = %s,
					discord_username = %s,
					discord_display_name = %s,
					discord_expiration = %s,
					avatar_url = %s,
					renewals = %s,
					contributions = %s,
					last_medium = %s
				WHERE id = {User_ID}"""
	# Avoid directly inserting JSON into a SQL query, since it could break if the JSON contains
	# quotes. Using %s instead, in combination with this Values list, allows mysqlclient to escape
	# JSON strings, thus avoiding the risk of SQL syntax errors
	Values = [
			Infos_user["Pseudo"],
			Infos_user["Mail"],
			Infos_user["First_name"],
			Infos_user["Last_name"],
			Infos_user["ML_pseudo"],
			Infos_user["Wiki_pseudo"],
			Infos_user["IRC_pseudo"],
			Infos_user["Forum_pseudo"],
			Infos_user["Discord_username"],
			Infos_user["Discord_display_name"],
			Infos_user["Discord_expiration"],
			Infos_user["Avatar_URL"],
			Renewals,
			Contributions,
			Infos_user["Last_medium"]
	]
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(Query, Values)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_create(Table, User, Question, Choices):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				INSERT INTO {Table} (user, question, choices)
				VALUES (%s, %s, %s)""",
				(User, Question, json.dumps(Choices))
		)
		Connection.commit()
		return Cursor.lastrowid
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_close(Table, Poll_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				UPDATE {Table} SET active = FALSE
				WHERE id = %s""",
				(Poll_ID,)
		)
		if Cursor.rowcount == 0:
			return False
		Connection.commit()
		return True
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_delete(Table, Poll_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				DELETE FROM {Table}
				WHERE id = %s""",
				(Poll_ID,)
		)
		if Cursor.rowcount == 0:
			return False
		Connection.commit()
		return True
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_fetch(Table, Poll_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				SELECT * FROM {Table}
				WHERE id = %s""",
				(Poll_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			return None
		Choices = json.loads(Result[4]) if Result[4] else {}
		if Choices:
			Temp = {}
			for Index, Choice in enumerate(Choices):
				Temp[Index + 1] = Choice
			Choices = Temp
		Infos_poll = {
				"ID": Poll_ID,
				"Creation_date": Result[1],
				"Author": Result[2] if Result[2] else "Anonymous",
				"Question": Result[3],
				"Choices": Choices,
				"Votes": json.loads(Result[5]) if Result[5] else {},
				"Proxies": json.loads(Result[6]) if Result[6] else {},
				"Active": bool(Result[7]),
		}
		return Infos_poll
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_fetch_list(Table, Number, Status=None):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Query = f"SELECT id FROM {Table} "
		# If the latest poll is requested, return it whether it’s active or not
		if Status == "latest":
			Query += f"ORDER BY id DESC LIMIT {Number}"
		else:
			if Status == "active":
				Query += "WHERE active = TRUE "
			elif Status == "closed":
				Query += "WHERE active = FALSE "
			Query += f"ORDER BY active DESC, id DESC LIMIT {Number}"
		Cursor.execute(Query)
		Results = Cursor.fetchall()
		Polls = []
		for Result in Results:
			Poll_ID = Result[0]
			Infos_poll = Polls_fetch(Table, Poll_ID)
			if Infos_poll:
				Polls.append(Infos_poll)
		# Sort the list from oldest to newest
		Polls.reverse()
		return Polls
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_vote(Table, Poll_ID, Pseudo, Choice_index, Proxy_holder=None):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Infos_poll = Polls_fetch(Table, Poll_ID)
		if not Infos_poll:
			return False
		Votes = Infos_poll["Votes"]
		Votes[Pseudo] = Choice_index
		Query = f"UPDATE {Table} SET votes = %s"
		Values = [json.dumps(Votes)]
		if Proxy_holder:
			Proxies = Infos_poll["Proxies"]
			Proxies[Pseudo] = Proxy_holder
			Query += ", proxies = %s"
			Values.append(json.dumps(Proxies))
		Query += f" WHERE id = {Poll_ID}"
		Cursor.execute(Query, Values)
		Connection.commit()
		return True
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Polls_unvote(Table, Poll_ID, Votes):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Query = f"UPDATE {Table} SET votes = %s WHERE id = {Poll_ID}"
		Values = [json.dumps(Votes)]
		Cursor.execute(Query, Values)
		Connection.commit()
		return True
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		return False
	finally:
		Cursor.close()
		Connection.close()
