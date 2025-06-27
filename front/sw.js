// Nome do cache da nossa aplicação
const CACHE_NAME = 'marombiew-signals-cache-v1';

// Ficheiros essenciais para guardar em cache para a aplicação funcionar offline
const urlsToCache = [
  '/',
  '/index.html',
  'https://cdn.tailwindcss.com',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
];

// Evento de Instalação: é acionado quando o service worker é registado pela primeira vez.
self.addEventListener('install', event => {
  console.log('[Service Worker] Instalando...');
  // Espera até que o cache seja aberto e todos os ficheiros essenciais sejam adicionados
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Cache aberto. Guardando ficheiros essenciais...');
        return cache.addAll(urlsToCache);
      })
  );
});

// Evento de Fetch: é acionado sempre que a aplicação tenta obter um recurso (ex: imagem, script, etc.)
self.addEventListener('fetch', event => {
  event.respondWith(
    // Tenta encontrar o recurso no cache primeiro
    caches.match(event.request)
      .then(response => {
        // Se encontrar no cache, retorna-o
        if (response) {
          return response;
        }
        // Se não encontrar, vai à rede para o obter
        return fetch(event.request);
      })
  );
});
