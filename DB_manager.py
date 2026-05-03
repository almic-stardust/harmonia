# -*- coding: utf-8 -*-

import sys
# This actually uses the package mysqlclient, a fork of MySQLdb adding Python 3 support
import MySQLdb
import json

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
				WHERE attachments LIKE %s""",
				('%\\"' + Old_filename.replace("—", "\\\\u2014") + '\\"%',)
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
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def History_addition(Table, Date, Server_ID, Chan_ID, Message_ID, Replied_message_ID, Discord_username, Content, Attachments, Relayed):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if the message is in the DB
		Cursor.execute(f"""
				SELECT message_id FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if Result:
			print("[DB] Warning: this message was already stored in the DB.")
			return
		if len(Attachments) > 0:
			Attachments = json.dumps(Attachments)
		# If the list is empty, save NULL in the attachments field
		else:
			Attachments = None
		Cursor.execute(f"""
				INSERT INTO {Table} (
						date_creation,
						server_id, chan_id, message_id,
						reply_to,
						user, content, attachments, relayed)
						VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
				, (
						Date,
						Server_ID, Chan_ID, Message_ID,
						Replied_message_ID,
						Discord_username, Content, Attachments, Relayed
				)
		)
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
				date_creation,
				server_id,
				chan_id,
				message_id,
				reply_to,
				user,
				content,
				attachments,
				reactions,
				date_deletion
				FROM {Table} WHERE message_id = %s""",
				(Message_ID,))
		Result = Cursor.fetchone()
		DB_entry = []
		if Result:
			DB_entry = list(Result)
			DB_entry[7] = json.loads(DB_entry[7]) if DB_entry[7] else []
		return DB_entry
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
				content,
				edited,
				attachments,
				reactions,
				date_creation,
				date_deletion
			FROM {Table}
			WHERE server_id = %s
			AND chan_id = %s
			AND date_deletion IS NULL
		"""
		Values = [Server_ID, Chan_ID]
		if Before is not None:
			Query += " AND date_creation < %s"
			Values.append(Before)
		Query += " ORDER BY date_creation DESC LIMIT %s"
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

def History_edition(Table, Keep, Message_ID, Date, New_content, Updated_filenames):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		# Check if the message is in the DB
		Cursor.execute(f"""
				SELECT user, content FROM {Table}
				WHERE message_id = %s""",
				(Message_ID,)
		)
		Result = Cursor.fetchone()
		if not Result:
			print(f"[DB] Warning: this message can’t be edited in the DB, because it hasn’t been recorded in it.")
			return
		if Keep:
			Old_content = Result[1]
			Edited_content = f"{Old_content}\n\n<|--- Edited {Date} ---|>\n\n{New_content}"
			if Updated_filenames:
				Updated_filenames = json.dumps(Updated_filenames)
				Cursor.execute(f"""
						UPDATE {Table} SET content = %s, attachments = %s, edited = TRUE
						WHERE message_id = %s""",
						(Edited_content, Updated_filenames, Message_ID)
				)
			else:
				Cursor.execute(f"""
						UPDATE {Table} SET content = %s, edited = TRUE
						WHERE message_id = %s""",
						(Edited_content, Message_ID)
				)
		else:
			Cursor.execute(f"""
					UPDATE {Table} SET content = %s
					WHERE message_id = %s""",
					(New_content, Message_ID)
			)
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
		# Check if the message is in the DB
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
			if Updated_filenames:
				Updated_filenames = json.dumps(Updated_filenames)
				Cursor.execute(f"""
						UPDATE {Table} SET attachments = %s, date_deletion = %s
						WHERE message_id = %s""",
						(Updated_filenames, Date, Message_ID)
				)
			else:
				Cursor.execute(f"""
						UPDATE {Table} SET date_deletion = %s
						WHERE message_id = %s""",
						(Date, Message_ID)
				)
		else:
			Cursor.execute(f"""
					DELETE FROM {Table} WHERE message_id = %s""",
					(Message_ID,)
			)
		Connection.commit()
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
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
				SELECT date_creation, chan_id, message_id, user FROM {Table}
				WHERE relayed = TRUE
				AND expired = FALSE
				AND date_creation BETWEEN UTC_TIMESTAMP() - INTERVAL 13 MONTH
						AND UTC_TIMESTAMP() - INTERVAL 1 MONTH"""
		)
		Result = Cursor.fetchall()
		if Result:
			for Row in Result:
				Messages.append({
						"date_creation": Row[0],
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

def Users_fetch_user(Table, User_ID):
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	User_infos = None
	try:
		if not Table.isidentifier():
			raise ValueError("[DB] Error: invalid table name.")
		Cursor.execute(f"""
				SELECT * FROM {Table}
				WHERE id = %s""",
				(User_ID,)
		)
		Result = Cursor.fetchone()
		User_infos = {
				"Pseudo":				Result[0],
				"ID":					User_ID,
				"Mail":					Result[2],
				"First_name":			Result[3],
				"Last_name":			Result[4],
				"ML_pseudo":			Result[5],
				"Wiki_pseudo":			Result[6],
				"IRC_pseudo":			Result[7],
				"Forum_pseudo":			Result[8],
				"Discord_pseudo":		Result[9],
				"Discord_expiration":	Result[10],
				"Avatar":				Result[11],
				"First_membership":		Result[12],
				"Last_renewal":			Result[13],
				"Medium":				Result[14],
				"Contribution":			Result[15]
		}
		return User_infos
	except MySQLdb.Error as Error:
		print(f"[DB] Error: {Error}")
		sys.exit(1)
	finally:
		Cursor.close()
		Connection.close()

def Users_check_presence(Table, User_infos):
	"""Check if the identifiers of this user (pseudo, first name, last name, etc) match other
	identifiers already present in the DB."""

	Connection = Connect_DB()
	Cursor = Connection.cursor()
	Fields = {
			"pseudonym": "",
			"mail": "",
			"first_name": "",
			"last_name": "",
			"ml_pseudo": "",
			"wiki_pseudo": "",
			"irc_pseudo": "",
			"forum_pseudo": "",
			"discord_pseudo": ""
	}
	if "Pseudo" in User_infos.keys():
		Fields["pseudonym"] = User_infos["Pseudo"]
	if "Mail" in User_infos.keys():
		Fields["mail"] = User_infos["Mail"].split("@")[0]
	if "First_name" in User_infos.keys():
		Fields["first_name"] = User_infos["First_name"]
	if "Last_name" in User_infos.keys():
		Fields["last_name"] = User_infos["Last_name"]
	if "ML_pseudo" in User_infos.keys():
		Fields["ml_pseudo"] = User_infos["ML_pseudo"]
	if "Wiki_pseudo" in User_infos.keys():
		Fields["wiki_pseudo"] = User_infos["Wiki_pseudo"]
	if "IRC_pseudo" in User_infos.keys():
		Fields["irc_pseudo"] = User_infos["IRC_pseudo"]
	if "Forum_pseudo" in User_infos.keys():
		Fields["forum_pseudo"] = User_infos["Forum_pseudo"]
	if "Discord_pseudo" in User_infos.keys():
		Fields["discord_pseudo"] = User_infos["Discord_pseudo"]

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
						# Other_identifiers[user ID] (Result[1] = user ID)
						Other_identifiers[Result[1]] = {
								"Mail":				Result[2].split("@")[0],
								"First_name":		Result[3],
								"Last_name":		Result[4],
								"Pseudos": {
										"Main":		Result[0],
										"ML":		Result[5],
										"Wiki":		Result[6],
										"IRC":		Result[7],
										"Forum":	Result[8],
										"Discord":	Result[9]
								}
						}

		if len(Other_identifiers) > 0:
			for Candidate_ID in Other_identifiers:
				Candidate_infos = Other_identifiers[Candidate_ID]
				Old_pseudo = Candidate_infos["Pseudos"]["Main"]
				New_pseudo = User_infos.get("Pseudo")
				if (Candidate_infos.get("First_name") == User_infos.get("First_name") \
						and Candidate_infos.get("Last_name") == User_infos.get("Last_name") \
				) or Candidate_infos.get("Mail") == User_infos.get("Mail"):
					if New_pseudo and New_pseudo != Old_pseudo:
						print(f"[DB] New pseudo? “{Old_pseudo}” vs “{New_pseudo}”")
					return Candidate_ID

				# Check if there’s a match in the pseudos of the different platforms
				Candidate_values = set()
				for Value in Candidate_infos["Pseudos"].values():
					if Value:
						Candidate_values.add(Value.strip().lower())
				User_values = set()
				for Key in ["Pseudo", "ML_pseudo", "Wiki_pseudo", "IRC_pseudo", "Forum_pseudo", "Discord_pseudo"]:
					Value = User_infos.get(Key)
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

def Users_manage_user(Table, Action, User_infos):
	"""This function expects a complete and clean dictionary as input. All necessary checks are
	assumed to have been performed."""
	Connection = Connect_DB()
	Cursor = Connection.cursor()
	if Action == "Add":
		Query = f"""
				INSERT INTO {Table} (
						pseudonym,
						mail,
						first_name,
						last_name,
						ml_pseudo,
						wiki_pseudo,
						irc_pseudo,
						forum_pseudo,
						discord_pseudo,
						discord_expiration,
						avatar,
						first_membership,
						last_renewal,
						medium,
						contribution)
						VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
	if Action == "Update":
		Query = f"""
				UPDATE {Table} SET
						pseudonym = %s,
						mail = %s,
						first_name = %s,
						last_name = %s,
						ml_pseudo = %s,
						wiki_pseudo = %s,
						irc_pseudo = %s,
						forum_pseudo = %s,
						discord_pseudo = %s,
						discord_expiration = %s,
						avatar = %s,
						first_membership = %s,
						last_renewal = %s,
						medium = %s,
						contribution = %s
				WHERE id = {User_infos['ID']}"""
	Values = [
			User_infos["Pseudo"],
			User_infos["Mail"],
			User_infos["First_name"],
			User_infos["Last_name"],
			User_infos["ML_pseudo"],
			User_infos["Wiki_pseudo"],
			User_infos["IRC_pseudo"],
			User_infos["Forum_pseudo"],
			User_infos["Discord_pseudo"],
			User_infos["Discord_expiration"],
			User_infos["Avatar"],
			User_infos["First_membership"],
			User_infos["Last_renewal"],
			User_infos["Medium"],
			User_infos["Contribution"]
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
