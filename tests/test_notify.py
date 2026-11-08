"""The general Telegram bot is send-only; questionnaires use the operator bots."""

from mnemosyne.notify import Notifier


def test_general_notifier_has_no_inbound_poll():
    # A random message to the alert bot must not be consumed into the control
    # inbox/journal. Questionnaire answers only go through operator.telegram.
    assert not hasattr(Notifier, "poll")
