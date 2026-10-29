"""Typed set of use cases injected into Telegram handlers."""

from dataclasses import dataclass

from app.application.use_cases import (
    CancelWorkflow,
    ChooseLanguage,
    DeliverSubtitle,
    FindSubtitles,
    NavigateSeries,
    SearchTitles,
    SelectTitle,
    StartSearch,
)
from app.application.use_cases.interface_preferences import InterfacePreferences


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    start_search: StartSearch
    choose_language: ChooseLanguage
    search_titles: SearchTitles
    select_title: SelectTitle
    navigate_series: NavigateSeries
    find_subtitles: FindSubtitles
    deliver_subtitle: DeliverSubtitle
    cancel_workflow: CancelWorkflow
    interface_preferences: InterfacePreferences
