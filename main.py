from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import httpx
import base64
import io
from PIL import Image
import logging
from datetime import datetime
import os

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de la API
app = FastAPI(title="OCR API con OpenRouter", version="1.0.0")

# Configurar CORS para permitir solicitudes desde tu aplicación Flet
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clave de API de OpenRouter (en producción, usar variables de entorno)
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Clave de acceso para proteger el endpoint (en producción, usar variables de entorno)
ACCESS_KEY = "ocr_secreta_2024"  # Cambia esto por una clave segura

# Modelo de respuesta
class OCRResponse(BaseModel):
    texto: str
    modelo: str
    timestamp: str

def comprimir_imagen(imagen_bytes: bytes, max_kb=1024) -> bytes:
    """
    Comprime la imagen progresivamente hasta que pese menos de max_kb.
    Devuelve los bytes de la imagen comprimida.
    """
    try:
        # Convertir bytes a imagen PIL
        img = Image.open(io.BytesIO(imagen_bytes))
        
        # Convertir a RGB si es necesario
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Calcular tamaño actual
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        tamaño_kb = len(buffer.getvalue()) / 1024
        
        if tamaño_kb <= max_kb:
            return buffer.getvalue()
        
        # Comprimir progresivamente
        calidad = 90
        for intento in range(10):
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", optimize=True, quality=calidad)
            tamaño_kb = len(buffer.getvalue()) / 1024
            if tamaño_kb <= max_kb:
                return buffer.getvalue()
            calidad -= 10
        
        # Si no se logra comprimir, devolver la última versión
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Error al comprimir imagen: {str(e)}")
        return imagen_bytes  # Devolver la imagen original si falla la compresión

@app.get("/")
async def root():
    return {"message": "OCR API con OpenRouter", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/ocr", response_model=OCRResponse)
async def ocr_endpoint(
    file: UploadFile = File(...),
    access_key: str = Header(None, alias="X-API-Key")
):
    """
    Endpoint para procesar una imagen y extraer texto usando OpenRouter.
    Requiere una clave de acceso en el header X-API-Key.
    """
    # Verificar clave de acceso
    if access_key != ACCESS_KEY:
        raise HTTPException(status_code=401, detail="Clave de acceso inválida")
    
    # Verificar que el archivo es una imagen
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")
    
    try:
        # Registrar la solicitud
        logger.info(f"Procesando imagen: {file.filename} ({file.content_type})")
        
        # Leer el archivo de imagen
        imagen_bytes = await file.read()
        
        # Comprimir la imagen
        imagen_comprimida = comprimir_imagen(imagen_bytes)
        
        # Convertir a base64
        encoded_string = base64.b64encode(imagen_comprimida).decode('utf-8')
        
        # Preparar la solicitud a OpenRouter
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tu-dominio.com",  # Reemplaza con tu dominio
            "X-Title": "OCR App"
        }
        
        payload = {
            "model": "openai/gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extrae todo el texto visible en esta imagen. Devuelve únicamente el texto sin ningún comentario adicional."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_string}"
                            }
                        }
                    ]
                }
            ]
        }
        
        # Enviar solicitud a OpenRouter
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
        
        # Extraer el texto de la respuesta
        if 'choices' in result and len(result['choices']) > 0:
            texto_extraido = result['choices'][0]['message']['content'].strip()
            modelo_usado = result.get('model', 'desconocido')
            
            # Registrar éxito
            logger.info(f"OCR exitoso para {file.filename}. Longitud del texto: {len(texto_extraido)}")
            
            return OCRResponse(
                texto=texto_extraido,
                modelo=modelo_usado,
                timestamp=datetime.now().isoformat()
            )
        else:
            logger.error(f"Respuesta inesperada de OpenRouter: {result}")
            raise HTTPException(status_code=500, detail="Respuesta inesperada de la API de OpenRouter")
            
    except httpx.RequestError as e:
        logger.error(f"Error de conexión con OpenRouter: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error de conexión con OpenRouter: {str(e)}")
    except Exception as e:
        logger.error(f"Error procesando OCR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error procesando OCR: {str(e)}")

