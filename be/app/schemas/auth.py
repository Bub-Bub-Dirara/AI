from pydantic import BaseModel, EmailStr, Field

class SignUpIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="6자 이상 권장")

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    email: EmailStr

class MessageOut(BaseModel):
    message: str
