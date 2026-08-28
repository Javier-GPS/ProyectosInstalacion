from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LuxJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1, max_length=50)
    target_refs: list[str] = Field(min_length=1, max_length=5000)
    base_inventory_hash: str = Field(pattern=r"^(sha256:[0-9a-f]{64}|md5:[0-9a-f]{32})$")
    materialize_valid: Literal[True]
    mode: Literal["calculate", "optimize"] = "optimize"


class LuxJobItemView(BaseModel):
    id: str
    target_ref: str
    state: str
    calculation_status: str
    materialization_status: str
    error_code: str | None = None
    error_message: str | None = None
    result_hash: str | None = None


class LuxJobView(BaseModel):
    id: str
    project_id: int
    zone_id: str
    intent_id: str
    state: str
    state_version: int
    total: int
    succeeded: int
    failed: int
    blocked: int
    unknown: int
    materialize_valid: bool
    partial_policy: str
    mode: str
    created_at: str
    updated_at: str
    items: list[LuxJobItemView] = Field(default_factory=list)
