#!/usr/bin/env bash

# check ADMIN_HELPER_SHELL_ENABLED, ADMIN_HELPER_FILEBROWSER_ENABLED and ADMIN_HELPER_DASHBOARD_ENABLED is set to false
if [ "${ADMIN_HELPER_SHELL_ENABLED}" = "false" ] && [ "${ADMIN_HELPER_FILEBROWSER_ENABLED}" = "false" ] && [ "${ADMIN_HELPER_DASHBOARD_ENABLED}" = "false" ]; then
  echo "All admin helpers are disabled. Traefik will not start."
  sleep infinity
  exit 0
fi

echo "Starting Traefik ..."

cd /opt/traefik || exit 1

# check ADMIN_HELPER_SHELL_ENABLED is set to false
if [ "${ADMIN_HELPER_SHELL_ENABLED}" = "false" ]; then
  rm -f "dynamic/ttyd.yml"
fi
# check ADMIN_HELPER_FILEBROWSER_ENABLED is set to false
if [ "${ADMIN_HELPER_FILEBROWSER_ENABLED}" = "false" ]; then
  rm -f "dynamic/filebrowser.yml"
fi
# check ADMIN_HELPER_DASHBOARD_ENABLED is set to false
if [ "${ADMIN_HELPER_DASHBOARD_ENABLED}" = "false" ]; then
  rm -f "dynamic/homer.yml"
fi

# set default username if not set
: "${ADMIN_HELPER_USERNAME:=admin}"

# generate random password if not set
ADMIN_HELPER_PASSWORD_GENERATED=false
if [ -z "${ADMIN_HELPER_PASSWORD}" ]; then
  ADMIN_HELPER_PASSWORD=$(openssl rand -base64 12)
  ADMIN_HELPER_PASSWORD_GENERATED=true
fi

# create userfile for basic auth
htpasswd -b -c /opt/traefik/dynamic/.htpasswd "${ADMIN_HELPER_USERNAME}" "${ADMIN_HELPER_PASSWORD}"

# print credentials
echo "--------------------------------"
echo "Traefik Admin Helpers Credentials"
echo "Username: ${ADMIN_HELPER_USERNAME}"
if [ "${ADMIN_HELPER_PASSWORD_GENERATED}" = true ]; then
  echo "Password: ${ADMIN_HELPER_PASSWORD} (generated)"
else
  echo "Password: set by user"
fi
echo "--------------------------------"

./traefik --configFile=traefik.yml