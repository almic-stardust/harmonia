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

display\_history/  
Everything related to the web display of the history.

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

# Web display of the history

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

	# apt install python3-hypercorn python3-fastapi python3-yaml python3-mysqldb
	% cd harmonia/display_history
	% hypercorn -k uvloop -w 4 --bind localhost:60444 --certfile /path/to/cert.pem --keyfile /path/to/key.pem --access-logfile - Main:Display_history

Then you need to configure nginx (for example), with a site acting as a reverse proxy towards
localhost:60444. You also need a nginx alias /static/ for harmonia/display\_history/static/ and
another nginx alias /attachments/ for the storage folder specified in Config.yaml. Once this is
done, the history should be accessible at:

	https://domain.tld/chan/server_id/chan_id

It could be useful to create a SystemD unit, so that Hypercorn starts when the system boots. If you
read French, I wrote a [tutorial for Hypercorn](https://almic.fr/blog/2026/01/19/asgi-hypercorn/)
(nginx configuration, TLS certificate, and SystemD service).

Instead of Hypercorn you can use Uvicorn, which displays a digest log on its standard output. It’s
useful during development.

	# apt install uvicorn
	% python3 -m uvicorn Main:Display_history --host LAN_IP --port 60081 --reload

Or, if you must have the very latest version:

	% python3 -m venv ~/.local/uvicorn-python3.13
	% ~/.local/uvicorn-python3.13/bin/pip install uvicorn fastapi PyYAML mysqlclient
	% ~/.local/uvicorn-python3.13/bin/uvicorn Main:Display_history --host LAN_IP --port 60081 --reload

Now the history should also be accessible at:

	http://LAN_IP:60081/chan/server_id/chan_id
