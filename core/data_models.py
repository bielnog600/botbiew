from pydantic import BaseModel, Field, model_validator
from typing import Optional, Dict, Any

class TradeSignal(BaseModel):
    """
    Define a estrutura de dados para um sinal de trade.
    Usa Pydantic para validação e conversão de dados.
    """
    # Campos principais do sinal
    pair: str
    direction: str
    strategy: str

    # Mapeia os dados da vela (candle) para os campos do banco de dados
    setup_candle_open: float = Field(..., alias='open')
    setup_candle_close: float = Field(..., alias='close')
    # Torna 'high' e 'low' opcionais para evitar erros com dados em tempo real
    setup_candle_high: Optional[float] = Field(None, alias='high')
    setup_candle_low: Optional[float] = Field(None, alias='low')

    @model_validator(mode='before')
    @classmethod
    def check_high_low(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Garante que 'high' e 'low' tenham valores. Se não forem fornecidos pela API,
        usa 'open' e 'close' para calculá-los, tornando o modelo mais robusto.
        """
        if isinstance(data, dict):
            open_price = data.get('open')
            close_price = data.get('close')

            if open_price is not None and close_price is not None:
                # Se 'high' não existir ou for nulo, calcula-o
                if 'high' not in data or data.get('high') is None:
                    data['high'] = max(open_price, close_price)
                
                # Se 'low' não existir ou for nulo, calcula-o
                if 'low' not in data or data.get('low') is None:
                    data['low'] = min(open_price, close_price)
        
        return data
    
    def to_dict(self) -> dict:
        """
        Converte o objeto para um dicionário que pode ser inserido no Supabase.
        """
        return self.model_dump()

    class Config:
        # Permite que o modelo ignore campos extras da API que não são necessários
        extra = 'ignore'
