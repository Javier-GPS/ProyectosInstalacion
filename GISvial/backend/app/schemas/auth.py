"""Auth schemas."""
from typing import Optional
from pydantic import BaseModel


class GisLoginBody(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: str


class GisSetupBody(BaseModel):
    username: str
    email: str = ""
    password: str


class GisResetRequest(BaseModel):
    email: str


class GisResetApply(BaseModel):
    token: str
    password: str


class GisCreateUserBody(BaseModel):
    username: str
    email: str = ""
    password: str
    role: str = "user"


class GisUpdateUserBody(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
