import logging
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class ExnovaService:
    """
    Serviço para interagir com a Exnova através de automação de navegador (Selenium).
    Esta classe substitui a necessidade de uma API direta.
    """
    def __init__(self, email, password):
        self.logger = logging.getLogger(__name__)
        self.email = email
        self.password = password
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        """Configura as opções do Chrome e inicializa o WebDriver."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920x1080")
        
        # --- CORREÇÃO: Adiciona um diretório de perfil único a cada arranque ---
        user_data_dir = f"/tmp/selenium_user_data_{int(time.time())}_{random.randint(1000, 9999)}"
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        
        service = Service()
        try:
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.logger.info("WebDriver do Chrome inicializado com sucesso.")
        except Exception as e:
            self.logger.error(f"Falha ao inicializar o WebDriver: {e}")
            self.driver = None

    def connect(self):
        """
        Conecta-se à Exnova fazendo login através do navegador.
        Retorna (True, None) em sucesso, (False, "motivo") em falha.
        """
        if not self.driver:
            return False, "WebDriver não foi inicializado."

        try:
            self.logger.info("A navegar para a página de login da Exnova...")
            self.driver.get("https://exnova.com/login")

            wait = WebDriverWait(self.driver, 20)
            
            email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            email_input.send_keys(self.email)
            self.logger.info("Campo de email preenchido.")

            password_input = self.driver.find_element(By.NAME, "password")
            password_input.send_keys(self.password)
            self.logger.info("Campo de senha preenchido.")

            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()
            self.logger.info("Botão de login clicado. A aguardar pela página principal...")

            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Total Portfolio')]")))
            
            self.logger.info("Login realizado com sucesso!")
            return True, None

        except TimeoutException:
            self.logger.error("Timeout ao tentar fazer login. A página demorou demasiado a carregar ou os elementos não foram encontrados.")
            return False, "Timeout no login"
        except Exception as e:
            self.logger.error(f"Ocorreu um erro inesperado durante o login: {e}")
            return False, str(e)

    def reconnect(self):
        """Tenta reconectar-se à plataforma."""
        self.logger.warning("A tentar reconectar à Exnova...")
        if self.driver:
            try:
                self.driver.quit()
            except: pass
        self._setup_driver()
        return self.connect()

    def get_profile(self):
        return {"name": self.email, "balance_type": self.get_balance_mode()}

    def change_balance(self, balance_type):
        """Muda o tipo de conta (REAL ou PRACTICE) clicando nos elementos da página."""
        if not self.driver: return
        try:
            self.logger.info(f"A tentar mudar para a conta {balance_type}...")
            wait = WebDriverWait(self.driver, 10)

            # Seletor de exemplo, pode precisar de ajuste
            balance_selector = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'account-switcher')]"))) 
            balance_selector.click()

            account_xpath = f"//div[contains(text(), '{balance_type.capitalize()}')]"
            target_account = wait.until(EC.element_to_be_clickable((By.XPATH, account_xpath)))
            target_account.click()
            
            self.logger.info(f"Conta mudada com sucesso para {balance_type}.")
            return True
        except Exception as e:
            self.logger.error(f"Falha ao mudar de conta para {balance_type}: {e}")
            return False

    def get_open_assets(self):
        self.logger.warning("get_open_assets() está a usar uma lista estática de ativos.")
        return ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "AUDCAD-OTC", "USDJPY-OTC"]

    def get_historical_candles(self, asset, timeframe, count):
        self.logger.warning(f"get_historical_candles() para {asset} está a retornar apenas dados simulados da vela atual.")
        try:
            price_element = self.driver.find_element(By.XPATH, "//div[contains(@class, 'current-price')]") # Seletor de exemplo
            current_price = float(price_element.text)
            
            return [{
                'open': current_price * 0.999, 'high': current_price * 1.001,
                'low': current_price * 0.998, 'close': current_price, 'volume': 1000
            }] * count
        except:
            return [{ 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1 }] * count

    def get_current_balance(self):
        """Lê o saldo atual diretamente da página."""
        if not self.driver: return 0.0
        try:
            balance_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'balance-value')]")) # Seletor de exemplo
            )
            balance_text = balance_element.text.replace('R$', '').replace(',', '.').strip()
            return float(balance_text)
        except Exception as e:
            self.logger.error(f"Não foi possível obter o saldo: {e}")
            return 0.0

    def execute_trade(self, amount, asset, direction, timeframe):
        """Executa uma operação clicando nos botões da página."""
        if not self.driver: return None
        try:
            self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {timeframe} min.")
            wait = WebDriverWait(self.driver, 10)

            amount_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@class='amount-input']"))) # Seletor de exemplo
            amount_input.clear()
            amount_input.send_keys(str(amount))

            if direction.lower() == 'call':
                button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-call')]"))) # Seletor de exemplo
            else: # put
                button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-put')]"))) # Seletor de exemplo
            
            button.click()
            
            self.logger.info("Operação executada com sucesso no navegador.")
            return int(time.time()) 
        except Exception as e:
            self.logger.error(f"Falha ao executar a operação no navegador: {e}")
            return None
