# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import threading
import queue

# Importações locais (dos outros ficheiros que vamos criar)
import models, security, database
from bot.trader import TradingBot 

# --- Configuração Inicial ---
models.Base.metadata.create_all(bind=database.engine)
app = FastAPI()

# Dicionário para guardar os bots ativos e as suas filas de comunicação
# A chave será o ID do utilizador, e o valor será um dicionário com a thread e a fila
active_bots = {}

# --- Funções Auxiliares ---
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Autenticação ---
# Esta função verifica o token JWT enviado pelo frontend
async def get_current_user(token: str = Depends(security.oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = security.get_user(db, email=email)
    if user is None:
        raise credentials_exception
    return user

# --- Rotas da API (Endpoints) ---

# Rota para servir o frontend
@app.get("/")
async def read_root():
    return FileResponse('index.html')

# Rota para registar um novo utilizador na sua plataforma
@app.post("/register", response_model=models.User)
def create_user(user: models.UserCreate, db: Session = Depends(get_db)):
    db_user = security.get_user(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return security.create_user(db=db, user=user)

# Rota para fazer login na sua plataforma
@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = security.authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # ### VERIFICAÇÃO DO PLANO DE EXPIRAÇÃO ###
    if user.plan_expiry_date and user.plan_expiry_date < datetime.utcnow().date():
         raise HTTPException(status_code=403, detail="Your plan has expired.")

    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Rota para obter informações do utilizador logado
@app.get("/users/me", response_model=models.User)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# Rota para o utilizador guardar as suas credenciais e configurações
@app.post("/bot/config")
async def set_bot_config(config: models.BotConfigCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Encripta a senha da corretora antes de a guardar
    encrypted_password = security.encrypt_data(config.exnova_password)
    config_to_save = config.dict()
    config_to_save['exnova_password'] = encrypted_password
    
    # Guarda ou atualiza a configuração na base de dados
    db_config = db.query(models.BotConfig).filter(models.BotConfig.owner_id == current_user.id).first()
    if db_config:
        for key, value in config_to_save.items():
            setattr(db_config, key, value)
    else:
        db_config = models.BotConfig(**config_to_save, owner_id=current_user.id)
        db.add(db_config)
    
    db.commit()
    db.refresh(db_config)
    return {"message": "Configuration saved successfully"}

# Rota para ligar o bot de um utilizador
@app.post("/bot/start")
async def start_bot(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user.id
    if user_id in active_bots and active_bots[user_id]["thread"].is_alive():
        raise HTTPException(status_code=400, detail="Bot is already running for this user")
    
    config = db.query(models.BotConfig).filter(models.BotConfig.owner_id == user_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Bot configuration not found. Please save your settings first.")

    # Desencripta a senha da corretora para usar na instância do bot
    exnova_password = security.decrypt_data(config.exnova_password)

    # Cria uma nova fila de mensagens e um novo bot para este utilizador
    user_queue = queue.Queue()
    bot_instance = TradingBot(
        email=config.exnova_email,
        password=exnova_password,
        config={
            'valor_entrada': config.entry_value,
            'usar_mg': config.use_martingale,
            'mg_niveis': config.mg_levels,
            'mg_fator': config.mg_factor,
            'modo_operacao': config.trade_mode
        },
        message_queue=user_queue
    )
    
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()

    active_bots[user_id] = {"thread": bot_thread, "queue": user_queue}
    
    return {"message": f"Bot started for user {current_user.email}"}


# Rota para parar o bot de um utilizador
@app.post("/bot/stop")
async def stop_bot(current_user: models.User = Depends(get_current_user)):
    user_id = current_user.id
    if user_id not in active_bots or not active_bots[user_id]["thread"].is_alive():
        raise HTTPException(status_code=400, detail="Bot is not running for this user")

    # Obtém a instância do bot e chama o método para parar
    # (Precisamos adicionar este método na nossa classe TradingBot)
    # bot_instance.stop() # Assumindo que temos uma forma de aceder à instância

    # Por agora, apenas removemos da lista (a thread continuará até ao fim do ciclo)
    # Uma implementação mais robusta usaria um evento de paragem.
    del active_bots[user_id]
    
    return {"message": f"Bot stopping for user {current_user.email}"}

# --- WebSocket para Comunicação em Tempo Real ---

@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    try:
        user = await get_current_user(token, db)
        user_id = user.id
        
        # Espera até que o bot para este utilizador seja iniciado
        while user_id not in active_bots:
            await asyncio.sleep(1)

        await websocket.accept()

        user_queue = active_bots[user_id]["queue"]
        
        # Envia o estado inicial
        # (A classe TradingBot precisaria de ter uma forma de obter este estado)
        # initial_state = bot_instance.get_state()
        # await websocket.send_json(initial_state)

        while True:
            # Pega as mensagens da fila específica deste utilizador
            if not user_queue.empty():
                message = user_queue.get_nowait()
                await websocket.send_json(message)
            await asyncio.sleep(0.1)

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()
        print(f"WebSocket connection closed for token {token}")

