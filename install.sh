#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# One-command installer and launcher for Linux and macOS. Run ./install.sh --help.
# User-space only: no sudo, nothing outside this directory (tools go to .tools/, venv to .venv/).
set -euo pipefail

# ---- pinned versions (update together with the checksums below) -------------------------------
NODE_VERSION="22.23.4"      # Node 22 LTS; SHA-256 taken from the SHASUMS256.txt of the same release
UV_VERSION="0.13.6"         # uv release; checksums are pinned here (published as .sha256 assets)
UV_SHA_x86_64_unknown_linux_gnu="f29c3e94ffabd7e6f3ba521dba169a9b7ec12100bf3257087f0f24f6123f3645"
UV_SHA_aarch64_unknown_linux_gnu="229e194255c7958d86d56e8790d969a6f74736592133f0dfd0076f754c642c1d"
UV_SHA_x86_64_apple_darwin="63ba17fdda55ad1a230d4b37fc6017ffa10c23688c83818bd3bfdf914c652a02"
UV_SHA_aarch64_apple_darwin="60fbd5c8a1ed681845eea28d9d622fcde03c51e91a43465b64a1e17db1ed3472"
PY_MIN_MINOR=12             # pyproject requires-python >=3.12
PY_PREFERRED="3.14"         # same minor as the Dockerfile base image and CI
DEFAULT_PORT=8000
TOTAL=4

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
TOOLS="$ROOT/.tools"
LOG="$ROOT/install.log"
STAMP="$ROOT/.install-stamp"
PIDFILE="$ROOT/.server.pid"
VENV="$ROOT/.venv"

YES=0; NO_BROWSER=0; WITH_LLM=0; LLM_SMALL=""; SKIP_DATA=0; NO_START=0; REINSTALL=0; PORT="$DEFAULT_PORT"; PORT_GIVEN=0
STEP=0

usage() {
  cat <<EOF
Usage: ./install.sh [options]

Installs everything needed to run the site from a fresh clone (no sudo), then starts it on
127.0.0.1 and opens your browser. Safe to run again: it only redoes what changed.

Options:
  --yes, -y       do not ask questions (accept all downloads)
  --no-browser    do not open the browser
  --port N        preferred port (default $DEFAULT_PORT; a free one is picked if busy)
  --skip-data     skip the NAIF ephemeris kernels and the lunar terrain (otherwise mandatory)
  --with-llm      also download the local language model of RAVEN SI (llama.cpp + Ministral 3B, about 2.2 GB, Linux only)
  --with-llm-small  the same with a smaller model (Granite 1B, about 1 GB; for machines with under 4 GB of free memory)
  --no-start      install only, do not start the server
  --reinstall     discard .venv, the build stamps and the frontend build, then redo them
  --help, -h      show this help

Stop the server with ./stop.sh. Log: install.log
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    --with-llm) WITH_LLM=1 ;;
    --with-llm-small) WITH_LLM=1; LLM_SMALL="--small" ;;
    --skip-data) SKIP_DATA=1 ;;
    --no-start) NO_START=1 ;;
    --reinstall) REINSTALL=1 ;;
    --port)
      [ $# -ge 2 ] || { echo "ERROR: --port needs a number" >&2; exit 2; }
      PORT="$2"; PORT_GIVEN=1; shift ;;
    --port=*) PORT="${1#--port=}"; PORT_GIVEN=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done
case "$PORT" in
  ''|*[!0-9]*) echo "ERROR: --port must be a number between 1 and 65535" >&2; exit 2 ;;
esac
PORT="${PORT#"${PORT%%[!0]*}"}"
[ -n "$PORT" ] || PORT=0
[ "${#PORT}" -le 5 ] || { echo "ERROR: --port must be a number between 1 and 65535" >&2; exit 2; }
PORT=$((10#$PORT))
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "ERROR: --port must be a number between 1 and 65535" >&2; exit 2
fi

# ---- output helpers ---------------------------------------------------------------------------
{ echo; echo "=== install.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="; } >> "$LOG"
say() { printf '%s\n' "$*"; printf '%s\n' "$*" >> "$LOG"; }
note() { printf '      %s\n' "$*"; printf '      %s\n' "$*" >> "$LOG"; }
IS_TTY=0; [ -t 1 ] && IS_TTY=1
# A text bar: bar PERCENT [LABEL]. On a terminal it redraws one line; otherwise it prints a line every 10 %.
LAST_BAR=-1
bar() {
  local pct="$1" label="${2:-}" w=24 filled i out=""
  [ "$pct" -ge 0 ] 2>/dev/null || pct=0; [ "$pct" -le 100 ] || pct=100
  filled=$((pct * w / 100))
  for ((i = 0; i < w; i++)); do if [ "$i" -lt "$filled" ]; then out="$out#"; else out="$out-"; fi; done
  if [ "$IS_TTY" = 1 ]; then printf '\r      [%s] %3d%% %s\033[K' "$out" "$pct" "$label"
  elif [ $((pct / 10)) -ne "$LAST_BAR" ] || [ "$pct" -eq 100 ]; then LAST_BAR=$((pct / 10)); printf '      [%s] %3d%% %s\n' "$out" "$pct" "$label"; fi
}
bar_done() { [ "$IS_TTY" = 1 ] && printf '\r\033[K' || true; }
step() {
  STEP=$((STEP + 1)); say "[$STEP/$TOTAL] $*"
  LAST_BAR=-1; bar $(((STEP - 1) * 100 / TOTAL)) "overall: step $STEP of $TOTAL"
  [ "$IS_TTY" != 1 ] || printf '\n'
}
warn() { printf 'WARNING: %s\n' "$*" >&2; printf 'WARNING: %s\n' "$*" >> "$LOG"; }
die() {
  printf 'ERROR: %s\n' "$1" >&2; printf 'ERROR: %s\n' "$1" >> "$LOG"
  if [ -n "${2:-}" ]; then printf 'Fix: %s\n' "$2" >&2; printf 'Fix: %s\n' "$2" >> "$LOG"; fi
  echo "Details: $LOG" >&2
  exit 1
}

# Run a command with its output going to the log; on failure show the tail of the log.
run_logged() {
  local what="$1"; shift
  printf '$ %s\n' "$*" >> "$LOG"
  local rc=0 start=$SECONDS spin='|/-\' n=0 last=0
  "$@" >> "$LOG" 2>&1 &
  local pid=$!
  # a heartbeat, so that a slow step never looks like a frozen one
  while kill -0 "$pid" 2>/dev/null; do
    local el=$((SECONDS - start))
    if [ "$IS_TTY" = 1 ]; then
      printf '\r      %s %s... %dm%02ds%s\033[K' "${spin:$((n % 4)):1}" "$what" $((el / 60)) $((el % 60)) "$(jobs_summary)"; n=$((n + 1))
    elif [ $((el - last)) -ge 30 ]; then
      printf '      still working: %s (%ds)\n' "$what" "$el"; last=$el
    fi
    sleep 0.25
  done
  wait "$pid" || rc=$?
  bar_done
  if [ "$rc" -ne 0 ]; then
    tail -n 15 "$LOG" >&2
    die "$what failed." "read the lines above (full log: $LOG), fix the cause and run ./install.sh again."
  fi
}

# Run a command that prints "PROGRESS done total" lines (the data downloads): draws a bar, sends everything else to the log.
# Returns the command's status.
run_progress() {
  local what="$1"; shift
  printf '$ %s\n' "$*" >> "$LOG"
  LAST_BAR=-1
  "$@" 2>&1 | while IFS= read -r line; do
    case "$line" in
      PROGRESS\ *) set -- $line; if [ "${3:-0}" -gt 0 ] 2>/dev/null; then bar $(($2 * 100 / $3)) "$what $2/$3"; fi ;;
      *) printf '%s\n' "$line" >> "$LOG" ;;
    esac
  done
  local rc="${PIPESTATUS[0]}"
  bar_done
  return "$rc"
}

# confirm "question": returns 0 on yes. With --yes always yes. Without a terminal: no.
confirm() {
  [ "$YES" = 1 ] && return 0
  if [ ! -t 0 ]; then
    warn "no terminal to ask: $1 (re-run with --yes to accept)"
    return 1
  fi
  local ans
  printf '      %s [y/N] ' "$1"
  read -r ans || ans=n
  case "$ans" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

have() { command -v "$1" > /dev/null 2>&1; }

server_owned() {
  local pid="$1" port="$2" cmd
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  [ "$pid" -gt 1 ] 2>/dev/null || return 1
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [ "$cmd" = "$VENV/bin/python -m uvicorn --factory backend.bootstrap:build_app --host 127.0.0.1 --port $port" ]
}

sha256_file() {
  if have sha256sum; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}
sha256_stdin() {
  if have sha256sum; then sha256sum | cut -d' ' -f1; else shasum -a 256 | cut -d' ' -f1; fi
}
hash_files() { cat "$@" | sha256_stdin; }

download() { # url dest
  printf 'download %s\n' "$1" >> "$LOG"
  if have curl; then
    curl -fL --retry 3 --connect-timeout 20 -sS -o "$2" "$1" 2>> "$LOG" \
      || die "download failed: $1" "check your network/proxy and run ./install.sh again."
  elif have wget; then
    wget -q -O "$2" "$1" 2>> "$LOG" \
      || die "download failed: $1" "check your network/proxy and run ./install.sh again."
  else
    die "neither curl nor wget is installed." "install one of them with your package manager (e.g. 'sudo apt install curl') and run ./install.sh again."
  fi
}

stamp_get() { [ -f "$STAMP" ] && sed -n "s/^$1=//p" "$STAMP" | head -n 1 || true; }
# Several background jobs write stamps: a directory is the lock (mkdir is atomic everywhere; no flock needed).
stamp_set() {
  local tmp="$STAMP.tmp.$$" i=0
  while ! mkdir "$STAMP.lock" 2> /dev/null; do i=$((i + 1)); [ "$i" -le 200 ] || break; sleep 0.05; done
  { [ -f "$STAMP" ] && grep -v "^$1=" "$STAMP" || true; echo "$1=$2"; } > "$tmp"
  mv "$tmp" "$STAMP"
  rmdir "$STAMP.lock" 2> /dev/null || true
}
rmdir "$STAMP.lock" 2> /dev/null || true


# ---- background jobs (everything slow and independent runs at the same time) -----------------
JOBDIR="$TOOLS/jobs"
JOB_NAMES=()
# job_start NAME FUNCTION: runs FUNCTION in the background with its output in $JOBDIR/NAME.log and its status in NAME.rc.
job_start() {
  local name="$1"; shift
  mkdir -p "$JOBDIR"; rm -f "$JOBDIR/$name.rc" "$JOBDIR/$name.log"
  ( set +e; ( set -e; IS_TTY=0; "$@" ) > "$JOBDIR/$name.log" 2>&1; echo $? > "$JOBDIR/$name.rc" ) &
  JOB_NAMES+=("$name")
}
job_status() { # NAME -> done | FAILED | NN% | working
  local n="$1" rc p
  if [ -f "$JOBDIR/$n.rc" ]; then
    rc="$(cat "$JOBDIR/$n.rc")"; if [ "$rc" = 0 ]; then echo done; else echo FAILED; fi
  else
    p="$(grep '^PROGRESS ' "$JOBDIR/$n.log" 2> /dev/null | tail -n 1 || true)"
    if [ -n "$p" ]; then set -- $p; if [ "${3:-0}" -gt 0 ] 2> /dev/null; then echo "$(($2 * 100 / $3))%"; else echo working; fi; else echo working; fi
  fi
}
jobs_summary() {
  local n out=""
  [ "${#JOB_NAMES[@]}" -gt 0 ] || return 0
  for n in "${JOB_NAMES[@]}"; do out="$out | $n: $(job_status "$n")"; done
  printf '%s' "$out"
}
# jobs_wait: waits for every job, showing one live line (a line every 10 s without a terminal); then merges the job logs into the log.
jobs_wait() {
  local n pending last=$SECONDS first=1
  [ "${#JOB_NAMES[@]}" -gt 0 ] || return 0
  while :; do
    pending=0
    for n in "${JOB_NAMES[@]}"; do [ -f "$JOBDIR/$n.rc" ] || pending=1; done
    if [ "$IS_TTY" = 1 ]; then printf '\r      working%s\033[K' "$(jobs_summary)"
    elif [ "$first" = 1 ] || [ $((SECONDS - last)) -ge 10 ]; then printf '      working%s\n' "$(jobs_summary)"; last=$SECONDS; first=0; fi
    [ "$pending" = 0 ] && break
    sleep 0.5
  done
  bar_done
  for n in "${JOB_NAMES[@]}"; do
    { printf '=== job %s ===\n' "$n"; grep -v '^PROGRESS ' "$JOBDIR/$n.log" 2> /dev/null || true; } >> "$LOG"
  done
}
job_failed() { # NAME -> 0 if it failed; shows the tail of its log
  local n="$1"
  [ "$(cat "$JOBDIR/$n.rc" 2> /dev/null || echo 1)" = 0 ] && return 1
  grep -v '^PROGRESS ' "$JOBDIR/$n.log" 2> /dev/null | tail -n 15 >&2 || true
  return 0
}

# A fresh scratch directory inside .tools for downloads (removed on exit).
SCRATCH=""
cleanup() { [ -n "$SCRATCH" ] && rm -rf "$SCRATCH"; return 0; }
trap cleanup EXIT
new_scratch() { mkdir -p "$TOOLS"; SCRATCH="$(mktemp -d "$TOOLS/tmp.XXXXXX")"; }

# ---- 1. platform and base tools ---------------------------------------------------------------
step "Checking this machine"
OS="$(uname -s)"; ARCH="$(uname -m)"
case "$OS-$ARCH" in
  Linux-x86_64)  NODE_PLAT="linux-x64";    NODE_EXT="tar.xz"; UV_TRIPLE="x86_64-unknown-linux-gnu" ;;
  Linux-aarch64|Linux-arm64) NODE_PLAT="linux-arm64"; NODE_EXT="tar.xz"; UV_TRIPLE="aarch64-unknown-linux-gnu" ;;
  Darwin-x86_64) NODE_PLAT="darwin-x64";   NODE_EXT="tar.gz"; UV_TRIPLE="x86_64-apple-darwin" ;;
  Darwin-arm64)  NODE_PLAT="darwin-arm64"; NODE_EXT="tar.gz"; UV_TRIPLE="aarch64-apple-darwin" ;;
  *) die "unsupported platform: $OS $ARCH." "use Docker (see README) or a Linux/macOS machine on x86_64/arm64; on Windows use install.ps1." ;;
esac
if [ "$OS" = Linux ] && have ldd && ldd --version 2>&1 | grep -qi musl; then
  die "musl-based Linux (e.g. Alpine) is not supported by the downloaded tools." "use the Docker image (see README)."
fi
have tar || die "tar is not installed." "install it with your package manager and run ./install.sh again."
if [ "$NODE_EXT" = tar.xz ] && ! have xz; then
  have node || die "xz is not installed (needed to unpack Node.js)." "install it (e.g. 'sudo apt install xz-utils') or install Node.js 22+ yourself, then run ./install.sh again."
fi
have sha256sum || have shasum || die "no SHA-256 tool (sha256sum or shasum) found." "install coreutils/perl and run ./install.sh again."
[ -f "$ROOT/pyproject.toml" ] && [ -d "$ROOT/frontend" ] || die "run this script from a full clone of the repository." "git clone the project again."
note "$OS $ARCH, project directory: $ROOT"
note "full log: $LOG"

if [ "$REINSTALL" = 1 ]; then
  [ ! -f "$PIDFILE" ] || run_logged "stopping the previous server" bash "$ROOT/stop.sh"
  note "--reinstall: removing .venv, stamps and the frontend build"
  rm -rf "$VENV" "$STAMP" "$ROOT/frontend/dist"
fi

step "Installing everything in parallel"
# ---- 2. install everything in parallel ---------------------------------------------------------
# Order of work: the frontend (Node.js, npm ci, build) and the C plugins start at once in the background; in the foreground uv,
# Python, numpy+scipy; as soon as those are in, the data downloads (kernels, terrain of all sites, horizon masks) start in the
# background while the rest of the Python packages install. Then the script waits for all of them.
VPY="$VENV/bin/python"
# Server-side PDF of the report (extra `pdf`, WeasyPrint): needs Pango/HarfBuzz shared libraries from the
# system. They are detected, never installed (no sudo): without them the extra is skipped and the report
# page falls back to the browser print dialog.
pango_ok() {
  if have ldconfig && ldconfig -p 2> /dev/null | grep -q 'libpango-1.0.so.0' && ldconfig -p 2> /dev/null | grep -q 'libpangoft2-1.0.so.0'; then return 0; fi
  for d in /usr/lib /usr/lib64 /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu /usr/local/lib /lib/x86_64-linux-gnu; do
    [ -e "$d/libpango-1.0.so.0" ] && [ -e "$d/libpangoft2-1.0.so.0" ] && return 0
  done
  return 1
}
EXTRAS="fusion,sky"
if pango_ok; then
  EXTRAS="fusion,sky,pdf"
else
  warn "Pango libraries not found: the server-side PDF of the report (extra 'pdf') is skipped; the report falls back to the browser print dialog. To enable it install Pango (Fedora: 'sudo dnf install pango'; Debian/Ubuntu: 'sudo apt install libpango-1.0-0 libpangoft2-1.0-0'; Arch: 'sudo pacman -S pango') and run ./install.sh again."
fi
compute_pyhash() { { hash_files pyproject.toml constraints/base.txt; echo "$EXTRAS"; "$VPY" -V; echo "$UV_VERSION"; } 2>&1 | sha256_stdin; }
FEHASH="$( { hash_files frontend/package-lock.json frontend/package.json frontend/vite.config.ts frontend/tsconfig.json; \
  find frontend/src frontend/public frontend/index.html -type f -print0 2> /dev/null | LC_ALL=C sort -z | xargs -0 cat; \
  echo "node-22"; } | sha256_stdin)"
CHASH=""
if have make && have gcc; then
  CHASH="$(hash_files backend/plugins/fspl_c/fspl.c backend/plugins/servo_ctrl_c/*.c backend/plugins/servo_ctrl_c/*.h contracts/hal/* Makefile | sha256_stdin)"
fi
node_ensure() {
node_ok() { # dir containing node and npm (or empty for PATH)
  local n="${1:+$1/}node" major
  have "$n" || [ -x "$n" ] || return 1
  major="$("$n" -p 'process.versions.node.split(".")[0]' 2> /dev/null)" || return 1
  [ "$major" -ge 22 ] 2> /dev/null || return 1
  if [ -n "$1" ]; then [ -x "$1/npm" ] || return 1; else have npm || return 1; fi
}
NODE_DIR="$TOOLS/node-v$NODE_VERSION-$NODE_PLAT"
if node_ok ""; then
  note "using Node.js $(node -v) already on PATH"
elif node_ok "$NODE_DIR/bin"; then
  note "using project-local Node.js v$NODE_VERSION (.tools)"
  export PATH="$NODE_DIR/bin:$PATH"
else
  note "Node.js 22+ not found. Will download Node.js v$NODE_VERSION from nodejs.org (about 30 MB, SHA-256 verified) into .tools/."
  confirm "Download Node.js now?" || die "Node.js is required to build the site." "install Node.js 22+ yourself or re-run with --yes."
  new_scratch
  base="https://nodejs.org/dist/v$NODE_VERSION"
  file="node-v$NODE_VERSION-$NODE_PLAT.$NODE_EXT"
  download "$base/SHASUMS256.txt" "$SCRATCH/SHASUMS256.txt"
  download "$base/$file" "$SCRATCH/$file"
  want="$(awk -v f="$file" '$2 == f {print $1}' "$SCRATCH/SHASUMS256.txt")"
  [ -n "$want" ] || die "checksum for $file not found in SHASUMS256.txt." "report this; do not continue with an unverified download."
  got="$(sha256_file "$SCRATCH/$file")"
  [ "$want" = "$got" ] || die "SHA-256 mismatch for $file (expected $want, got $got)." "check your network/proxy and run ./install.sh again; the file was discarded."
  note "SHA-256 verified"
  mkdir -p "$SCRATCH/x"
  tar -xf "$SCRATCH/$file" -C "$SCRATCH/x" || die "could not unpack $file." "make sure 'xz' is installed and run ./install.sh again."
  rm -rf "$NODE_DIR"
  mv "$SCRATCH/x/node-v$NODE_VERSION-$NODE_PLAT" "$NODE_DIR"
  export PATH="$NODE_DIR/bin:$PATH"
  node_ok "" || die "the downloaded Node.js does not run on this machine." "install Node.js 22+ yourself and run ./install.sh again."
  note "installed Node.js $(node -v) in .tools/"
  rm -rf "$SCRATCH"
fi
}
frontend_job() {
  export npm_config_cache="$TOOLS/npm-cache" npm_config_update_notifier=false npm_config_fund=false npm_config_audit=false
if [ "$(stamp_get fe)" = "$FEHASH" ] && [ -f "$ROOT/frontend/dist/index.html" ]; then
  note "up to date"
  return 0
else
  node_ensure
  note "installing npm packages (about 200 MB in frontend/node_modules; e2e tooling is NOT installed)"
  confirm "Install the npm packages and build the site now?" || die "the site cannot be built without them." "re-run with --yes."
  run_logged "npm ci" npm --prefix "$ROOT/frontend" ci
  run_logged "npm run build" npm --prefix "$ROOT/frontend" run build
  [ -f "$ROOT/frontend/dist/index.html" ] || die "the build finished but frontend/dist/index.html is missing." "see $LOG."
  stamp_set fe "$FEHASH"
fi
}
cplugins_job() {
C_AVAILABLE=0
if have make && have gcc; then
  if [ "$(stamp_get c)" = "$CHASH" ] && [ -x backend/plugins/fspl_c/bin/fspl ] && [ -x backend/plugins/servo_ctrl_c/bin/servo_ctrl ]; then
    note "up to date"; C_AVAILABLE=1
  elif make build-c >> "$LOG" 2>&1; then
    stamp_set c "$CHASH"; C_AVAILABLE=1; note "compiled"
  else
    warn "the C plugins failed to compile (see $LOG). The site still works; the C plugins will be reported as unavailable."
  fi
else
  warn "no C compiler/make found (need 'gcc' and 'make'): the C plugins (fspl, servo_ctrl) will be reported as unavailable. The rest of the site works. To enable them install a compiler (Linux: 'sudo apt install build-essential'; macOS: 'xcode-select --install') and run ./install.sh again."
fi
printf '%s\n' "$C_AVAILABLE" > "$JOBDIR/cplugins.avail"
}
kernels_job() {
  local lock; lock="$(hash_files backend/ephemeris/kernels.lock.json | cut -c1-16)"
  if [ "$(stamp_get eph)" = "$lock" ] && "$VPY" -m backend.ephemeris.fetch --check; then
    note "ephemeris kernels: up to date"; return 0
  fi
  note "ephemeris kernels: about 45 MB from naif.jpl.nasa.gov (SHA-256 verified, in parallel) into build/ephemeris"
  "$VPY" -m backend.ephemeris.fetch || die "could not fetch the ephemeris kernels (offline?)." "check your network and run ./install.sh again (finished files are kept)."
  stamp_set eph "$lock"; note "ephemeris kernels: done"
}
terrain_job() {
  local key
  key="$(hash_files backend/domain/grazing/prefetch.py | cut -c1-16)"
  if [ "$(stamp_get lola)" != "$key" ]; then
    note "LOLA tiles of the default sites: about 41 MB (20 m tiles to 10 km, 240 m tiles to 200 km) from the NASA PDS into build/lola"
    "$VPY" -m backend.domain.grazing.prefetch --jobs 24 || die "could not fetch the LOLA tiles (offline?)." "check your network and run ./install.sh again (finished tiles are kept)."
    stamp_set lola "$key"
  fi
  key="$(hash_files backend/domain/raven/prefetch_global.py backend/domain/grazing/prefetch.py | cut -c1-16)"
  if [ "$(stamp_get lola_all)" != "$key" ]; then
    note "terrain of ALL 51 catalogue sites: about 250 MB from the NASA PDS (24 requests at a time), then the horizon masks on every core"
    "$VPY" -m backend.domain.raven.prefetch_global --jobs 24 || die "could not fetch the terrain of the catalogue sites (offline?)." "check your network and run ./install.sh again (finished tiles are kept)."
    stamp_set lola_all "$key"
  fi
  note "terrain: done"
}
DATA_STARTED=0
start_data_jobs() {
  [ "$DATA_STARTED" = 1 ] && return 0
  DATA_STARTED=1
  if [ "$SKIP_DATA" = 1 ]; then note "data skipped (--skip-data): sky/ephemeris pages and the terrain of most sites will report 'unavailable'"; return 0; fi
  [ -d backend/domain/grazing ] || return 0
  job_start kernels kernels_job
  job_start terrain terrain_job
}

# one question for everything, unless every stamp says it is already installed
fresh=1
if [ -x "$VPY" ]; then [ "$(stamp_get py)" = "$(compute_pyhash)" ] || fresh=0; else fresh=0; fi
[ "$(stamp_get fe)" = "$FEHASH" ] && [ -f "$ROOT/frontend/dist/index.html" ] || fresh=0
if [ "$SKIP_DATA" != 1 ]; then
  [ "$(stamp_get eph)" = "$(hash_files backend/ephemeris/kernels.lock.json | cut -c1-16)" ] || fresh=0
  [ "$(stamp_get lola)" = "$(hash_files backend/domain/grazing/prefetch.py | cut -c1-16)" ] || fresh=0
  [ "$(stamp_get lola_all)" = "$(hash_files backend/domain/raven/prefetch_global.py backend/domain/grazing/prefetch.py | cut -c1-16)" ] || fresh=0
fi
if [ "$fresh" = 0 ] && [ "$YES" != 1 ]; then
  note "this installs the tools it needs (Node.js, uv, Python: only what is missing) and downloads, all at the same time:"
  note "  npm packages about 200 MB, Python packages about 150 MB, ephemeris kernels about 45 MB (NASA NAIF),"
  note "  lunar terrain of all 51 catalogue sites about 290 MB (NASA PDS); everything stays inside this directory"
  confirm "Install and download everything now?" || die "nothing was installed." "re-run with --yes to accept all downloads."
fi
[ "$fresh" = 1 ] || YES=1
job_start frontend frontend_job
job_start cplugins cplugins_job

UV_DIR="$TOOLS/uv-$UV_VERSION-$UV_TRIPLE"
UV="$UV_DIR/uv"
export UV_CACHE_DIR="$TOOLS/uv-cache" UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_PYTHON_DOWNLOADS=manual
export UV_NO_CONFIG=1 UV_NO_PROGRESS=1
if [ ! -x "$UV" ]; then
  note "uv $UV_VERSION is not installed. Will download it from its official release (about 20 MB, pinned SHA-256) into .tools/."
  confirm "Download uv now?" || die "uv is required to create the Python environment." "re-run with --yes."
  new_scratch
  file="uv-$UV_TRIPLE.tar.gz"
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$file"
  download "$url" "$SCRATCH/$file"
  case "$UV_TRIPLE" in
    x86_64-unknown-linux-gnu) want="$UV_SHA_x86_64_unknown_linux_gnu" ;;
    aarch64-unknown-linux-gnu) want="$UV_SHA_aarch64_unknown_linux_gnu" ;;
    x86_64-apple-darwin) want="$UV_SHA_x86_64_apple_darwin" ;;
    aarch64-apple-darwin) want="$UV_SHA_aarch64_apple_darwin" ;;
  esac
  got="$(sha256_file "$SCRATCH/$file")"
  [ "$want" = "$got" ] || die "SHA-256 mismatch for $file (expected $want, got $got)." "check your network/proxy and run ./install.sh again; the file was discarded."
  note "SHA-256 verified"
  mkdir -p "$SCRATCH/x"
  tar -xzf "$SCRATCH/$file" -C "$SCRATCH/x" || die "could not unpack $file." "run ./install.sh again."
  rm -rf "$UV_DIR"
  mv "$SCRATCH/x/uv-$UV_TRIPLE" "$UV_DIR"
fi

py_ok() { "$1" -I -c "import sys,venv; sys.exit(0 if sys.version_info >= (3, $PY_MIN_MINOR) else 1)" > /dev/null 2>&1; }
PYSRC=""
for cand in python3.14 python3.13 python3.12 python3 python; do
  if have "$cand"; then
    p="$(command -v "$cand")"
    if py_ok "$p"; then PYSRC="$p"; break; fi
  fi
done
if [ -x "$VENV/bin/python" ] && py_ok "$VENV/bin/python"; then
  note "reusing the existing .venv ($("$VENV/bin/python" -V 2>&1))"
elif [ -n "$PYSRC" ]; then
  note "using $("$PYSRC" -V 2>&1) found at $PYSRC"
  rm -rf "$VENV"
  run_logged "creating the virtual environment" "$UV" venv --python "$PYSRC" "$VENV"
else
  note "no Python 3.$PY_MIN_MINOR+ found. Will let uv download CPython $PY_PREFERRED (about 35 MB, checksum verified by uv) into .tools/python."
  confirm "Download Python $PY_PREFERRED now?" || die "Python is required." "install Python 3.$PY_MIN_MINOR+ yourself or re-run with --yes."
  run_logged "installing Python $PY_PREFERRED" "$UV" python install "$PY_PREFERRED"
  rm -rf "$VENV"
  run_logged "creating the virtual environment" "$UV" venv --python "$PY_PREFERRED" "$VENV"
fi
VPY="$VENV/bin/python"

PYHASH="$(compute_pyhash)"
if [ "$(stamp_get py)" = "$PYHASH" ]; then
  note "up to date"
else
  note "installing packages from PyPI (numpy, scipy, skyfield, FastAPI, ...; roughly 150 MB)"
  confirm "Install the Python packages now?" || die "the backend cannot run without its packages." "re-run with --yes."
  # numpy and scipy first (a few seconds): the data downloads need nothing else, so they start now and run during the big install
  run_logged "installing numpy and scipy" "$UV" pip install --python "$VPY" -c constraints/base.txt numpy scipy
  start_data_jobs
  run_logged "installing the Python packages" "$UV" pip install --python "$VPY" -c constraints/base.txt -e ".[$EXTRAS]"
  stamp_set py "$PYHASH"
fi
start_data_jobs
llm_job() {
  "$VPY" -I "$ROOT/scripts/install_local_llm.py" $LLM_SMALL
}
[ "$WITH_LLM" = 1 ] && job_start llm llm_job


# ---- wait for the background jobs and check them ----------------------------------------------
jobs_wait
for n in "${JOB_NAMES[@]}"; do
  if job_failed "$n"; then
    case "$n" in
      llm) warn "the local model could not be installed (see above). RAVEN SI keeps working with the rules and any configured model service." ;;
      cplugins) warn "the C plugins failed to compile (see $LOG). The site still works; they will be reported as unavailable." ;;
      *) die "the $n step failed (details above)." "fix the cause shown above and run ./install.sh again; finished work is kept." ;;
    esac
  fi
done
C_AVAILABLE=0
[ -f "$JOBDIR/cplugins.avail" ] && C_AVAILABLE="$(cat "$JOBDIR/cplugins.avail")"
[ -f "$ROOT/frontend/dist/index.html" ] || die "the build finished but frontend/dist/index.html is missing." "see $LOG."
for n in "${JOB_NAMES[@]}"; do sed -n 's/^      //p' "$JOBDIR/$n.log" 2> /dev/null | while IFS= read -r l; do printf '      %s: %s\n' "$n" "$l"; done; done

# ---- 8. start the server ----------------------------------------------------------------------
health_ok() { # port
  if have curl; then curl -fsS -m 2 "http://127.0.0.1:$1/health" > /dev/null 2>&1
  else "$VPY" -I -c "import urllib.request as u,sys; u.urlopen('http://127.0.0.1:$1/health', timeout=2)" > /dev/null 2>&1; fi
}
port_free() {
  "$VPY" -I -c "import socket,sys
s=socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(('127.0.0.1', int(sys.argv[1])))
except OSError:
    sys.exit(1)" "$1" > /dev/null 2>&1
}

if [ "$NO_START" = 1 ]; then
  step "Start the server: skipped (--no-start)"
  step "Open the browser: skipped (--no-start)"
  say "Installed. Start later with: ./install.sh   (stop with ./stop.sh)"
  exit 0
fi

step "Starting the server (127.0.0.1 only)"
SERVERHASH="$( {
  printf '%s\n' "$PYHASH" "$FEHASH" "$CHASH"
  find backend contracts -type f \( -name '*.py' -o -name '*.toml' -o -name '*.json' -o -name '*.md' \) \
    -print0 | LC_ALL=C sort -z | xargs -0 cat
} | sha256_stdin)"
URL=""
if [ -f "$PIDFILE" ]; then
  old_pid="$(sed -n 1p "$PIDFILE")"; old_port="$(sed -n 2p "$PIDFILE")"; old_hash="$(sed -n 3p "$PIDFILE")"
  case "$old_pid" in ''|*[!0-9]*) die "invalid server PID record." "check .server.pid before removing it." ;; esac
  [ "$old_pid" -gt 1 ] || die "invalid server PID record." "check .server.pid before removing it."
  if kill -0 "$old_pid" 2> /dev/null; then
    server_owned "$old_pid" "$old_port" || die "the recorded PID is not this project's server." "do not stop that process; check the stale .server.pid."
    if [ "$old_hash" != "$SERVERHASH" ]; then
      note "project changed: restarting the previous server"
      run_logged "stopping the previous server" bash "$ROOT/stop.sh"
      [ "$PORT_GIVEN" = 1 ] || PORT="$old_port"
    elif health_ok "$old_port"; then
      URL="http://127.0.0.1:$old_port/"
      note "server already running (pid $old_pid), reusing it"
    else
      die "the recorded server is running but unhealthy." "run ./stop.sh, check build/server.log and retry."
    fi
  else
    rm -f "$PIDFILE"
  fi
fi
if [ -z "$URL" ]; then
  chosen=""
  cand="$PORT"
  for _ in $(seq 1 50); do
    [ "$cand" -le 65535 ] || break
    if port_free "$cand"; then chosen="$cand"; break; fi
    [ "$PORT_GIVEN" = 1 ] && [ "$cand" = "$PORT" ] && warn "port $cand is busy, picking another"
    cand=$((cand + 1))
  done
  [ -n "$chosen" ] || die "no free port found from $PORT to $((PORT + 49))." "free a port or pass --port N."
  [ "$chosen" = "$PORT" ] || note "port $PORT is busy, using $chosen"
  mkdir -p "$ROOT/build"
  csv=""
  [ -f "$ROOT/demo/telemetry_demo.csv" ] && csv="$ROOT/demo/telemetry_demo.csv"
  (
    export STATIC_DIR="$ROOT/frontend/dist"
    [ -n "$csv" ] && export TELEMETRY_CSV="$csv"
    if have setsid; then
      setsid nohup "$VPY" -m uvicorn --factory backend.bootstrap:build_app --host 127.0.0.1 --port "$chosen" \
        > "$ROOT/build/server.log" 2>&1 < /dev/null &
    else
      nohup "$VPY" -m uvicorn --factory backend.bootstrap:build_app --host 127.0.0.1 --port "$chosen" \
        > "$ROOT/build/server.log" 2>&1 < /dev/null &
    fi
    printf '%s\n%s\n%s\n' "$!" "$chosen" "$SERVERHASH" > "$PIDFILE"
  )
  new_pid="$(sed -n 1p "$PIDFILE")"
  ok=0
  for _ in $(seq 1 60); do
    if health_ok "$chosen"; then ok=1; break; fi
    kill -0 "$new_pid" 2> /dev/null || break
    sleep 1
  done
  if [ "$ok" != 1 ]; then
    tail -n 15 "$ROOT/build/server.log" >&2 || true
    kill "$new_pid" 2> /dev/null || true
    rm -f "$PIDFILE"
    die "the server did not answer on /health." "see build/server.log (shown above) and $LOG."
  fi
  URL="http://127.0.0.1:$chosen/"
  note "server started (pid $new_pid), log: build/server.log"
fi

# ---- 9. open the browser ----------------------------------------------------------------------
step "Opening the site"
say ""
say "Ready: $URL"
[ "$C_AVAILABLE" = 1 ] || say "Note: C plugins unavailable (no compiler), see the warning above."
say "Stop the server with: ./stop.sh"
if [ "$NO_BROWSER" = 1 ]; then
  note "--no-browser: not opening a browser"
elif have xdg-open; then
  (xdg-open "$URL" > /dev/null 2>&1 &) || note "could not launch a browser; open $URL yourself"
elif have open; then
  open "$URL" > /dev/null 2>&1 || note "could not launch a browser; open $URL yourself"
else
  note "no browser launcher found; open $URL yourself"
fi
exit 0
