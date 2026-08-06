from datetime import datetime

from ninja import Schema


class LayoutInput(Schema):
    name: str
    module_ids: list[str]


class LayoutOutput(Schema):
    id: int
    name: str
    module_ids: list[str]
    created_at: datetime
    updated_at: datetime

