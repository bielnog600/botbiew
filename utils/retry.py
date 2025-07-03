import asyncio
from typing import Callable, TypeVar, Awaitable, Any

T = TypeVar('T')

async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    retries: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
    **kwargs: Any
) -> T:
    """
    Executa uma função async e, em caso de exceção, tenta novamente.

    Parâmetros:
    - func: função assíncrona que retorna um Awaitable.
    - args/kwargs: argumentos para passar à função.
    - retries: número máximo de tentativas (padrão=3).
    - backoff: tempo em segundos para esperar antes de cada retry, multiplicado exponencialmente.
    - exceptions: tupla de exceções que devem disparar retry (padrão=Exception).

    Retorna o resultado de func ou levanta a última exceção.
    """
    attempt = 0
    delay = backoff
    while True:
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            attempt += 1
            if attempt > retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2
