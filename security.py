# --- security.py ---
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from fastapi.security import OAuth2PasswordBearer
import models

# Configuração de Senhas da Plataforma
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-for-jwt")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 horas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Configuração de Encriptação das Credenciais da Corretora
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "your-super-secret-key-for-credentials")
fernet = Fernet(ENCRYPTION_KEY.encode())

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def authenticate_user(db: Session, email: str, password: str):
    user = get_user(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_user(db: Session, user: models.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password, plan_expiry_date=user.plan_expiry_date)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    return fernet.decrypt(encrypted_data.encode()).decode()
