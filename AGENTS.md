# Repository Instructions

## Communication

- Communicate with the repository owner in German.
- Keep source code, identifiers, comments, docstrings, log messages, exception messages, warnings, tests, commit messages, and durable repository documentation in English.
- Conversational summaries and explanations may be German.

## Long outputs

- When an answer is longer than roughly 100 lines or primarily consists of architecture, analysis, planning, or documentation, write the full output to `docs/_session_output.md`.
- Overwrite `docs/_session_output.md` for each new long output.
- In that case, terminal output contains only a short summary, important warnings, and the output file path.
- Keep small conversational responses in the terminal only.

## Architecture

- Dependencies point only downward.
- Before creating a module, check whether an existing domain already owns the responsibility.
- Do not perform filesystem operations, configure logging, build registries, or cause other runtime side effects during import.


## Security and masking
- Never print, log, commit, snapshot, or expose masked values or secrets.

## Git workflow

- Never make changes directly on the stable default branch.
- Use one branch or worktree per logical task.
- Keep commits focused and reviewable.
- Show and summarize the diff before committing.
- Do not push, merge, or open a pull request unless explicitly requested.
