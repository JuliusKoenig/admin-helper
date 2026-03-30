#!/bin/bash

echo "Installing Traefik v$ADMIN_HELPER_TRAEFIK__VERSION ..."
wget -q -O "$ADMIN_HELPER_TEMP_DIR/traefik.tar.gz" "https://github.com/traefik/traefik/releases/download/v$ADMIN_HELPER_TRAEFIK__VERSION/traefik_v$ADMIN_HELPER_TRAEFIK__VERSION""_linux_amd64.tar.gz" || exit
tar -xvzf "$ADMIN_HELPER_TEMP_DIR/traefik.tar.gz" -C "$ADMIN_HELPER_TEMP_DIR/" || exit
mkdir -p "/opt/traefik" || exit
mv "$ADMIN_HELPER_TEMP_DIR/traefik" "/opt/traefik/traefik" || exit
chmod +x "/opt/traefik/traefik" || exit
ln -s /opt/traefik/traefik /usr/local/bin/traefik || exit

echo "Installing uv ..."
curl -LsSf https://astral.sh/uv/install.sh | sh || exit

echo "Installing CLI ..."
cd $(pwd)/cli || exit
uv sync || exit
cd ..