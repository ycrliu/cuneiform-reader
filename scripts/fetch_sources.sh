#!/usr/bin/env bash
# Download the raw sources a text is built from.
#   scripts/fetch_sources.sh 1.4.3        # ETCSL composition number
# Also refreshes the ORACC/OSL sign list used to turn readings into glyphs.
set -euo pipefail
cd "$(dirname "$0")/.."
num="${1:?usage: fetch_sources.sh <etcsl-number e.g. 1.4.3>}"
mkdir -p data/sources/etcsl data/sources/osl
base='https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi'
curl -sSL -m 120 -o "data/sources/etcsl/c.${num}.html" "${base}?text=c.${num}&display=Crit&charenc=gcirc"
curl -sSL -m 120 -o "data/sources/etcsl/t.${num}.html" "${base}?text=t.${num}"
# Sign list: the live OSL source (newest) plus the published OGSL JSON (fallback).
curl -sSL -m 120 -o data/sources/osl/osl.asl 'https://raw.githubusercontent.com/oracc/osl/master/00lib/osl.asl'
# oracc.museum.upenn.edu serves an incomplete certificate chain; -k is needed for this one host.
tmp="$(mktemp -d)"
curl -ksSL -m 120 -o "$tmp/ogsl.zip" 'https://oracc.museum.upenn.edu/json/ogsl.zip' \
  && unzip -oq "$tmp/ogsl.zip" -d "$tmp" \
  && cp "$tmp/ogsl/ogsl-sl.json" data/sources/osl/ogsl-sl.json \
  && cp "$tmp/ogsl/metadata.json" data/sources/osl/ogsl-metadata.json
rm -rf "$tmp"
echo "fetched ETCSL c.${num}, t.${num} and sign lists into data/sources/"
