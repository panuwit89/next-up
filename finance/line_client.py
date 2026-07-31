from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookParser

from finance.config import Settings, get_settings


@dataclass(frozen=True)
class LineTextEvent:
    reply_token: str
    text: str
    user_id: str | None = None


class LineClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._configuration = Configuration(access_token=self.settings.LINE_CHANNEL_ACCESS_TOKEN)
        self._api_client = ApiClient(self._configuration)
        self._messaging_api = MessagingApi(self._api_client)
        self._parser = WebhookParser(self.settings.LINE_CHANNEL_SECRET)

    def push_message(self, text: str, user_id: str | None = None) -> None:
        target_user = user_id or self.settings.LINE_USER_ID
        if not target_user:
            raise ValueError("LINE_USER_ID is required for scheduled push messages.")

        self._ensure_access_token()
        self._messaging_api.push_message(
            PushMessageRequest(
                to=target_user,
                messages=[TextMessage(text=text)],
            )
        )

    def reply_message(self, reply_token: str, text: str) -> None:
        if not reply_token:
            raise ValueError("reply_token is required for on-demand replies.")

        self._ensure_access_token()
        self._messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            )
        )

    def parse_webhook_events(self, body: bytes, signature: str | None) -> list[LineTextEvent]:
        if not signature:
            raise InvalidSignatureError("Missing x-line-signature header.")

        raw_body = body.decode("utf-8")
        events = self._parser.parse(raw_body, signature)
        return [event for event in (self._to_text_event(item) for item in events) if event]

    def _ensure_access_token(self) -> None:
        if not self.settings.LINE_CHANNEL_ACCESS_TOKEN:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is required to call LINE Messaging API.")

    @staticmethod
    def _to_text_event(event: Any) -> LineTextEvent | None:
        message = getattr(event, "message", None)
        text = getattr(message, "text", None)
        reply_token = getattr(event, "reply_token", None)
        if not text or not reply_token:
            return None

        source = getattr(event, "source", None)
        user_id = getattr(source, "user_id", None)
        return LineTextEvent(reply_token=reply_token, text=text, user_id=user_id)
