# Harmonia

A bot to set up a bridge between Discord and IRC.

# Installation (Debian 13)

From the pip command:  
If you wish to install a non-Debian-packaged Python package, create a virtual environment. […] Make
sure you have python3-full installed.”

apt install python3-full 

To build the package mysqlclient:  
apt install python3-dev default-libmysqlclient-dev build-essential pkg-config 

In \~/.zshrc add:  
export PATH=\~/.local/pydle-python3.13/bin:$PATH

source /etc/zsh/zshrc && source \~/.zshrc  
python3 -m venv \~/.local/pydle-python3.13  
\~/.local/pydle-python3.13/bin/pip install discord.py  
\~/.local/pydle-python3.13/bin/pip install pydle  
\~/.local/pydle-python3.13/bin/pip install PyYAML  
\~/.local/pydle-python3.13/bin/pip install mysqlclient
