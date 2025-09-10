from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title='mcp-server', version='0.1.0', docs_url='/docs', openapi_url='/openapi.json')

@app.get('/health')
def health():
    return JSONResponse({'status': 'ok', 'service': 'mcp-server'})
