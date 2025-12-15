import pandas as pd
import numpy as np

class TechnicalAnalysis:
    @staticmethod
    def prepare_data(candles):
        if not candles:
            return pd.DataFrame()
            
        data = []
        for c in candles:
            if isinstance(c, dict):
                row = {
                    'close': float(c.get('close', 0)),
                    'high': float(c.get('high', c.get('max', 0))),
                    'low': float(c.get('low', c.get('min', 0))),
                }
            else:
                row = {
                    'close': float(c.close),
                    'high': float(getattr(c, 'high', getattr(c, 'max', 0))),
                    'low': float(getattr(c, 'low', getattr(c, 'min', 0))),
                }
            data.append(row)
            
        return pd.DataFrame(data)

    @staticmethod
    def calculate_indicators(df):
        # RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Estocástico (14, 3, 3)
        low_min = df['low'].rolling(window=14).min()
        high_max = df['high'].rolling(window=14).max()
        k_raw = 100 * ((df['close'] - low_min) / (high_max - low_min))
        stoch_k = k_raw.rolling(window=3).mean()
        
        # EMA 100 (Tendência)
        ema_trend = df['close'].ewm(span=100, adjust=False).mean()

        return rsi, stoch_k, ema_trend

    @staticmethod
    def get_signal(candles):
        """
        Estratégia PRO: Confluência + Tendência
        """
        try:
            df = TechnicalAnalysis.prepare_data(candles)
            if df.empty or len(df) < 100:
                return None
            
            rsi_series, stoch_series, ema_series = TechnicalAnalysis.calculate_indicators(df)
            
            price = df['close'].iloc[-1]
            rsi = rsi_series.iloc[-1]
            stoch = stoch_series.iloc[-1]
            ema = ema_series.iloc[-1]

            trend = "ALTA" if price > ema else "BAIXA"
            # print(f"   [ANÁLISE] RSI:{rsi:.1f} | Stoch:{stoch:.1f} | Tendência:{trend}", end=" ")

            # VENDA (PUT)
            if rsi >= 70 and stoch >= 80: # Removido filtro de tendência estrito para mais entradas
                # print("🔥 PUT!")
                return 'put'

            # COMPRA (CALL)
            if rsi <= 30 and stoch <= 20:
                # print("🔥 CALL!")
                return 'call'
            
            # print(".")
                
        except Exception:
            pass
            
        return None

class MoneyManager:
    def __init__(self):
        self.martingale_steps = {}

    def get_amount(self, asset, base_amount, factor):
        step = self.martingale_steps.get(asset, 0)
        # Calcula valor: Base * (Fator ^ Nivel)
        return round(base_amount * (factor ** step), 2)

    def get_current_step(self, asset):
        return self.martingale_steps.get(asset, 0)

    def register_result(self, asset, result, max_levels):
        current = self.martingale_steps.get(asset, 0)
        
        if result == 'win':
            self.martingale_steps[asset] = 0
            return False # Não continua Gale
        else:
            if current < max_levels:
                self.martingale_steps[asset] = current + 1
                return True # Continua Gale
            else:
                self.martingale_steps[asset] = 0 # Reset (Stop Loss)
                return False # Parar Gale
