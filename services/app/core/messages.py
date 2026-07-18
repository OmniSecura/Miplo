"""Stabilne kody sukcesu przeznaczone do tłumaczenia przez frontend."""

from enum import Enum

from pydantic import BaseModel


class MessageCode(str, Enum):
    REVIEW_REPORTED = "review_reported"


class ApiMessage(BaseModel):
    message_code: MessageCode
