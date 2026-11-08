# Email waits — park a task until a matching email arrives

## Why

The browser agent sometimes sends an email (permission request, missing
metadata, clarification) and must wait for the answer. Polling the webmail in a
loop burns tokens and keeps a browser session open. The old fallback was to end
the turn and let the task be resumed blindly; that could spin forever.

`wait_for_email` turns this into a first-class, parked state:

1. the agent registers criteria (expected sender and/or the Message-ID of the
   email it sent);
2. a marker message is posted in the task mailbox, so the task is not closed;
3. `Database.next_task()` parks the task (no activation, no tokens);
4. the heartbeat's `email_watch` job polls an IMAP mailbox;
5. on a match, the email is posted into the task mailbox and the task is picked
   up again by the next agency tick.

Email is **input only** here. The tool does not send email and does not scrape
the webmail; the browser agent remains responsible for composing/sending the
message through the web interface.

## Configuration

`config/config.yaml`:

```yaml
email:
  enabled: false              # set true once credentials are available
  imap_host: imap.gmail.com
  imap_port: 993
  imap_ssl: true
  folder: INBOX
  poll_interval_s: 60
  lookback_days: 14
  max_body_chars: 4000
  username_env: MNEMOSYNE_EMAIL_USER
  password_env: MNEMOSYNE_EMAIL_PASSWORD
```

Credentials are read from the environment first, then from the vault under the
lowercased variable name:

```bash
# .env (never committed)
MNEMOSYNE_EMAIL_USER=archivist.mnemosyne@gmail.com
MNEMOSYNE_EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail app password

# or
mnemosyne vault set mnemosyne_email_password xxxx-xxxx-xxxx-xxxx
```

Gmail requires IMAP enabled and an **app password**; the account password is
not accepted. The mailbox is opened `readonly=True` and messages are fetched
with `RFC822`, so flags/read state are not changed.

`email.enabled: false` keeps the heartbeat from opening a socket. Once enabled,
the `email_watch` job is created at boot; restart the container after changing
the setting.

## Tool contract

Available to the browser and coder agents:

```text
wait_for_email(
  from_address="person@example.org",   # expected sender (exact or @domain)
  subject_contains="permission",       # optional
  in_reply_to="<outgoing@example.org>",# optional Message-ID of the sent email
  timeout_s=0,                         # 0 = never timeout
  reason="attente du consentement de l'institution"
)
```

At least one of `from_address` / `in_reply_to` is required; a subject alone is
too broad. The tool returns:

> attente email #N enregistrée — arrête ton tour. La session sera remise dans
> la file automatiquement quand un email correspondant arrivera.

The agent must stop its turn (like `ask_operator`), not call `finish`.

## Matching rules

A message matches when:

- it arrives in the configured folder after the wait was created (1 h clock
  skew tolerated);
- `from_address` matches the `From` address (`@domain` suffix matches too;
  an address without `@` is a substring of the raw header);
- `subject_contains` is a case-insensitive substring of the decoded subject;
- `in_reply_to` appears in `In-Reply-To` or `References` (angle brackets
  ignored);
- it is not from the agent's own `identity.agent_email`;
- it is not an automatic reply (`Auto-Submitted`, `X-Autoreply`,
  `X-Autorespond` are rejected).

The newest 500 UIDs since the oldest pending wait (minus one day) are scanned
per poll. One pending wait per task is allowed.

## Wake-up and mailbox format

The watcher posts a message from `email` to the waiting agent:

```text
[EMAIL RECEIVED]
From: Person <person@example.org>
To: agent@example.org
Subject: Re: permission
Date: ...
Message-ID: <reply@example.org>

<plain-text body, max_body_chars>
```

The marker message is marked `handled`, the `email_waits` row becomes
`matched`, and an `email.received` observatory event is recorded. The task is
then eligible again: `next_task()` sees the pending `email → agent` message and
reactivates the session with the email in its context.

If `timeout_s > 0` and no email matched, the watcher posts a `system → agent`
message (`[EMAIL WAIT #N TIMEOUT]`) and marks the wait `timed_out`. With the
default `timeout_s=0`, the task stays parked until an email arrives or the
operator cancels it.

## Operations

- `mnemosyne queue list` shows `📧 attend un email` on a parked task.
- `mnemosyne queue cancel <task_id>` cancels the task, drops its mailbox,
  session cache and email wait.
- The observatory shows `email.wait`, `email.received` and `email.timeout`
  events on the mailbox step.
- If IMAP is temporarily unavailable, the wait stays pending; the job logs a
  warning and retries at the next interval. Timeouts still fire.
- A wait survives a container restart because it lives in SQLite; the
  `email_watch` job is re-created at bootstrap when `email.enabled` is true.

## Limitations

- IMAP only; no Gmail API / OAuth, no webmail scraping.
- Text body only; attachments are ignored.
- The watcher scans the newest 500 UIDs since the oldest wait; very old or very
  large mailboxes may need a manual `from_address`/`subject_contains` to narrow
  the match.
- Email is not an operator channel: `mnemosyne answer` answers `ask_operator`,
  not an email wait. Use `queue cancel` to abort an email wait.
- The browser agent still sends the email itself via the web interface; this
  feature only watches for the reply.
