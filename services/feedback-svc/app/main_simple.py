from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title='feedback-svc', version='0.1.0', docs_url='/docs', openapi_url='/openapi.json')

@app.get('/health')
def health():
    return JSONResponse({'status': 'ok', 'service': 'feedback-svc'})

@app.get('/')
def root():
    return {"message": "Feedback Service is running"}
