#!/bin/bash
#
## remove yarn source list
#rm /etc/apt/sources.list.d/yarn.list
#
## install supervisor
#echo "Installing supervisor ..."
#apt update && apt install -y supervisor || exit
#mkdir -p "/var/log/supervisor"
#mkdir -p "$ADMIN_HELPER_SUPERVISOR_CONFIG_PATH"
#
## download binaries
#bash "./download_binaries.sh" || exit
#
## cd "$ADMIN_HELPER_FILE_BROWSER__PATH" && ./filebrowser config import ./setting.json
## chmod +x "$ADMIN_HELPER_FILE_BROWSER__PATH/start_filebrowser.sh"

# install uv
echo "Installing uv ..."
curl -LsSf https://astral.sh/uv/install.sh | sh || exit

# install cli
echo "Installing CLI ..."
uv sync || exit
