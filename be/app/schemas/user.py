from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    email: EmailStr = Field(..., example="test@example.com")
    password: str = Field(..., min_length=8, example="P@ssw0rd!")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    class Config:
        from_attributes = True  # SQLAlchemy → Pydantic 변환

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
