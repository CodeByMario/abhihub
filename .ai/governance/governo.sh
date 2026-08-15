#!/usr/bin/env bash
# governo — CLI wrapper for the AbhiHub Governance Engine
cd "$(dirname "$0")" && python -m ai.governance.governo "$@"
