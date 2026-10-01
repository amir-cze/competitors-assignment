from pydantic import BaseModel


class LoginIn(BaseModel):
    password: str


class OpsLoginIn(BaseModel):
    token: str
