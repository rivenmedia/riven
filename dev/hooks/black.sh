black $(git diff --name-only --cached | grep '\.py$' || exit 0) && git add .
