#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:-serve}"

case "$mode" in
  init-key)
    uid="${HERMES_UID:-1000}"
    gid="${HERMES_GID:-1000}"
    install -d -m 0755 /client-key /authorized-key
    if [[ ! -s /client-key/id_ed25519 || ! -s /client-key/id_ed25519.pub ]]; then
      rm -f /client-key/id_ed25519 /client-key/id_ed25519.pub
      ssh-keygen -q -t ed25519 -N "" -C "hermes-sandbox" -f /client-key/id_ed25519
    fi
    chown "$uid:$gid" /client-key/id_ed25519 /client-key/id_ed25519.pub
    chmod 0600 /client-key/id_ed25519
    chmod 0644 /client-key/id_ed25519.pub
    install -m 0644 /client-key/id_ed25519.pub /authorized-key/authorized_keys.new
    mv -f /authorized-key/authorized_keys.new /authorized-key/authorized_keys
    echo "Hermes sandbox client key is ready."
    ;;

  trust-host)
    host_key=/sandbox-host-key/ssh_host_ed25519_key.pub
    known_hosts_dir=/hermes-trust
    known_hosts="$known_hosts_dir/known_hosts"
    host='[sandbox]:2222'

    if [[ ! -s "$host_key" ]]; then
      echo "Missing sandbox public host key; start the sandbox first." >&2
      exit 1
    fi
    ssh-keygen -l -f "$host_key" >/dev/null
    read -r key_type key_data _ < "$host_key"
    if [[ "$key_type" != ssh-ed25519 || ! "$key_data" =~ ^[A-Za-z0-9+/]+={0,3}$ ]]; then
      echo "Sandbox public host key is not a valid ED25519 key." >&2
      exit 1
    fi

    umask 077
    mkdir -p "$known_hosts_dir"
    touch "$known_hosts"
    ssh-keygen -f "$known_hosts" -R "$host" >/dev/null 2>&1
    printf '%s %s %s\n' "$host" "$key_type" "$key_data" >> "$known_hosts"
    rm -f "$known_hosts.old"
    echo "Hermes trusts the persisted sandbox host key."
    ;;

  serve)
    if [[ ! -s /run/hermes-authorized-key/authorized_keys ]]; then
      echo "Missing sandbox authorized key; run the sandbox-keygen service first." >&2
      exit 1
    fi

    install -d -m 0700 -o agent -g agent /home/agent/.ssh
    install -m 0600 -o agent -g agent \
      /run/hermes-authorized-key/authorized_keys \
      /home/agent/.ssh/authorized_keys

    # The directory is traversable so the unprivileged trust reconciler can
    # read the 0644 public key. The private host key remains root-only at 0600.
    install -d -m 0755 /etc/ssh/host-keys
    if [[ ! -s /etc/ssh/host-keys/ssh_host_ed25519_key \
      || ! -s /etc/ssh/host-keys/ssh_host_ed25519_key.pub ]]; then
      rm -f /etc/ssh/host-keys/ssh_host_ed25519_key \
        /etc/ssh/host-keys/ssh_host_ed25519_key.pub
      ssh-keygen -q -t ed25519 -N "" -f /etc/ssh/host-keys/ssh_host_ed25519_key
    fi
    chmod 0600 /etc/ssh/host-keys/ssh_host_ed25519_key
    chmod 0644 /etc/ssh/host-keys/ssh_host_ed25519_key.pub
    chmod 0755 /etc/ssh/host-keys

    install -d -m 0755 /run/sshd
    chown -R agent:agent /home/agent
    /usr/sbin/sshd -t -f /etc/ssh/sshd_config
    exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config
    ;;

  *)
    echo "Unknown sandbox mode: $mode" >&2
    exit 2
    ;;
esac
