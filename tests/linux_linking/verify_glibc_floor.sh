#!/usr/bin/env bash
# Verifies that the given binary requires no glibc symbol version newer than
# the given maximum.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <readelf> <binary> <max glibc version>" >&2
  exit 2
fi

readelf=$1
binary=$2
max_version=$3

if [[ ! -x "$readelf" ]]; then
  echo "FAIL: readelf $readelf is not executable" >&2
  exit 1
fi

if [[ ! -e "$binary" ]]; then
  echo "FAIL: $binary does not exist" >&2
  exit 1
fi

required=$("$readelf" -V "$binary" | grep -oE "GLIBC_[0-9]+(\.[0-9]+)+" | sed 's/^GLIBC_//' | sort -uV | tail -n 1)
if [[ -z "$required" ]]; then
  echo "FAIL: $binary has no GLIBC version requirements" >&2
  exit 1
fi

newest=$(printf '%s\n%s\n' "$required" "$max_version" | sort -V | tail -n 1)
if [[ "$newest" != "$max_version" ]]; then
  echo "FAIL: $binary requires GLIBC_$required, newer than GLIBC_$max_version" >&2
  "$readelf" -V "$binary" >&2
  exit 1
fi

echo "OK: $binary requires at most GLIBC_$required (max GLIBC_$max_version)"
