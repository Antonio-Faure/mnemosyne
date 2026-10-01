# Actions — mnemosyne house rules

One canonical path per action. This is enforced (not just advice): the harness
wraps the helpers and refuses the alternatives.

- **Clicks**: `click_at_xy(x, y)` only (physical click). `js()` and `cdp()` are
  for **reading/observing**; a click or submission through them raises.
- **Keyboard**: `fill_input(selector, text)`, `type_text`, `press_key`.
- **After acting, verify the state** (`capture_screenshot`, `read_page`,
  `page_info`, `wait_for_load`). Never act twice "to be sure":
  - a second click on the same spot within 3 s is refused;
  - an email/form submission already delivered cannot be recalled.

Why: two different click mechanisms made it possible to submit an action twice
(one physical click + one JS click) without noticing. There is now a single
mechanism, and a failure tells you to observe, not to retry.
