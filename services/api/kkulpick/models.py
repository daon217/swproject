import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, AwareDatetime, field_validator, model_validator

Key = Annotated[str, Field(min_length=1, max_length=180)]
Money = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=4, allow_inf_nan=False)]


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal[2] = 2
    source: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
    observation_key: Key
    observed_at: AwareDatetime
    result: Literal["success", "not_found", "blocked", "timeout", "error"]
    selected_domain: Literal["product", "food"]
    source_listing_id: Key | None = None
    variant_key: Key | None = None
    condition: Literal["new", "used"] = "new"
    name: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None
    price: Money | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None
    shipping_fee: Money | None = None
    availability: Literal["available","out_of_stock","ended"] | None = None
    url: HttpUrl | None = None
    field_presence: list[Literal["price","currency","shipping_fee","availability","url","name","description"]]

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        if value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("observation is in the future")
        return value.astimezone(UTC)

    @field_validator("price","shipping_fee", mode="before")
    @classmethod
    def decimal_string(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("send money as a decimal string")
        return value

    @model_validator(mode="after")
    def fields_match(self):
        p = set(self.field_presence)
        actual = self.model_fields_set & {"name","description","price","currency","shipping_fee","availability","url"}
        if len(p) != len(self.field_presence) or p != actual:
            raise ValueError("field_presence must match the payload")
        if self.result != "success" and p:
            raise ValueError("failed observation cannot update public fields")
        if self.selected_domain == "food" and self.condition == "used":
            raise ValueError("used food is unsupported")
        if ("price" in p) != ("currency" in p) or ("shipping_fee" in p and "price" not in p):
            raise ValueError("price and currency required together for price snapshot")
        for k in p - {"description","shipping_fee"}:
            if getattr(self, k) is None:
                raise ValueError(f"{k} cannot be null")
        if self.url and (self.url.username or self.url.password or self.url.host not in
                         os.getenv("CATALOG_URL_HOSTS","store.example.test").split(",")):
            raise ValueError("URL host must be explicitly allowed")
        return self
