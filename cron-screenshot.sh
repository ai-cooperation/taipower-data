#!/bin/bash
cd ~/taipower-data || exit 1
git pull --rebase --quiet 2>/dev/null
python3 screenshot.py 2>&1
if git diff --quiet data/ 2>/dev/null; then
    echo '  no changes'
else
    git add data/screenshots/
    git commit -m "screenshot: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" --quiet
    git push --quiet 2>&1
    echo '  pushed'
fi
