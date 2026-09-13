#!/bin/sh
set -eu
for command_name in python3 git codex; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "Missing $command_name. Install Python 3.11+, Git, and Codex CLI; then run codex login." >&2
        exit 1
    }
done
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' || {
    echo 'Python 3.11+ is required.' >&2
    exit 1
}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$script_dir/codex_status.py" ]; then
    project_dir=$script_dir
else
    project_dir=${CODEXPULSE_INSTALL_DIR:-"$HOME/.codexpulse/project"}
    if [ -e "$project_dir" ]; then
        echo "Destination exists: $project_dir. Run its codex_status.py --install, or set CODEXPULSE_INSTALL_DIR." >&2
        exit 1
    fi
    git clone --depth 1 https://github.com/NoobyGains/CodexPulse.git "$project_dir"
fi
python3 "$project_dir/codex_status.py" --install
python3 "$project_dir/codex_status.py" --install-skill
printf 'CodexPulse installed. Restart Codex for the footer.\nFull display: python3 "%s/codex_status.py" --watch\n' "$project_dir"
