#!/bin/sh
set -eu
umask 077
key=/var/lib/team-ssh/ssh_host_ed25519_key
if [ ! -s "$key" ]; then ssh-keygen -q -t ed25519 -N '' -f "$key"; fi
test -s /enrolled/authorized_keys
cp /enrolled/authorized_keys /run/team_authorized_keys
chmod 644 /run/team_authorized_keys
/usr/sbin/sshd -t
exec /usr/sbin/sshd -D -e
