"""Regression coverage for Telegram Business updates at normal-DM ingress."""

from types import SimpleNamespace

from plugins.platforms.telegram.adapter import TelegramAdapter


def _adapter() -> TelegramAdapter:
    return object.__new__(TelegramAdapter)


def test_business_message_is_not_treated_as_normal_dm() -> None:
    """A Business copy of an owner DM must not start a second normal session."""
    business_message = object()
    update = SimpleNamespace(
        business_message=business_message,
        effective_message=business_message,
        message=None,
    )

    assert _adapter()._effective_update_message(update) is None


def test_normal_message_still_reaches_normal_dm_handler() -> None:
    message = object()
    update = SimpleNamespace(
        business_message=None,
        effective_message=message,
        message=message,
    )

    assert _adapter()._effective_update_message(update) is message
