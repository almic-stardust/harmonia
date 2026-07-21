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
		# Check if there is an entry with Old_filename in its content_history field
		Cursor.execute(f"""
				SELECT message_id, content_history
				FROM {Table}
				WHERE JSON_SEARCH(content_history, 'one', %s) IS NOT NULL """,
				(Old_filename,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print("[DB] Error: There’s already a file with that name in the folder, but it wasn’t registered in the DB for that message")
			return
		Message_ID, Content_history = Result
		Content_history = json.loads(Content_history)
		Modified = False
		for Entry in Content_history:
			# Avoid adding a dependency on Gears and Discord_manager modules for display_history
			from Gears import Is_URL
			if "Attachments" in Content_history[Entry]:
				for Index, Filename in enumerate(Content_history[Entry]["Attachments"]):
					if Is_URL(Filename):
						continue
					if Filename == Old_filename:
						Content_history[Entry]["Attachments"][Index] = New_filename
						Modified = True
			if "Deleted_attachments" in Content_history[Entry]:
				for Index, Filename in enumerate(Content_history[Entry]["Deleted_attachments"]):
					if Is_URL(Filename):
						continue
					if Filename == Old_filename:
						Content_history[Entry]["Deleted_attachments"][Index] = New_filename
						Modified = True
		if not Modified:
			print("[DB] Error: filename found by JSON_SEARCH(), but no matching list entry was updated.")
			return
		Cursor.execute(f"""
				UPDATE {Table} SET content_history = %s
				WHERE message_id = {Message_ID}""",
				(json.dumps(Content_history),)
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
		New_entry = Date.isoformat(timespec="seconds") + f".{Centiseconds:02d}"
		Content_history = {New_entry: {
				"Text": Text
		}}
		if len(Attachments) > 0:
			Content_history[New_entry]["Attachments"] = Attachments
		Content_history = json.dumps(Content_history)
		Cursor.execute(f"""
				INSERT INTO {Table} (
					creation_date,
					server_id, chan_id, message_id,
					reply_to,
					user, content_history, relayed)
				VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
				(
					Date,
					Server_ID, Chan_ID, Message_ID,
					Replied_message_ID,
					Discord_username, Content_history, Relayed
				)
		)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_edition(Table, Keep, Message_ID, Date, New_text, Deleted_filenames):

	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Retrieve the necessary informations from the DB
		Cursor.execute(f"""
				SELECT content_history FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print(f"[DB] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
			return

		Content_history = json.loads(Result[0])
		# The keys are ISO timestamps, so lexicographic order matches chronological order
		First_entry = min(Content_history)
		if Keep:
			Centiseconds = round(Date.microsecond / 10000)
			Current_entry = Date.isoformat(timespec="seconds") + f".{Centiseconds:02d}"
		else:
			Current_entry = First_entry
		Last_text_entry = First_entry
		Content_history[Current_entry] = {}
		for Entry in Content_history:
			if "Text" in Content_history[Entry] and Last_text_entry < Entry:
				Last_text_entry = Entry
		if Content_history[Last_text_entry]["Text"] != New_text:
			Content_history[Current_entry]["Text"] = New_text

		if len(Deleted_filenames) > 0:
			if Keep:
				Content_history[Current_entry]["Deleted_attachments"] = []
			for Deleted_filename in Deleted_filenames:
				if Deleted_filename["Previous_filename"] in Content_history[First_entry]["Attachments"]:
					Content_history[First_entry]["Attachments"].remove(
							Deleted_filename["Previous_filename"]
					)
					if len(Content_history[First_entry]["Attachments"]) == 0:
						del Content_history[First_entry]["Attachments"]
				if Keep:
					Content_history[Current_entry]["Deleted_attachments"].append(
							Deleted_filename["New_filename"]
					)

		Content_history = json.dumps(Content_history)
		Query = f"UPDATE {Table} SET content_history = %s WHERE message_id = {Message_ID}"
		Values = [Content_history]
		Cursor.execute(Query, Values)
		Connection.commit()

	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_deletion(Table, Keep, Message_ID, Date, Deleted_attachments):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Retrieve the necessary informations from the DB
		Cursor.execute(f"""
				SELECT content_history FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print(f"[DB] Warning: this message can’t be deleted from the DB, because it hasn’t been recorded in it.")
			return
		Content_history = json.loads(Result[0])
		# The keys are ISO timestamps, so lexicographic order matches chronological order
		Current_entry = max(Content_history)
		if Keep:
			Query = f"UPDATE {Table} SET deletion_date = %s"
			Values = [Date]
			if len(Deleted_attachments) > 0:
				# if Deleted_attachments isn’t empty, it means Content_history[Current_entry] had an
				# "Attachements" entry, with files that have just been marked as deleted
				if "Attachments" in Content_history[Current_entry]:
					del Content_history[Current_entry]["Attachments"]
				# The message might have been edited to delete some attachments but not all, so the
				# latest edition could already contain a "Deleted_attachments" entry
				if "Deleted_attachments" in Content_history[Current_entry]:
					Content_history[Current_entry]["Deleted_attachments"].extend(
							Deleted_attachments
					)
				else:
					Content_history[Current_entry]["Deleted_attachments"] = list(
							Deleted_attachments
					)
				Content_history = json.dumps(Content_history)
				Query += ", content_history = %s"
				Values.append(Content_history)
			Query += f" WHERE message_id = %s"
			Values.append(Message_ID)
		else:
			Query = f"DELETE FROM {Table} WHERE message_id = %s"
			Values = [Message_ID]
		Cursor.execute(Query, Values)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def SyncHistory_add_period(Server_ID, Chan_ID, Oldest, Latest):
	Connection = Connect_DB()
	# To manipulate results using a dictionary
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
	try:
		Cursor.execute("""
				SELECT oldest_message_id, latest_message_id FROM history_sync
				WHERE server_id = %s AND chan_id = %s
				ORDER BY oldest_message_id""",
				(Server_ID, Chan_ID)
		)
		Periods = Cursor.fetchall()
		New_oldest = Oldest
		New_latest = Latest
		Delete = []
		for Period in Periods:
			Periods_not_overlapping = (
				Period["latest_message_id"] + 1 < New_oldest
				or Period["oldest_message_id"] - 1 > New_latest
			)
			if Periods_not_overlapping:
				continue
			New_oldest = min(New_oldest, Period["oldest_message_id"])
			New_latest = max(New_latest, Period["latest_message_id"])
			Delete.append((Period["oldest_message_id"], Period["latest_message_id"]))
		for Period in Delete:
			Cursor.execute("""
					DELETE FROM history_sync
					WHERE server_id=%s AND chan_id=%s
					AND oldest_message_id=%s AND latest_message_id=%s""",
					(Server_ID, Chan_ID, Period[0], Period[1])
			)
		Cursor.execute("""
				INSERT INTO history_sync (server_id, chan_id, oldest_message_id, latest_message_id)
				VALUES (%s, %s, %s, %s)""",
				(Server_ID, Chan_ID, New_oldest, New_latest)
		)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def SyncHistory_find_next_gap(Server_ID, Chan_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
	try:
		Cursor.execute("""
				SELECT oldest_message_id, latest_message_id FROM history_sync
				WHERE server_id = %s AND chan_id = %s
				ORDER BY latest_message_id DESC""",
				(Server_ID, Chan_ID)
		)

		Periods = Cursor.fetchall()
		if not Periods:
			return {"Latest": None}
		# Walk from latest to oldest looking for a gap
		Previous_oldest = Periods[0]["oldest_message_id"]
		for Period in Periods[1:]:
			if Period["latest_message_id"] + 1 < Previous_oldest:
				return {"Latest": Previous_oldest}
			Previous_oldest = Period["oldest_message_id"]
		# Still haven’t reached the beginning of the chan
		return {"Latest": Previous_oldest}
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_fetch_message(Table, Message_ID):

	Connection = Connect_DB()
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
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
					reactions,
					relayed,
					expired,
					deletion_date
				FROM {Table} WHERE message_id = %s""",
				(Message_ID,))
		Result = Cursor.fetchone()

		Infos_message = None
		Content_history = {}
		Attachments = []
		Deleted_attachments = []

		if Result:

			if Result["content_history"]:
				Content_history = Result["content_history"]
				# Decode the JSON only if the returned object is a string: depending on the driver
				# version, MariaDB may return JSON columns as already-decoded Python objects
				if isinstance(Content_history, str):
					try:
						Content_history = json.loads(Content_history)
						Content_history = {
							datetime.datetime.fromisoformat(Date): Text
							for Date, Text in Content_history.items()
						}
						First_entry = min(Content_history)
						Attachments = Content_history[First_entry].get("Attachments", [])
						Deleted_attachments = []
						for Entry in Content_history:
							if "Deleted_attachments" in Content_history[Entry]:
								Deleted_attachments.append(
										Content_history[Entry]["Deleted_attachments"]
								)
					except json.JSONDecodeError:
						print("[DB] Invalid data in the content_history field:", repr(Content_history))

			if Result["reactions"]:
				Reactions = Result["reactions"]
				if isinstance(Reactions, str):
					Reactions = json.loads(Reactions)
			else:
				Reactions = {}

			Infos_message = {
					"Creation_date":		Result["creation_date"],
					"Server_ID":			Result["server_id"],
					"Chan_ID":				Result["chan_id"],
					"Message_ID":			Result["message_id"],
					"Reply_to":				Result["reply_to"] if Result["reply_to"] else None,
					"User":					Result["user"],
					"Content_history":		Content_history,
					"Attachments":			Attachments,
					"Deleted_attachments":  Deleted_attachments,
					"Reactions":			Reactions,
					"Relayed":				bool(Result["relayed"]),
					"Expired":				bool(Result["expired"]),
					"Deletion_date":		Result["deletion_date"] \
													if Result["deletion_date"] else None,
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
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
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
						"creation_date":	Row["creation_date"],
						"chan_id":			Row["chan_id"],
						"message_id":		Row["message_id"],
						"user":				Row["user"],
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
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
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
			"pseudo_displayed_on_discord": "",
	}
	Dict_keys = {
		"Pseudo", "Mail", "First_name", "Last_name",
		"ML_pseudo", "Wiki_pseudo", "IRC_pseudo", "Forum_pseudo",
		"Discord_username", "Discord_display_name"
	}
	for Dict_key in Dict_keys:
		if Dict_key in Infos_user:
			Fields[Dict_key.lower()] = Infos_user[Dict_key]

	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Other_identifiers = {}
		for Column in Fields:
			if not Fields[Column]:
				continue
			for Other_column in Fields:
				Cursor.execute(f"""
						SELECT * FROM {Table}
						WHERE {Other_column} = %s""",
						(Fields[Column],)
				)
				Results = Cursor.fetchall()
				if len(Results) > 0:
					for Result in Results:
						Mail_login = Result["mail"].split("@")[0]
						Mail_login = Mail_login.split("+")[0]
						# Sometimes used as an alternative recipient delimiter
						Mail_login = Mail_login.split("-")[0]
						User_ID = Result["id"]
						Other_identifiers[User_ID] = {
								"Mail":						Result["mail"],
								"First_name":				Result["first_name"],
								"Last_name":				Result["last_name"],
								"Pseudos": {
										"Main":				Result["pseudo"],
										"Mail_login":		Mail_login,
										"ML":				Result["ml_pseudo"],
										"Wiki":				Result["wiki_pseudo"],
										"IRC":				Result["irc_pseudo"],
										"Forum":			Result["forum_pseudo"],
										"Discord_username":	Result["discord_username"],
										"Pseudo_displayed_on_Discord": Result["pseudo_displayed_on_discord"],
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
				for Key in ("Pseudo", "ML_pseudo", "Wiki_pseudo", "IRC_pseudo", "Forum_pseudo", "Discord_username", "Pseudo_displayed_on_Discord"):
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
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
	Users = {}
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"SELECT * FROM {Table}")
		Results = Cursor.fetchall()
		for Result in Results:
			User_ID = Result["id"]
			Keep = Result["history_keep_all"]
			if Keep is None:
				Keep = True
			else:
				Keep = bool(Keep)
			Dates = json.loads(Result["renewals"]) if Result["renewals"] else {}
			Renewals = {}
			for Year, Dates_for_year in Dates.items():
				Year = int(Year)
				Renewals[Year] = []
				for Date in Dates_for_year:
					Renewals[Year].append(datetime.datetime.fromisoformat(Date))
				Renewals[Year].sort()
			Amounts = json.loads(Result["contributions"]) if Result["contributions"] else {}
			Contributions = {}
			if len(Amounts) > 0:
				for Year, Amount in Amounts.items():
					Contributions[int(Year)] = Amount
			Infos_user = {
					"Pseudo":						Result["pseudo"],
					"ID":							User_ID,
					"Mail":							Result["mail"],
					"First_name":					Result["first_name"],
					"Last_name":					Result["last_name"],
					"ML_pseudo":					Result["ml_pseudo"],
					"Wiki_pseudo":					Result["wiki_pseudo"],
					"IRC_pseudo":					Result["irc_pseudo"],
					"Forum_pseudo":					Result["forum_pseudo"],
					"Discord_username":				Result["discord_username"],
					"Pseudo_displayed_on_Discord":	Result["pseudo_displayed_on_Discord"],
					"Discord_expiration_for_IRC":	Result["discord_expiration_for_irc"],
					"History_keep_all":				Keep,
					"Avatar_URL":					Result["avatar_url"],
					"Renewals":						Renewals,
					"Contributions":				Contributions,
					"Last_medium":					Result["last_medium"],
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
					pseudo_displayed_on_discord,
					discord_expiration_for_irc,
					history_keep_all,
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
					pseudo_displayed_on_discord = %s,
					discord_expiration_for_irc = %s,
					history_keep_all = %s,
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
			Infos_user["Pseudo_displayed_on_Discord"],
			Infos_user["Discord_expiration_for_IRC"],
			Infos_user["History_keep_all"],
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
	Cursor = Connection.cursor(MySQLdb.cursors.DictCursor)
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
		Choices = json.loads(Result["choices"]) if Result["choices"] else {}
		if Choices:
			Temp = {}
			for Index, Choice in enumerate(Choices):
				Temp[Index + 1] = Choice
			Choices = Temp
		Infos_poll = {
				"ID":				Poll_ID,
				"Creation_date":	Result["creation_date"],
				"Author":			Result["user"] if Result["user"] else "Anonymous",
				"Question":			Result["question"],
				"Choices":			Choices,
				"Votes":			json.loads(Result["votes"]) if Result["votes"] else {},
				"Proxies":			json.loads(Result["proxies"]) if Result["proxies"] else {},
				"Active":			bool(Result["active"]),
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
