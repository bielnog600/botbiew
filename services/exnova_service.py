import logging
import time
import random
import os
import shutil
import psutil
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
        # --- CORREÇÃO: Limpa sessões antigas ANTES de iniciar uma nova ---
        self._cleanup_old_sessions()
        self._setup_driver()

    def _cleanup_old_sessions(self):
        """Força o encerramento de processos antigos do Chrome e limpa pastas temporárias."""
        self.logger.info("A verificar e limpar sessões antigas do navegador...")
        try:
            # Encerra processos "zombie"
            for proc in psutil.process_iter(['pid', 'name']):
                if 'chrome' in proc.info['name'].lower() or 'chromedriver' in proc.info['name'].lower():
                    self.logger.warning(f"A encerrar processo antigo: {proc.info['name']} (PID: {proc.info['pid']})")
                    proc.kill()
            
            # Limpa pastas de perfil antigas
            for item in os.listdir('/tmp'):
                if item.startswith('selenium_user_data_'):
                    path = os.path.join('/tmp', item)
                    self.logger.warning(f"A remover pasta de perfil antiga: {path}")
                    shutil.rmtree(path, ignore_errors=True)
            self.logger.info("Limpeza de sessões antigas concluída.")
        except Exception as e:
            self.logger.error(f"Erro durante a limpeza de sessões antigas: {e}")


    def _setup_driver(self):
        """Configura as opções do Chrome e inicializa o WebDriver."""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        
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
            self.driver.get("https://trade.exnova.com/en/login")

            wait = WebDriverWait(self.driver, 30)
            
            email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email']")))
            email_input.send_keys(self.email)
            self.logger.info("Campo de email preenchido.")

            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
            password_input.send_keys(self.password)
            self.logger.info("Campo de senha preenchido.")

            login_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Log in')]")
            login_button.click()
            self.logger.info("Botão de login clicado. A aguardar pela sala de negociação...")

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.traderoom")))
            
            self.logger.info("Login realizado com sucesso! Sala de negociação carregada.")
            return True, None

        except TimeoutException:
            self.logger.error("Timeout ao tentar fazer login. A página demorou demasiado a carregar ou os elementos não foram encontrados.")
            try:
                self.driver.save_screenshot("login_timeout_error.png")
            except: pass
            return False, "Timeout no login"
        except Exception as e:
            self.logger.error(f"Ocorreu um erro inesperado durante o login: {e}")
            try:
                self.driver.save_screenshot("login_unexpected_error.png")
            except: pass
            return False, str(e)

    def reconnect(self):
        """Tenta reconectar-se à plataforma, garantindo que a sessão antiga é encerrada."""
        self.logger.warning("A tentar reconectar à Exnova...")
        self.quit()
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
            # Esta lógica precisa de ser ajustada com os seletores corretos do site
            return True
        except Exception as e:
            self.logger.error(f"Falha ao mudar de conta para {balance_type}: {e}")
            return False

    def get_open_assets(self):
        self.logger.warning("get_open_assets() está a usar uma lista estática de ativos.")
        return ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "AUDCAD-OTC", "USDJPY-OTC"]

    def get_historical_candles(self, asset, timeframe, count):
        self.logger.warning(f"get_historical_candles() para {asset} está a retornar dados simulados.")
        return [{ 'open': 1, 'high': 1.01, 'low': 0.99, 'close': 1, 'volume': 1000 }] * count

    def get_current_balance(self):
        if not self.driver: return 0.0
        try:
            # Esta lógica precisa de ser ajustada com os seletores corretos do site
            return 10000.00 # Valor de exemplo
        except Exception as e:
            self.logger.error(f"Não foi possível obter o saldo: {e}")
            return 0.0

    def execute_trade(self, amount, asset, direction, timeframe):
        if not self.driver: return None
        try:
            self.logger.info(f"A executar operação: {direction.upper()} {amount} em {asset} por {timeframe} min.")
            # Esta lógica precisa de ser ajustada com os seletores corretos do site
            return int(time.time())
        except Exception as e:
            self.logger.error(f"Falha ao executar a operação no navegador: {e}")
            return None
