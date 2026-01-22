# Harmonia

A bot to set up a bridge between Discord and IRC.

# Code structure

The different sections of the bot are separated into modules.

Harmonia.py  
The script used to start the bot.

Config\_manager.py  
Loads and processes the configuration and localizations.

DB\_manager.py  
Manages database-related operations.

Discord\_related.py  
Functions specific to Discord, like handling events concerning sent/deleted messages (on\_message/on\_raw\_message\_delete).

IRC\_related.py  
Functions specific to IRC, using pydle.

# Installation

I’m using the bot on Debian 13 (trixie).

#### Python virtual environment

The python3-pydle package in trixie isn’t usable, we need to create a venv with pip.

Sentence from the output of the pip command:  
“If you wish to install a non-Debian-packaged Python package, create a virtual environment. […] Make
sure you have python3-full installed.”

	# apt install python3-full

To build the package mysqlclient:

	# apt install python3-dev default-libmysqlclient-dev build-essential pkg-config

Create the virtual environment:

	% python3 -m venv ~/.local/pydle-python3.13
	% ~/.local/pydle-python3.13/bin/pip install discord.py pydle PyYAML mysqlclient

#### Database

Create a base according to your Config.yaml, then create this table:

	CREATE TABLE history (
	    date_creation   TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00'
	    server_id       BIGINT NOT NULL,
	    chan_id         BIGINT NOT NULL,
	    message_id      BIGINT NOT NULL PRIMARY KEY,
	    reply_to        BIGINT NULL,
	    user_name       VARCHAR(32) NOT NULL,
	    content         TEXT NOT NULL,
	    edited          BOOLEAN NOT NULL DEFAULT FALSE,
	    attachments     TEXT NULL,
	    reactions       TEXT NULL,
	    date_deletion   TIMESTAMP NULL
	);

Creating the field date\_creation with “TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00'” is
necessary. Otherwise, MariaDB automatically assigns the following attributes to the column: “DEFAULT
CURRENT\_TIMESTAMP ON UPDATE CURRENT\_TIMESTAMP”, which would cause the message’s creation date to
be lost with any changes to the field.

#### Last steps

	% git https://github.com/almic-stardust/harmonia
	% cd harmonia

Adjust the configuration to your needs:

Config\_dist.yaml  
Example of configuration file to modify. Rename it as Config.yaml

Finally, you can start the bot:

	% ~/.local/pydle-python3.13/bin/python3 Harmonia.py

#### Generate a Web display for the history

If you need this additional feature, here is the procedure to follow.

	% cd harmonia/display_history
	% ln -s ../DB_manager.py
	% ln -s ../Config.yaml
	% ln -s ../Config_manager.py

For performance, create composite indexes in the DB:

	CREATE INDEX Index_messages ON history (server_id, chan_id, date_creation);
	CREATE INDEX Index_replies ON history (reply_to);
	CREATE INDEX Index_deletions ON history (server_id, chan_id, date_deletion);

The ASGI server I use is Hypercorn. On the system where you want to run it:

	# apt install python3-hypercorn python3-fastapi python3-jinja2 python3-yaml python3-mysqldb
	% cd harmonia/display_history
	% hypercorn --certfile /path/to/cert.pem --keyfile /path/to/key.pem --bind '127.0.0.1:60444' Main:Display_history

Then you need to configure nginx (for example), with a VirtualServer acting as a reverse proxy
towards 127.0.0.1:60444. Also, it could be useful to create a service in SystemD, so that Hypercorn
starts when the system boots.

The history should now be accessible at:

	https://domain.tld/server_id/chan_id

Instead of Hypercorn, you can use uvicorn. It’s useful during development, thanks to its option
--reload.

	# apt install uvicorn
	% python3 -m uvicorn Main:Display_history --host Local_IP --port 8080  --reload

Or, if you must have the very latest version:

	% python3 -m venv ~/.local/uvicorn-python3.13
	% ~/.local/uvicorn-python3.13/bin/pip install uvicorn fastapi Jinja2 PyYAML mysqlclient
	% ~/.local/uvicorn-python3.13/bin/uvicorn Main:Display_history --host Local_IP --port 8080 --reload

Now the history should also be accessible at:

	http://domain.tld:8080/server_id/chan_id
