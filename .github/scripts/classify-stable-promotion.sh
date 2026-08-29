#!/bin/sh
set -eu

manifest=${1:-.codex-plugin/plugin.json}
: "${GITHUB_REF:?GITHUB_REF is required}"
: "${RELEASE_VERSION:?RELEASE_VERSION is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
: "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY is required}"

plugin_version=$(jq -er '.version | select(type == "string")' "$manifest")
case "$GITHUB_REF" in
    refs/tags/v*)
        tag_version=${GITHUB_REF#refs/tags/v}
        if [ "$tag_version" != "$RELEASE_VERSION" ] || [ "$plugin_version" != "$RELEASE_VERSION" ]; then
            echo "stable package blocked: stable tag, release version, and plugin version must match" >&2
            exit 1
        fi
        echo "required=true" >> "$GITHUB_OUTPUT"
        ;;
    *)
        if [ "$plugin_version" = "$RELEASE_VERSION" ]; then
            echo "required=true" >> "$GITHUB_OUTPUT"
        else
            echo "required=false" >> "$GITHUB_OUTPUT"
            echo "Preview $plugin_version: stable promotion package gate is not requested." >> "$GITHUB_STEP_SUMMARY"
        fi
        ;;
esac
