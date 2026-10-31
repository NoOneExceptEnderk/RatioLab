# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Nonprivileged macOS application replacement using fixed system tools."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from external_programs import child_environment, system_library_search
import update_receipt

TOOLS = ('/bin/sh', '/bin/ps', '/usr/bin/shasum', '/usr/bin/stat',
    '/usr/bin/hdiutil', '/usr/bin/ditto', '/usr/bin/codesign', '/usr/bin/lipo',
    '/usr/libexec/PlistBuddy', '/usr/bin/open', '/usr/bin/mktemp',
    '/bin/mkdir', '/bin/rmdir', '/bin/rm', '/bin/mv', '/bin/sleep', '/bin/cat')


def process_identity(pid):
    """Stable ps birth token; changing run/sleep state never signals exit.

    ps lstart has second precision. A reused PID with that same birth second
    conservatively delays replacement until exit/timeout; it cannot cause an
    installation while the original process still runs.
    """
    environment=child_environment() | {'LC_ALL':'C'}
    with system_library_search():
        result=subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart=','-o','state='],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=environment,timeout=5,encoding='ascii',check=True)
    fields=result.stdout.split()
    if len(fields)!=6 or fields[5].startswith(('Z','X')):
        raise ValueError('The RatioLab parent process is unavailable')
    return ' '.join(fields[:5])


def validate_source(installation):
    """Worker-only checks before asking the user to close the application."""
    if not all(os.access(tool,os.X_OK) for tool in TOOLS):
        raise RuntimeError('macOS update tools are unavailable. Use Download manually instead.')
    environment=child_environment()
    with tempfile.TemporaryDirectory(prefix='ratiolab-source-check-') as temporary:
        report=Path(temporary)/'version.txt'
        commands=(['/usr/bin/codesign','--verify','--deep','--strict','--verbose=2',str(installation.destination)],
                  ['/usr/bin/lipo','-archs',str(installation.executable)],
                  [str(installation.executable),'--version','--report',str(report)])
        with system_library_search():
            results=[subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,env=environment,timeout=60,encoding='utf-8',check=True)
                for command in commands]
        with open(report,'r',encoding='utf-8') as stream:version=stream.read(1025)
    if installation._target['machine'] not in results[1].stdout.split():
        raise ValueError('The running macOS application architecture does not match this installation')
    if len(version)>1024 or version.strip()!='RatioLab '+installation._target['current']:
        raise ValueError('The running macOS application version does not match its identity')


def _hash(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''):digest.update(chunk)
    return digest.hexdigest()


def script(job, installation, package, digest, pid, birth, timeout, target, restart):
    """Prepare data-only literals and a bounded, nonprivileged shell transaction."""
    bundle=installation.destination
    values=dict(job=job,package=package,digest=digest,destination=bundle,
        parent=bundle.parent,executable=installation.executable,pid=pid,birth=birth,
        count=max(1,int(timeout*10)),target=target,source=installation._target['current'],
        machine=installation._target['machine'],
        bundle_id=f'{bundle.stat().st_dev}:{bundle.stat().st_ino}',
        parent_id=f'{bundle.parent.stat().st_dev}:{bundle.parent.stat().st_ino}',
        source_executable_hash=_hash(installation.executable),
        source_info_hash=_hash(bundle/'Contents/Info.plist'),
        slot=Path(job).parent/update_receipt.receipt_name(installation.executable),
        restart='1' if restart else '0')
    prefix=['#!/bin/sh','set -eu','umask 077','LC_ALL=C; export LC_ALL']
    prefix += [f'{key}={shlex.quote(str(value))}' for key,value in values.items()]
    return '\n'.join(prefix)+r'''
cd "$job"
status=failed
stage=
backup=
mounted=0
old_moved=0
committed=0
new_id=
mountpoint=$job/mount
parent_token() {
  record=$(/bin/ps -p "$pid" -o lstart= -o state= 2>/dev/null) || return 0
  set -- $record
  [ "$#" = 6 ] || return 0
  case "$6" in Z*|X*) return 0 ;; esac
  printf '%s %s %s %s %s' "$1" "$2" "$3" "$4" "$5"
}
ordinary_path() {
  checked=$1
  while :; do
    [ ! -L "$checked" ] || return 1
    [ "$checked" != / ] || break
    checked=${checked%/*}
    [ -n "$checked" ] || checked=/
  done
}
validate_app() {
  checked_app=$1
  checked_version=$2
  probe=$3
  info=$checked_app/Contents/Info.plist
  binary=$checked_app/Contents/MacOS/RatioLab
  ordinary_path "$checked_app" && ordinary_path "$info" && ordinary_path "$binary" || return 21
  [ -d "$checked_app" ] && [ -f "$info" ] && [ -f "$binary" ] && [ -x "$binary" ] || return 21
  [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$info")" = local.solidcraft.reducers ] || return 21
  [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$info")" = RatioLab ] || return 21
  [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info")" = "$checked_version" ] || return 21
  architectures=$(/usr/bin/lipo -archs "$binary") || return 21
  case " $architectures " in *" $machine "*) ;; *) return 21 ;; esac
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$checked_app" || return 22
  if [ -n "$probe" ]; then
    /bin/rm -f "$job/runtime-version.txt" "$job/runtime-check.json"
    "$binary" --version --report "$job/runtime-version.txt" || return 23
    ordinary_path "$job/runtime-version.txt" && [ -f "$job/runtime-version.txt" ] || return 23
    [ "$(/usr/bin/stat -f '%z' "$job/runtime-version.txt")" -le 1024 ] || return 23
    [ "$(/bin/cat "$job/runtime-version.txt")" = "RatioLab $checked_version" ] || return 23
    "$binary" "--$probe" --report "$job/runtime-check.json" || return 23
  fi
}
require_app() {
  code=0
  validate_app "$@" || code=$?
  case "$code" in
    0) return 0 ;; 21) status=package-identity-mismatch ;;
    22) status=signature-invalid ;; *) status=runtime-invalid ;;
  esac
  return 1
}
finish() {
  trap - EXIT HUP INT TERM
  if [ "$committed" = 0 ] && [ "$old_moved" = 1 ]; then
    if [ -e "$destination" ] || [ -L "$destination" ]; then
      actual=$(/usr/bin/stat -f '%d:%i' "$destination" 2>/dev/null) || actual=
      if [ -n "$new_id" ] && [ "$actual" = "$new_id" ] && [ ! -L "$destination" ]; then
        /bin/rm -rf "$destination" || status=rollback-failed
      else
        status=rollback-failed
      fi
    fi
    if [ ! -e "$destination" ] && [ ! -L "$destination" ] && [ -d "$backup/RatioLab.app" ]; then
      if /bin/mv "$backup/RatioLab.app" "$destination"; then old_moved=0; else status=rollback-failed; fi
    fi
    if [ "$old_moved" = 1 ]; then
      printf 'Previous application retained in %s\n' "$backup" >> helper.log
    fi
  fi
  if [ -n "$stage" ] && [ -d "$stage" ] && [ ! -L "$stage" ]; then /bin/rm -rf "$stage" || true; fi
  if [ -n "$backup" ] && [ -d "$backup" ] && [ "$status" != rollback-failed ]; then /bin/rm -rf "$backup" || true; fi
  if [ "$mounted" = 1 ]; then
    if /usr/bin/hdiutil detach "$mountpoint"; then mounted=0; else printf '%s\n' 'The disk image could not be detached.' >> helper.log; fi
  fi
  if [ "$mounted" = 0 ]; then /bin/rmdir "$mountpoint" 2>/dev/null || true; fi
  printf '%s\n' "$status" > result
  if [ -e armed ] && [ -f receipt.pending ]; then /bin/mv -f receipt.pending "$slot"; fi
  if [ "$restart" = 1 ] && [ -e armed ] && [ "$(parent_token)" != "$birth" ]; then
    if [ "$committed" = 1 ]; then
      /usr/bin/open -n "$destination" || printf '%s\n' 'The updated application could not be opened.' >> helper.log
    elif [ "$status" != rollback-failed ] && validate_app "$destination" "$source" diagnose; then
      /usr/bin/open -n "$destination" || printf '%s\n' 'The previous application could not be reopened.' >> helper.log
    fi
  fi
}
trap finish EXIT
trap 'status=cancelled; exit 1' HUP INT TERM
printf ready > ready
while :; do
  [ ! -e cancel ] || { status=cancelled; exit 1; }
  if [ -e armed ] && [ "$(parent_token)" != "$birth" ]; then break; fi
  count=$((count-1))
  [ "$count" -gt 0 ] || { status=timeout; exit 1; }
  /bin/sleep 0.1
done
[ ! -e cancel ] || { status=cancelled; exit 1; }
ordinary_path "$package" && [ -f "$package" ] || { status=package-changed; exit 1; }
actual=$(/usr/bin/shasum -a 256 "$package"); actual=${actual%% *}
[ "$actual" = "$digest" ] || { status=checksum-mismatch; exit 1; }
ordinary_path "$destination" && ordinary_path "$parent" || { status=installation-changed; exit 1; }
[ "$(/usr/bin/stat -f '%d:%i' "$destination")" = "$bundle_id" ] &&
[ "$(/usr/bin/stat -f '%d:%i' "$parent")" = "$parent_id" ] && [ -w "$parent" ] || { status=installation-changed; exit 1; }
actual=$(/usr/bin/shasum -a 256 "$executable"); actual=${actual%% *}
[ "$actual" = "$source_executable_hash" ] || { status=installation-changed; exit 1; }
actual=$(/usr/bin/shasum -a 256 "$destination/Contents/Info.plist"); actual=${actual%% *}
[ "$actual" = "$source_info_hash" ] || { status=installation-changed; exit 1; }
require_app "$destination" "$source" '' || exit 1
/bin/mkdir "$mountpoint"
mounted=1
status=mount-failed
/usr/bin/hdiutil attach -readonly -nobrowse -noautoopen -mountpoint "$mountpoint" "$package" || exit 1
require_app "$mountpoint/RatioLab.app" "$target" '' || exit 1
status=installer-failed
stage=$(/usr/bin/mktemp -d "$parent/.ratiolab-stage.XXXXXX")
/usr/bin/ditto "$mountpoint/RatioLab.app" "$stage/RatioLab.app" || exit 1
require_app "$stage/RatioLab.app" "$target" self-test || exit 1
[ ! -e cancel ] || { status=cancelled; exit 1; }
[ "$(/usr/bin/stat -f '%d:%i' "$destination")" = "$bundle_id" ] &&
[ "$(/usr/bin/stat -f '%d:%i' "$parent")" = "$parent_id" ] || { status=installation-changed; exit 1; }
status=installer-failed
backup=$(/usr/bin/mktemp -d "$parent/.ratiolab-backup.XXXXXX")
new_id=$(/usr/bin/stat -f '%d:%i' "$stage/RatioLab.app")
/bin/mv "$destination" "$backup/RatioLab.app" || exit 1
old_moved=1
/bin/mv "$stage/RatioLab.app" "$destination" || exit 1
require_app "$destination" "$target" diagnose || exit 1
committed=1
status=installed
if [ "$restart" = 1 ]; then status=installed-restart-requested; fi
'''
