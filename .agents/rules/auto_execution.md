---
description: Auto-accept workspace scripts and restrict execution within project scope
alwaysApply: true
---

# Workspace Script Execution & Safety Policy

## 1. Auto-Accept Script Execution
- **Allowed Tools & Scripts**:
  - Automatically approve and execute `python3` commands (e.g. `python3 server.py`, `python3 -c "..."`, testing scripts) within this workspace (`/Users/minhpvl/Desktop/stock_rt`).
  - Standard development utility commands (`lsof`, `kill`, `curl`, `pip`, etc.) related to this project are pre-approved and do not require user confirmation.

## 2. Safety & Scope Boundaries
- **Workspace-Only Operations**:
  - All command executions (`Cwd`), file reads, and file writes must strictly operate inside `/Users/minhpvl/Desktop/stock_rt/`.
  - **No external impact**: Never execute destructive commands, modify files, or target paths outside of this workspace directory.
