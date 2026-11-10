---
name: commit-msg
description: Inspects git status and diff across the workspace, analyzes all code modifications, and generates standard Conventional Commits messages in English with concise summaries and optional detailed body. Use when the user invokes /commit-msg, asks for a commit message, wants to summarize recent changes for git commit, or asks to commit code changes.
---

# Git Commit Message Generator (`commit-msg`)

This skill inspects all staged, unstaged, and untracked changes across the repository, synthesizes what changed and why, and formats clean, idiomatic Conventional Commits messages in **English**.

---

## 1. Trigger Conditions & Language Rules

### Quy định ngôn ngữ (Language Rules):
- **Toàn bộ nội dung phân tích, tóm tắt, giải thích và trao đổi với người dùng**: Phải dùng **Tiếng Việt**.
- **Chỉ riêng Commit Message (subject, body, git command)**: Bắt buộc chuẩn hóa bằng **Tiếng Anh (English)** theo quy chuẩn Conventional Commits.

### Khi nào kích hoạt:
- Người dùng gõ `/commit-msg` hoặc đề cập đến việc tạo commit message.
- Người dùng hỏi "tạo commit message", "viết commit", "generate commit msg", hoặc "chuẩn bị commit".
- Người dùng hoàn thành một tính năng, fix lỗi hoặc refactor và muốn commit source code.

---

## 2. Step-by-Step Execution Workflow

### Step 1: Inspect Repository State

Always run commands to gather the exact diff. Never guess changes.

1. **Check file status**:
   ```bash
   git status -s
   ```
2. **Inspect staged diff** (if changes are already staged):
   ```bash
   git diff --cached
   ```
3. **Inspect unstaged diff** (if changes have not been staged yet):
   ```bash
   git diff
   ```
4. **For large diffs**:
   Use `git diff --stat` first to get an overview of modified files, then inspect key files specifically:
   ```bash
   git diff --stat
   git diff -- path/to/critical_file
   ```
5. **For untracked new files**:
   If new files are listed in `git status -s` (marked with `??`), inspect their contents or header to understand their purpose.

> [!NOTE]
> If there are no changes (`git status` is clean), immediately notify the user: "No changes detected in working tree to commit."

---

### Step 2: Semantic Analysis & Classification

Analyze the gathered changes and classify them according to the **Conventional Commits** specification:

| Type       | When to Use                                                               |
| :--------- | :------------------------------------------------------------------------ |
| `feat`     | A new feature or user-facing functionality                                |
| `fix`      | A bug fix or error correction                                             |
| `refactor` | Code restructuring without fixing bugs or adding features                 |
| `perf`     | Performance improvement or optimization                                   |
| `docs`     | Documentation-only changes (README, guides, docstrings)                   |
| `style`    | Formatting, missing semi-colons, whitespace, CSS tweaks (no logic change) |
| `test`     | Adding or updating unit tests, integration tests                          |
| `chore`    | Build tasks, package updates, dependencies, tooling configs, CI/CD        |

**Determine Scope**:
- Extract the core component, module, or package name (e.g., `screener`, `entrade`, `chart`, `auth`, `ui`, `bot`).
- Format: `<type>(<scope>): <summary>` or `<type>: <summary>` (if scope spans whole repo).

---

### Step 3: English Commit Message Rules

1. **Language**: Must strictly be in **English**.
2. **Subject Line**:
   - Imperative mood (e.g., "add", "fix", "update", "refactor" — NOT "added", "fixing", "updates").
   - Lowercase first letter after colon, no trailing period (`.`).
   - Keep subject line under 72 characters (ideally 50-60 chars).
3. **Body (when needed)**:
   - Separate subject and body with a blank line.
   - Use bullet points (`- ...`) to describe *what* changed and *why* (not line-by-line mechanics).
   - Wrap body lines at 72 characters.
4. **Breaking Changes**:
   - Indicate breaking changes with `!` before `:` (e.g., `feat(api)!: ...`) or in the footer: `BREAKING CHANGE: <explanation>`.

---

### Step 4: Multi-Commit Detection

If the changes encompass unrelated features (e.g., fixing an authentication bug AND adding a chart feature AND updating dependencies):
- Advise splitting into multiple logical commits.
- Group files per commit with clear `git add` and `git commit` commands for each group.

---

## 3. Standard Output Format

Output **ONLY** the commit message (and optional ready-to-run git command).
- **Tuyệt đối không giải thích rườm rà hay phân tích dông dài**, đi thẳng vào nội dung commit message.
- Sử dụng code block để người dùng copy trực tiếp.
- Commit message hoàn toàn bằng Tiếng Anh theo chuẩn Conventional Commits.

```text
<type>(<scope>): <concise subject in English>

- <bullet 1>
- <bullet 2>
```

```bash
git add -A && git commit -m "..." -m "..."
```

---

## 4. Examples

### Example A: Single Feature Addition
```text
feat(screener): add real-time RSI and ATR volatility filters

- Integrate ATR14 and Fractal Pivot calculations into screener controller
- Update frontend screener table to display dynamic volatility badges
- Connect WebSocket feed for live price ticker streaming
```

### Example B: Bug Fix
```text
fix(entrade): handle missing tick payload gracefully on reconnect

- Add fallback dictionary check when price tick payload is empty
- Prevent KeyError crash during off-market hours
```

### Example C: Refactoring / Clean-up
```text
refactor(chart): optimize canvas render loop and decouple color constants

- Extract chart theme hex codes into shared color constants
- Avoid redundant DOM repaints during tick batch processing
```

