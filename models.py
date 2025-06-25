# --- models.py ---
from sqlalchemy import Boolean, Column, Integer, String, Date, Float
from database import Base
from pydantic import BaseModel, EmailStr
from datetime import date

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    plan_expiry_date = Column(Date)

class BotConfig(Base):
    __tablename__ = "bot_configs"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer)
    exnova_email = Column(String)
    exnova_password = Column(String) # Será guardado encriptado
    entry_value = Column(Float, default=1.0)
    use_martingale = Column(Boolean, default=True)
    mg_levels = Column(Integer, default=2)
    mg_factor = Column(Float, default=2.0)
    trade_mode = Column(String, default="aggressive") # 'aggressive' or 'conservative'

# Pydantic models for data validation
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    plan_expiry_date: date

class BotConfigCreate(BaseModel):
    exnova_email: EmailStr
    exnova_password: str
    entry_value: float
    use_martingale: bool
    mg_levels: int
    mg_factor: float
    trade_mode: str
