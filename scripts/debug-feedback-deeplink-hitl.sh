#!/usr/bin/env bash
# HITL repro for logged-out feedback deep-link redirect.
# Agent-runnable loop: user follows prompts; script prints KEY=VALUE for parsing.
#
# Usage:
#   bash scripts/debug-feedback-deeplink-hitl.sh
#
# Pass criterion (green): FINAL_PATH starts with /feedback/<case-id>
# Fail criterion (red):   FINAL_PATH is anything else (e.g. /chat, /dashboard, /login)

set -euo pipefail

CASE_ID="${CASE_ID:-a7b7c2df-a857-42fc-880c-a771328dc5a8}"
BASE_URL="${BASE_URL:-https://alochat.platform.confabs.org}"
FEEDBACK_URL="${BASE_URL}/feedback/${CASE_ID}"

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

step "Sign OUT of ${BASE_URL} (or use a private/incognito window with no alochat cookies)."

step "Paste this URL into the address bar and press Enter:
    ${FEEDBACK_URL}"

capture LANDED_ON_LOGIN "Did you land on the Login page with returnTo pointing at the feedback path? (y/n)"

capture LOGIN_URL "Paste the browser address bar URL after that redirect (or 'same'):"

step "Sign in as the user who owns that feedback case (siddalocgupta+1@gmail.com)."

capture FINAL_URL "After Sign In completes, paste the FULL final URL from the address bar:"

capture SAW_CASE "Do you see the feedback case content (not chat/dashboard)? (y/n)"

# Derive path for machine-checkable verdict
FINAL_PATH=$(printf '%s' "$FINAL_URL" | sed -E 's#https?://[^/]+##; s#[?#].*$##')
EXPECTED_PATH="/feedback/${CASE_ID}"

if [[ "$FINAL_PATH" == "$EXPECTED_PATH" && "$SAW_CASE" == "y" ]]; then
  VERDICT=green
else
  VERDICT=red
fi

printf '\n--- Captured ---\n'
printf 'FEEDBACK_URL=%s\n' "$FEEDBACK_URL"
printf 'LANDED_ON_LOGIN=%s\n' "$LANDED_ON_LOGIN"
printf 'LOGIN_URL=%s\n' "$LOGIN_URL"
printf 'FINAL_URL=%s\n' "$FINAL_URL"
printf 'FINAL_PATH=%s\n' "$FINAL_PATH"
printf 'EXPECTED_PATH=%s\n' "$EXPECTED_PATH"
printf 'SAW_CASE=%s\n' "$SAW_CASE"
printf 'VERDICT=%s\n' "$VERDICT"
