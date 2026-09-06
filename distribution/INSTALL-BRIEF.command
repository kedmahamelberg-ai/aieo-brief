#!/bin/bash
set -euo pipefail
package_dir="$(cd "$(dirname "$0")" && pwd -P)"
source_dir="$package_dir/Repository"
manifest="$package_dir/FILES-TO-INSTALL.tsv"
target_dir=''
settings_file=''
interactive=1
fail() { printf '\nInstallation stopped: %s\n' "$1" >&2; exit 1; }
[[ -d "$source_dir" && -f "$manifest" ]] || fail 'Keep this installer beside the Repository folder and FILES-TO-INSTALL.tsv in the unzipped download.'
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repository) [[ $# -ge 2 ]] || fail 'Missing repository folder.'; target_dir="$2"; interactive=0; shift 2 ;;
    --settings) [[ $# -ge 2 ]] || fail 'Missing settings file.'; settings_file="$2"; shift 2 ;;
    *) fail 'Usage: INSTALL-BRIEF.command [--repository FOLDER] [--settings JSON_FILE]' ;;
  esac
done
if [[ -z "$target_dir" ]]; then
  printf 'In GitHub Desktop, select aieo-brief and choose Repository > Show in Finder.\nSelect that existing aieo-brief folder in the next window.\n'
  target_dir="$(osascript -e 'POSIX path of (choose folder with prompt "Select your existing aieo-brief GitHub Desktop repository. This update is for the Brief.")')" || exit 1
fi
[[ -d "$target_dir" ]] || fail 'The selected folder does not exist.'
target_dir="$(cd "$target_dir" && pwd -P)"
[[ -e "$target_dir/.git" && -f "$target_dir/scripts/build_site.py" && -f "$target_dir/templates/base.html" ]] || fail 'Select the existing aieo-brief repository that GitHub Desktop cloned. It must contain scripts/build_site.py and templates/base.html.'
[[ ! -d "$target_dir/data/releases" ]] || fail 'This looks like the Observatory repository. Select the separate aieo-brief repository.'
case "$target_dir/" in "$package_dir/"*) fail 'Select the existing GitHub Desktop repository, outside this downloaded package.' ;; esac
remote="$(git -C "$target_dir" remote get-url origin 2>/dev/null || true)"
if [[ -n "$remote" ]]; then
  case "${remote%/}" in */aieo-brief|*/aieo-brief.git|*:aieo-brief|*:aieo-brief.git) ;;
    *) fail 'The selected repository points to a different GitHub project. Choose aieo-brief in GitHub Desktop.' ;;
  esac
fi
if [[ "$interactive" == 1 && -z "$settings_file" ]]; then
  choice="$(osascript -e 'button returned of (display dialog "Would you like to install a Brief-Settings.json file downloaded from the settings form? Existing website settings are preserved otherwise." buttons {"Cancel", "Use current settings", "Choose settings file"} default button "Use current settings" cancel button "Cancel")')" || exit 1
  if [[ "$choice" == 'Choose settings file' ]]; then
    settings_file="$(osascript -e 'POSIX path of (choose file with prompt "Choose Brief-Settings.json downloaded from CONFIGURE-THE-BRIEF.html" of type {"public.json"})')" || exit 1
  fi
fi
# Validate every packaged file and destination before copying anything.
file_count=0
while IFS=$'\t' read -r expected relative; do
  [[ -n "$expected" && -n "$relative" ]] || fail 'The installation file list is incomplete.'
  case "$relative" in /*|..|../*|*/../*|*/..|.git|.git/*) fail 'An unsafe destination was found in the installation list.' ;; esac
  [[ -f "$source_dir/$relative" && ! -L "$source_dir/$relative" ]] || fail "Missing installation file: $relative"
  actual="$(shasum -a 256 "$source_dir/$relative" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "A package file failed its checksum: $relative. Download and unzip the update again."
  candidate="$target_dir/$relative"
  [[ ! -d "$candidate" ]] || fail "A folder occupies a file destination: $relative"
  while [[ "$candidate" != "$target_dir" ]]; do
    [[ ! -L "$candidate" ]] || fail "The destination contains a symbolic link: $relative"
    candidate="$(dirname "$candidate")"
  done
  file_count=$((file_count+1))
done < "$manifest"
[[ "$file_count" -gt 10 ]] || fail 'The installation file list is incomplete.'
if [[ -n "$settings_file" ]]; then
  [[ -f "$settings_file" && ! -L "$settings_file" ]] || fail 'The selected settings file is missing or is a link.'
  command -v python3 >/dev/null || fail 'Python 3 is needed to validate the optional settings file. You can install the website files using current settings first.'
  # No network request. Validate with exactly the same rules as the site build.
  python3 - "$source_dir" "$settings_file" <<'PY'
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from brief_contract import load_config
for key in ('BRIEF_SITE_URL','SUPABASE_URL','SUPABASE_PUBLISHABLE_KEY','GA4_MEASUREMENT_ID','BRIEF_COMMUNITY_ENABLED'):
    os.environ.pop(key,None)
try:
    text=Path(sys.argv[2]).read_text()
    obj=json.loads(text)
    if not isinstance(obj,dict): raise ValueError('Settings must be a JSON object.')
    known=set(json.loads((Path(sys.argv[1])/'config/site.json').read_text()))
    if set(obj)-known: raise ValueError('Unexpected fields. Use the included settings form; never include server credentials.')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'config').mkdir();(root/'config/site.json').write_text(text)
        load_config(root)
except Exception as error:
    raise SystemExit('Settings were not installed: '+str(error))
print('Website settings validated. No server credentials or database changes are made by this installer.')
PY
fi
backup_parent="$(dirname "$target_dir")"
backup_dir="$(mktemp -d "$backup_parent/Brief-backup-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
count=0
while IFS=$'\t' read -r expected relative; do
  # Preserve the owner's settings on repeat installation unless a new file was selected.
  if [[ "$relative" == 'config/site.json' && -f "$target_dir/$relative" && -z "$settings_file" ]]; then
    continue
  fi
  if [[ -f "$target_dir/$relative" ]]; then
    mkdir -p "$backup_dir/$(dirname "$relative")"
    cp -p "$target_dir/$relative" "$backup_dir/$relative"
  else
    printf '%s\n' "$relative" >> "$backup_dir/NEW-FILES.txt"
  fi
  mkdir -p "$target_dir/$(dirname "$relative")"
  if [[ "$relative" == 'config/site.json' && -n "$settings_file" ]]; then
    expected="$(shasum -a 256 "$settings_file" | awk '{print $1}')"
    cp -p "$settings_file" "$target_dir/$relative"
  else
    cp -p "$source_dir/$relative" "$target_dir/$relative"
  fi
  actual="$(shasum -a 256 "$target_dir/$relative" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "Copy verification failed: $relative. Your backup is at $backup_dir"
  count=$((count+1))
done < "$manifest"
printf '\nInstalled and verified %s Brief files.\nBackup: %s\n\n' "$count" "$backup_dir"
printf 'Return to GitHub Desktop with aieo-brief selected.\nEnter Upgrade the Brief in Summary, click Commit to main, then Push origin.\n\n'
printf 'For your first installation, complete the one-time database and publishing steps\nin START-HERE.html or OWNER-SETUP.md. This installer has not changed the live website.\n'
