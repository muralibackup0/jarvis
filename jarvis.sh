#!/bin/sh
# Launcher for Git Bash / WSL / zsh. Runs the Windows Python in .venv so Jarvis can control Windows.
cd "$(dirname "$0")" || exit 1
exec .venv/Scripts/python.exe main.py "$@"
