#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/native/apple-calendar-bridge"
OUTPUT_DIR="$SOURCE_DIR/.build"

mkdir -p "$OUTPUT_DIR"
xcrun swiftc \
  "$SOURCE_DIR/main.swift" \
  -parse-as-library \
  -framework EventKit \
  -Xlinker -sectcreate \
  -Xlinker __TEXT \
  -Xlinker __info_plist \
  -Xlinker "$SOURCE_DIR/Info.plist" \
  -o "$OUTPUT_DIR/apple-calendar-bridge"

echo "Pont Apple Calendar construit : $OUTPUT_DIR/apple-calendar-bridge"
echo "Pour demander l’accès : $OUTPUT_DIR/apple-calendar-bridge request-access"
