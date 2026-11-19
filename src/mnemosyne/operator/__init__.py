"""Operator channel: the third correspondent of a task's mailbox.

Agents ASK (`ask_operator`), the operator ANSWERS — over Telegram (inline
keyboard buttons, one bot per agent) or via `mnemosyne answer` on the CLI.
A question never creates a task: the synchronous tool waits for the answer and
returns it to the agent in the same turn; the answer is also kept in the task
mailbox for audit.
"""
