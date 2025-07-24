#!/bin/bash
set -e

# Build docs output to /tmp/public
sphinx-build docs/src/ /tmp/public/

# Serve the docs from /tmp/public
python3 -m http.server 8000 --directory /tmp/public
