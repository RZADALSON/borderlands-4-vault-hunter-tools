"""Everything the player reads comes in Polish and English, in that order. Shared by the filter and the meter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mods_base import SpinnerOption

Text = tuple[str, str]
POLISH = "pl"
ENGLISH = "en"
language_in_use: str = ENGLISH
# Every option's texts, for when the language changes
labelled: list[tuple[Any, Text, Text]] = []


def use_language(language: str) -> None:
    """Sets the language, and puts every option's name and description into it."""
    global language_in_use  # noqa: PLW0603

    language_in_use = language
    for option, name, description in labelled:
        show_label(option, name, description)


def say(text: Text) -> str:
    """Picks the text for the language in use."""
    return text[0] if language_in_use == POLISH else text[1]


def show_label(option: Any, name: Text, description: Text) -> None:
    """Sets what an option is called, in the current language."""
    option.display_name = option.description_title = say(name)
    option.description = say(description)


def label(option: Any, name: Text, description: Text) -> Any:
    """Says what an option is called in the menus. Language changes go through what's kept here."""
    labelled.append((option, name, description))
    show_label(option, name, description)
    return option


class LocalizedSpinner(SpinnerOption):
    """
    A choice whose entries read in the player's language. Its `key` stays the same whatever the
    language: that's what the code checks, and what the settings file keeps.
    """

    labels: dict[str, Text] = {}  # noqa: RUF012
    key: str = ""
    default_key: str = ""
    after_change: Callable[[], None] | None = None

    def key_for(self, value: str) -> str | None:
        """Finds which entry a value means. It may be in any language, or from an older version."""
        for key, texts in self.labels.items():
            if value == key or value in texts:
                return key
        return None

    def __setattr__(self, name: str, value: Any) -> None:
        if name != "value" or not self.labels:
            super().__setattr__(name, value)
            return
        self.key = self.key_for(value) or self.key
        super().__setattr__("value", say(self.labels[self.key]))
        if self.after_change is not None:
            self.after_change()

    def _to_json(self) -> str:
        return self.key

    def _from_json(self, value: Any) -> None:
        if self.key_for(str(value)) is None:
            super()._from_json(value)  # Which logs that it's sticking with the default
        else:
            self.value = str(value)

    def relabel(self) -> None:
        """Puts what's shown in the current language, which is no change to what's chosen."""
        self.choices = [say(text) for text in self.labels.values()]
        self.default_value = say(self.labels[self.default_key])
        object.__setattr__(self, "value", say(self.labels[self.key]))


def localized_spinner(identifier: str, default: str, labels: dict[str, Text]) -> LocalizedSpinner:
    """Creates a choice from its entries' keys and what they're called."""
    option = LocalizedSpinner(identifier, default, list(labels))
    option.key = option.default_key = default
    option.labels = labels
    option.relabel()
    return option
