#!/bin/bash

# downloading traefik
echo "Downloading Traefik v$ADMIN_HELPER_TRAEFIK_VERSION ..."
wget -q -O "$ADMIN_HELPER_TEMP_DIR/traefik.tar.gz" "https://github.com/traefik/traefik/releases/download/v$ADMIN_HELPER_TRAEFIK_VERSION/traefik_v$ADMIN_HELPER_TRAEFIK_VERSION""_linux_amd64.tar.gz" || exit
tar -xvzf "$ADMIN_HELPER_TEMP_DIR/traefik.tar.gz" -C "$ADMIN_HELPER_TEMP_DIR/" || exit
mkdir -p "$ADMIN_HELPER_TRAEFIK_PATH" || exit
mv "$ADMIN_HELPER_TEMP_DIR/traefik" "$ADMIN_HELPER_TRAEFIK_PATH/traefik" || exit
chmod +x "$ADMIN_HELPER_TRAEFIK_PATH/traefik" || exit
ln -s "$ADMIN_HELPER_TRAEFIK_PATH/traefik" /usr/local/bin/traefik || exit

# downloading ttyd
echo "Downloading ttyd v$ADMIN_HELPER_TTYD_VERSION ..."
wget -q -O "$ADMIN_HELPER_TEMP_DIR/ttyd" "https://github.com/tsl0922/ttyd/releases/download/$ADMIN_HELPER_TTYD_VERSION/ttyd.x86_64" || exit
mkdir -p "$ADMIN_HELPER_TTYD_PATH" || exit
mv "$ADMIN_HELPER_TEMP_DIR/ttyd" "$ADMIN_HELPER_TTYD_PATH/ttyd" || exit
chmod +x "$ADMIN_HELPER_TTYD_PATH/ttyd" || exit
ln -s "$ADMIN_HELPER_TTYD_PATH/ttyd" /usr/local/bin/ttyd || exit

# downloading filebrowser
echo "Downloading FileBrowser v$ADMIN_HELPER_FILE_BROWSER_VERSION ..."
wget -q -O "$ADMIN_HELPER_TEMP_DIR/filebrowser.tar.gz" "https://github.com/filebrowser/filebrowser/releases/download/v$ADMIN_HELPER_FILE_BROWSER_VERSION/linux-amd64-filebrowser.tar.gz" || exit
tar -xvzf "$ADMIN_HELPER_TEMP_DIR/filebrowser.tar.gz" -C "$ADMIN_HELPER_TEMP_DIR/" || exit
mkdir -p "$ADMIN_HELPER_FILE_BROWSER_PATH" || exit
mv "$ADMIN_HELPER_TEMP_DIR/filebrowser" "$ADMIN_HELPER_FILE_BROWSER_PATH/filebrowser" || exit
chmod +x "$ADMIN_HELPER_FILE_BROWSER_PATH/filebrowser" || exit
ln -s "$ADMIN_HELPER_FILE_BROWSER_PATH/filebrowser" /usr/local/bin/filebrowser || exit