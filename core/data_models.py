from pydantic import BaseModel, Field
from typing import Optional

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
    # O alias permite que o bot crie o objeto usando nomes simples como 'open',
    # mas os dados são armazenados com os nomes corretos da classe.
    setup_candle_open: float = Field(..., alias='open')
    setup_candle_high: float = Field(..., alias='high')
    setup_candle_low: float = Field(..., alias='low')
    setup_candle_close: float = Field(..., alias='close')
    
    def to_dict(self) -> dict:
        """
        Converte o objeto para um dicionário que pode ser inserido no Supabase.
        Este era o método que estava em falta.
        """
        # model_dump() é o método padrão do Pydantic v2 para serialização.
        # Ele usará os nomes dos campos da classe (ex: 'setup_candle_open'),
        # que é o que o banco de dados espera.
        return self.model_dump()

    class Config:
        # Permite que o modelo seja populado com campos extras que não estão definidos
        # (como 'id', 'from', 'to' da vela), que serão simplesmente ignorados.
        # Isto torna a criação do objeto mais robusta.
        extra = 'ignore'
