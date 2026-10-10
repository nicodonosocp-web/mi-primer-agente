"""Sesiones locales y confirmaciones de un solo uso para el servidor personal."""
import secrets
import threading
import time
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

_sessions = {}
_lock = threading.RLock()
TTL = 8 * 3600

def instalar_seguridad(app):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]'])

    @app.middleware('http')
    async def proteger(request: Request, call_next):
        from urllib.parse import urlsplit
        origin = request.headers.get('origin')
        expected = (request.url.scheme, request.url.netloc)
        if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != expected:
            return JSONResponse({'ok': False, 'error': 'Origen no autorizado.'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'ok': False, 'error': 'Origen no autorizado.'}, status_code=403)
        sid = request.cookies.get('grifo_session', '')
        now = time.time()
        with _lock:
            for key in list(_sessions):
                if _sessions[key]['expires'] < now:
                    del _sessions[key]
            session = _sessions.get(sid)
        public = request.url.path in {'/', '/session', '/health'}
        if not public:
            if not session:
                return JSONResponse({'ok': False, 'error': 'Abre GRIFO para iniciar sesión local.'}, status_code=401)
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not secrets.compare_digest(request.headers.get('x-grifo-csrf', ''), session['csrf']):
                return JSONResponse({'ok': False, 'error': 'Confirmación de sesión inválida.'}, status_code=403)
        request.state.grifo_session = sid
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/session')
    def session(request: Request):
        sid = request.cookies.get('grifo_session', '')
        with _lock:
            value = _sessions.get(sid)
            if not value:
                if len(_sessions) >= 200:
                    return JSONResponse({'error': 'Demasiadas sesiones locales.'}, status_code=429)
                sid = secrets.token_urlsafe(32)
                value = {'csrf': secrets.token_urlsafe(32), 'expires': time.time() + TTL}
                _sessions[sid] = value
        response = JSONResponse({'csrf': value['csrf']})
        response.set_cookie('grifo_session', sid, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=TTL)
        return response
