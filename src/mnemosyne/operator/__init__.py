"""Operator channel: the third correspondent of a task's mailbox.

Agents ASK (`ask_operator`), the operator ANSWERS — over Telegram (inline
keyboard buttons, one bot per agent) or via `mnemosyne answer` on the CLI.
A question never creates a task: it parks the running task until the answer
lands back in its mailbox.
"""
