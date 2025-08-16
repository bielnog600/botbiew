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
            self.logger.error("Timeout ao tentar fazer login.")
            return False, "Timeout no login"
        except Exception as e:
            self.logger.error(f"Ocorreu um erro inesperado durante o login: {e}")
            return False, str(e)

    def reconnect(self):
        """Tenta reconectar-se à plataforma, garantindo que a sessão antiga é encerrada."""
        self.logger.warning("A tentar reconectar à Exnova...")
        self.quit() # Garante que o driver antigo é encerrado
        self._setup_driver()
        return self.connect()

    def quit(self):
        """Encerra o navegador de forma segura."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Navegador encerrado com sucesso.")
            except Exception as e:
                self.logger.error(f"Erro ao encerrar o navegador: {e}")
            finally:
                self.driver = None

    def get_profile(self):
        return {"name": self.email}

    def change_balance(self, balance_type):
        if not self.driver: return False
        try:
            self.logger.info(f"A tentar mudar para a conta {balance_type}...")
            # A lógica exata aqui depende da estrutura do site da Exnova
            # Esta é uma implementação de exemplo que precisa de ser ajustada
            wait = WebDriverWait(self.driver, 10)
            balance_selector = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(@class,'balance-switcher')]")))
            balance_selector.click()
            account_option = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[contains(text(), '{balance_type.capitalize()}')]")))
            account_option.click()
            self.logger.info(f"Conta mudada com sucesso para {balance_type}.")
            return True
        except Exception as e:
            self.logger.error(f"Falha ao mudar de conta para {balance_type}: {e}")
            return False

    def get_open_assets(self):
        self.logger.warning("get_open_assets() está a usar uma lista estática de ativos.")
        return ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "AUDCAD-OTC", "USDJPY-OTC"]

    def get_historical_candles(self, asset, timeframe, count):
        self.logger.warning(f"get_historical_candles() para {asset} está a retornar dados simulados.")
        # A implementação real disto com Selenium é muito complexa.
        # Retornamos dados simulados para permitir que as estratégias funcionem.
        return [{ 'open': 1, 'high': 1.01, 'low': 0.99, 'close': 1, 'volume': 1000 }] * count

    def get_current_balance(self):
        if not self.driver: return 0.0
        try:
            # A lógica exata aqui depende da estrutura do site da Exnova
            balance_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(@class,'balance-value')]"))
            )
            balance_text = balance_element.text.replace('R$', '').replace(',', '.').strip()
            return float(balance_text)
        except Exception as e:
            self.logger.error(f"Não foi possível obter o saldo: {e}")
            return 0.0

    def execute_trade(self, amount, asset, direction, timeframe):
        if not self.driver: return None
        try:
            self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {timeframe} min.")
            # A lógica exata aqui depende da estrutura do site da Exnova
            wait = WebDriverWait(self.driver, 10)
            amount_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@class,'amount-input')]")))
            amount_input.clear()
            amount_input.send_keys(str(amount))

            if direction.lower() == 'call':
                button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'call-button')]")))
            else:
                button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'put-button')]")))
            
            button.click()
            self.logger.info("Operação executada com sucesso no navegador.")
            return int(time.time())
        except Exception as e:
            self.logger.error(f"Falha ao executar a operação no navegador: {e}")
            return None
