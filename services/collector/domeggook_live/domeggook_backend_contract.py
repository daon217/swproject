"""Owned v2 shape validator; compatibility is tested against the team's read-only model."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,HttpUrl,AwareDatetime,field_validator,model_validator,ValidationInfo
Key=Annotated[str,Field(min_length=1,max_length=180)]
Money=Annotated[Decimal,Field(ge=0,max_digits=20,decimal_places=4,allow_inf_nan=False)]

class Observation(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    schema_version:Literal[2]=2
    source:Annotated[str,Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
    observation_key:Key
    observed_at:AwareDatetime
    result:Literal['success','not_found','blocked','timeout','error']
    selected_domain:Literal['product','food']
    source_listing_id:Key|None=None
    variant_key:Key|None=None
    # catalog-v2: explicit unknown; omission stays new for existing producers.
    condition:Literal['new','used','unknown']='new'
    name:Annotated[str,Field(min_length=1,max_length=500)]|None=None
    description:Annotated[str,Field(max_length=4000)]|None=None
    price:Money|None=None
    currency:Annotated[str,Field(pattern=r'^[A-Z]{3}$')]|None=None
    shipping_fee:Money|None=None
    availability:Literal['available','out_of_stock','ended']|None=None
    url:HttpUrl|None=None
    field_presence:list[Literal['price','currency','shipping_fee','availability','url','name','description']]

    @field_validator('observed_at')
    @classmethod
    def timestamp(cls,value):
        if value>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('future_observation')
        return value.astimezone(timezone.utc)
    @field_validator('price','shipping_fee',mode='before')
    @classmethod
    def money_string(cls,value):
        if value is not None and not isinstance(value,str):raise ValueError('decimal_string_required')
        return value
    @model_validator(mode='after')
    def fields_match(self,info:ValidationInfo):
        supported={'name','description','price','currency','shipping_fee','availability','url'}
        present=set(self.field_presence);actual=self.model_fields_set&supported
        if len(present)!=len(self.field_presence) or present!=actual:raise ValueError('field_presence_mismatch')
        if self.result!='success' and present:raise ValueError('failed_observation_has_values')
        if self.selected_domain=='food' and self.condition=='used':raise ValueError('used_food_unsupported')
        if ('price' in present)!=('currency' in present) or 'shipping_fee' in present and 'price' not in present:raise ValueError('price_currency_pair_required')
        if any(getattr(self,k) is None for k in present-{'description','shipping_fee'}):raise ValueError('null_public_field')
        context=info.context or {}
        if self.currency is not None and self.currency not in context.get('currencies',['KRW','USD','AUD','EUR','INR','GBP','JPY','CNY']):raise ValueError('unsupported_currency')
        if self.url and (self.url.username or self.url.password or self.url.host not in context.get('hosts',['store.example.test'])):raise ValueError('unapproved_URL_host')
        return self
