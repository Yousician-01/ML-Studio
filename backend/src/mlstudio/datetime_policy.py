"""Shared explicit datetime parsing policy, unchanged from temporal-v1."""

import re
from typing import Literal

from pydantic import Field, model_validator

from mlstudio.schemas import InputModel


class DatetimeSource(InputModel):
    format: str = Field(default="ISO8601", min_length=1, max_length=100)
    naive: Literal["utc", "reject"] = "reject"
    invalid: Literal["reject", "coerce"] = "reject"

    @model_validator(mode="after")
    def explicit_format(self):
        if self.format != "ISO8601" and not (
            "%Y" in self.format and "%m" in self.format and "%d" in self.format
        ):
            raise ValueError("Use ISO8601 or an explicit format containing year, month and day.")
        if self.format != "ISO8601" and (
            set(re.findall(r"%([A-Za-z%])", self.format)) - set("YmdHMSfz%")
        ):
            raise ValueError(
                "Use numeric date/time directives; locale-dependent formats are unsupported."
            )
        return self
