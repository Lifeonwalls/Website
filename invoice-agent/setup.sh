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

  bold "Starting…"
  compose up -d
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
