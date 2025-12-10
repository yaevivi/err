from fastapi import FastAPI, File, UploadFile, HTTPException
import requests
import base64
import io
from PIL import Image
import os

app = FastAPI()

# Configuración de OpenRouter
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def comprimir_imagen(imagen_bytes: bytes, max_kb=1024) -> bytes:
    """
    Comprime la imagen progresivamente hasta que pese menos de max_kb.
    Devuelve los bytes de la imagen comprimida.
    """
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

@app.post("/ocr")
async def ocr_endpoint(file: UploadFile = File(...)):
    try:
        # Leer el archivo de imagen
        imagen_bytes = await file.read()
        
        # Comprimir la imagen
        imagen_comprimida = comprimir_imagen(imagen_bytes)
        
        # Convertir a base64
        encoded_string = base64.b64encode(imagen_comprimida).decode('utf-8')
        
        # Preparar la solicitud a OpenRouter
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
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
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        
        # Extraer el texto de la respuesta
        if 'choices' in result and len(result['choices']) > 0:
            texto_extraido = result['choices'][0]['message']['content'].strip()
            return {"texto": texto_extraido}
        else:
            raise HTTPException(status_code=500, detail="Respuesta inesperada de la API de OpenRouter")
            
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión con OpenRouter: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando OCR: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)