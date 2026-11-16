#!/usr/bin/env bash
# Interactive setup for the payables agent on a VPS.
#   cd invoice-agent && ./setup.sh
# Safe to re-run: press Enter to keep any value that is already set.
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=.env
bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '  \033[33m! %s\033[0m\n' "$*"; }

get_env() {  # print current value of KEY from .env, without surrounding quotes
  local line
  line=$(grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 || true)
  line=${line#*=}
  line=${line%\'}; line=${line#\'}
  printf '%s' "$line"
}

set_env() {  # set KEY to VALUE in .env (single-quoted so $, # and spaces are literal)
  local key=$1 value=$2
  if [[ $value == *"'"* ]]; then
    echo "  Values cannot contain a single quote ('). Please choose another value." >&2
    return 1
  fi
  KEY="$key" VAL="'$value'" awk '
    BEGIN { done = 0 }
    $0 ~ "^" ENVIRON["KEY"] "=" { if (!done) print ENVIRON["KEY"] "=" ENVIRON["VAL"]; done = 1; next }
    { print }
    END { if (!done) print ENVIRON["KEY"] "=" ENVIRON["VAL"] }
  ' "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

random_string() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-40}"; }

ask() {  # ask KEY "question" [default] [secret]
  local key=$1 question=$2 default=${3:-} secret=${4:-} current value shown
  current=$(get_env "$key")
  if [[ -n $current ]]; then
    if [[ -n $secret ]]; then shown="(already set - Enter to keep)"; else shown="[$current]"; fi
  elif [[ -n $default ]]; then shown="[$default]"; else shown=""; fi
  while true; do
    if [[ -n $secret ]]; then
      read -r -s -p "  $question $shown: " value; echo
    else
      read -r -p "  $question $shown: " value
    fi
    value=${value:-${current:-$default}}
    if [[ -z $value ]]; then echo "  This value is required."; continue; fi
    set_env "$key" "$value" && break
  done
}

need_docker() {
  if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
    info "Docker $(docker --version | awk '{print $3}' | tr -d ,) with Compose found."
    return
  fi
  warn "Docker with the Compose plugin is not installed."
  read -r -p "  Install it now with Docker's official script (get.docker.com)? [y/N] " yn
  if [[ $yn =~ ^[Yy] ]]; then
    curl -fsSL https://get.docker.com | sh
  else
    echo "  Install Docker (https://docs.docker.com/engine/install/) and run ./setup.sh again."; exit 1
  fi
}

compose() { docker compose "$@"; }

# --- HTTPS proxy -------------------------------------------------------------
# If another container already publishes port 443 (e.g. the Caddy in front of n8n), add our site to
# that Caddy instead of starting a second one that would fight over the ports.
SHARED_CADDY=""
SHARED_CADDYFILE=""

find_existing_proxy() {
  docker ps --format '{{.Names}}|{{.Image}}|{{.Ports}}' \
    | awk -F'|' '$3 ~ /:443->/ && $1 != "invoice-agent-caddy-1" { print $1 "|" $2; exit }'
}

caddyfile_on_host() {  # host path of the Caddyfile mounted into container $1
  local mounts src dst
  mounts=$(docker inspect "$1" --format '{{range .Mounts}}{{.Source}}|{{.Destination}}{{"\n"}}{{end}}')
  while IFS='|' read -r src dst; do
    if [[ $dst == /etc/caddy/Caddyfile && -f $src ]]; then echo "$src"; return; fi
    if [[ $dst == /etc/caddy && -f $src/Caddyfile ]]; then echo "$src/Caddyfile"; return; fi
  done <<< "$mounts"
}

configure_proxy() {
  local found name image net domain
  found=$(find_existing_proxy)
  if [[ -z $found ]]; then
    set_env PROXY_MODE own
    set_env COMPOSE_PROFILES caddy
    set_env COMPOSE_FILE docker-compose.yml
    return
  fi
  name=${found%%|*}; image=${found#*|}
  bold "HTTPS"
  info "Container '$name' ($image) already serves ports 80/443 on this server."
  if [[ $image != *caddy* ]]; then
    warn "It is not Caddy, so it can't be configured automatically. The agent will join its network;"
    warn "point $(get_env DOMAIN) at http://payables-agent:8000 in that proxy's settings."
  fi
  net=$(docker inspect "$name" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' | grep -v '^$' | head -n1)
  set_env PROXY_MODE shared
  set_env PROXY_NETWORK "$net"
  set_env COMPOSE_PROFILES ""
  set_env COMPOSE_FILE "docker-compose.yml:docker-compose.proxy.yml"
  info "The agent will join Docker network '$net' as 'payables-agent'."
  if [[ $net == bridge || $net == host ]]; then
    warn "'$name' is on Docker's '$net' network, where containers can't find each other by name."
    warn "Ask for help before continuing: the proxy needs its own Docker network first."
  fi
  if [[ $image != *caddy* ]]; then return; fi

  SHARED_CADDY=$name
  SHARED_CADDYFILE=$(caddyfile_on_host "$name")
  domain=$(get_env DOMAIN)
  if [[ -z $SHARED_CADDYFILE ]]; then
    warn "Couldn't find $name's Caddyfile on disk. Add this block to it yourself, then reload Caddy:"
    printf '\n%s {\n\treverse_proxy payables-agent:8000\n}\n\n' "$domain"
    SHARED_CADDY=""
    return
  fi
  if grep -qE "^[[:space:]]*${domain//./\\.}([[:space:],{]|$)" "$SHARED_CADDYFILE"; then
    info "$SHARED_CADDYFILE already has a block for $domain - leaving it unchanged."
    return
  fi
  info "I'll add this site to $SHARED_CADDYFILE (a backup copy is made first; n8n is not touched):"
  printf '\n    %s {\n        reverse_proxy payables-agent:8000\n    }\n\n' "$domain"
  read -r -p "  OK to add it? [Y/n] " yn
  if [[ $yn =~ ^[Nn] ]]; then SHARED_CADDY=""; warn "Skipped - add the block yourself and reload Caddy."; return; fi
  cp "$SHARED_CADDYFILE" "$SHARED_CADDYFILE.bak.$(date +%Y%m%d%H%M%S)"
  printf '\n# Payables agent (added by invoice-agent/setup.sh)\n%s {\n\tencode gzip\n\treverse_proxy payables-agent:8000 {\n\t\ttransport http {\n\t\t\tread_timeout 10m\n\t\t}\n\t}\n}\n' \
    "$domain" >> "$SHARED_CADDYFILE"
}

reload_shared_caddy() {
  [[ -z $SHARED_CADDY ]] && return
  info "Reloading $SHARED_CADDY (validated first; on error the old config stays live)…"
  if docker exec "$SHARED_CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
    info "Caddy reloaded. The certificate for $(get_env DOMAIN) is requested now (up to a minute)."
  else
    local latest; latest=$(ls -t "$SHARED_CADDYFILE".bak.* | head -n1)
    warn "Reload failed - restoring the previous Caddyfile from $latest."
    cp "$latest" "$SHARED_CADDYFILE"
    docker exec "$SHARED_CADDY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true
    exit 1
  fi
}

main() {
  bold "Payables agent setup"
  need_docker

  if [[ ! -f $ENV_FILE ]]; then cp .env.example "$ENV_FILE"; info "Created .env from .env.example"; fi
  chmod 600 "$ENV_FILE"

  # The container runs as uid 1000; give it the data folders.
  mkdir -p data claude-sessions
  if [[ $(stat -c %u data) != 1000 || $(stat -c %u claude-sessions) != 1000 ]]; then
    if [[ $EUID -eq 0 ]]; then chown -R 1000:1000 data claude-sessions
    else sudo chown -R 1000:1000 data claude-sessions; fi
  fi

  bold "1/4  Web address"
  info "The DNS A record for this name must point at this server's public IP."
  info "This server's addresses: $(hostname -I 2>/dev/null || echo unknown)"
  ask DOMAIN "Domain for the dashboard (e.g. payables.lifeonwalls.co.uk)"
  set_env PUBLIC_BASE_URL "https://$(get_env DOMAIN)"

  bold "2/4  Claude API"
  info "Create a key at https://console.anthropic.com/settings/keys"
  ask ANTHROPIC_API_KEY "Anthropic API key" "" secret

  bold "3/4  Mailbox (read-only)"
  info "Google Workspace: as the accounts user, turn on 2-Step Verification, then create an"
  info "App Password at https://myaccount.google.com/apppasswords. IMAP must be enabled for the user"
  info "(Admin console > Apps > Google Workspace > Gmail > End user access)."
  ask IMAP_USER "Mailbox address" "accounts@lifeonwalls.co.uk"
  ask IMAP_HOST "IMAP server" "imap.gmail.com"
  ask IMAP_PASSWORD "App password (16 letters)" "" secret
  set_env IMAP_PASSWORD "$(get_env IMAP_PASSWORD | tr -d ' ')"

  bold "4/4  Web login and Telegram"
  ask WEB_USERNAME "Web login username" "admin"
  local generated_pw=""
  if [[ -z $(get_env WEB_PASSWORD) ]]; then
    read -r -s -p "  Web login password (Enter = generate a strong one): " pw; echo
    if [[ -z $pw ]]; then pw=$(random_string 20); generated_pw=$pw; fi
    while (( ${#pw} < 12 )); do
      read -r -s -p "  At least 12 characters please: " pw; echo
    done
    set_env WEB_PASSWORD "$pw"
  else
    info "Web password already set (edit .env to change it)."
  fi
  local secret; secret=$(get_env SESSION_SECRET)
  if (( ${#secret} < 32 )); then set_env SESSION_SECRET "$(random_string 48)"; fi

  info "Telegram: open @BotFather, send /newbot, and copy the token it gives you."
  read -r -p "  Set up Telegram now? [Y/n] " yn
  local telegram=0
  if [[ ! $yn =~ ^[Nn] ]]; then ask TELEGRAM_BOT_TOKEN "Bot token" "" secret; telegram=1; fi

  bold "Building the app (first time takes a few minutes)…"
  compose build agent

  bold "Testing the connections…"
  if [[ $telegram -eq 1 ]]; then
    info "Now send any message to your bot in Telegram (and add it to the board's group, then post"
    info "a message there) so the check can show the chat ids."
    read -r -p "  Press Enter when done… " _
  fi
  compose run --rm --no-deps agent python -m app check || {
    warn "Some checks failed. Fix them (re-run ./setup.sh to change values) and run again."; exit 1; }

  if [[ $telegram -eq 1 ]]; then
    info "Copy the chat ids from the list above (groups are negative numbers)."
    ask TELEGRAM_ALLOWED_CHAT_IDS "Chat ids allowed to use the bot (comma separated)"
    read -r -p "  Chat ids that receive the weekly report [same as above]: " notify
    set_env TELEGRAM_NOTIFY_CHAT_IDS "${notify:-$(get_env TELEGRAM_ALLOWED_CHAT_IDS)}"
  fi

  if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    info "Firewall (ufw) is active; opening ports 80 and 443 for HTTPS."
    if [[ $EUID -eq 0 ]]; then ufw allow 80,443/tcp; else sudo ufw allow 80,443/tcp; fi
  fi

  configure_proxy

  bold "Starting…"
  compose up -d --remove-orphans
  if [[ $(get_env PROXY_MODE) == shared ]]; then reload_shared_caddy; fi
  for _ in $(seq 1 30); do
    if compose exec -T agent python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
      break
    fi
    sleep 2
  done

  bold "Done"
  info "Dashboard:  $(get_env PUBLIC_BASE_URL)   (HTTPS certificate is issued on the first visit)"
  info "Username:   $(get_env WEB_USERNAME)"
  if [[ -n $generated_pw ]]; then info "Password:   $generated_pw   <- save this in your password manager now"; fi
  info "First step: open the dashboard and click 'Check mailbox now'."
  info "Logs:       docker compose logs -f agent"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
