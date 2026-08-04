import os
import json
import google.generativeai as genai
from PIL import Image
from database.queries import get_config_value

def run_gemini_ocr(uploaded_file, mime_type, api_key=None):
    """
    Llama a Gemini para extraer productos y cantidades.
    Soporta imágenes (PNG/JPG) y PDFs.
    """
    if not api_key:
        api_key = get_config_value('GeminiAPIKey') or os.environ.get('GEMINI_API_KEY')
        
    if not api_key:
        raise ValueError(
            "Falta configurar la API Key de Gemini. "
            "Podés ingresarla en el campo de configuración o definir la variable de entorno GEMINI_API_KEY."
        )
        
    genai.configure(api_key=api_key)
    
    # Usamos gemini-2.5-flash ya que es rápido, multimodal y excelente para OCR
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = """
    Analiza la siguiente imagen o documento (remito, factura o nota manuscrita) y extrae de forma estructurada los movimientos de stock de los productos.
    
    INSTRUCCIONES DE EXTRACCIÓN Y LIMPIEZA:
    1. Si el documento contiene una tabla con columnas:
       - Identifica la columna de descripción del producto (suele llamarse "Descripción", "Artículo", "Detalle", "Producto", "Concepto").
       - Extrae el nombre del producto de esa columna de descripción.
       - NO incluyas en "producto_detectado" las cantidades de otras columnas (como "Cantidad", "Bultos", "Paquetes"), ni palabras de empaque (ej. "Paq.", "Hilado", "Bto.", "Paquete", "Caja"), ni números de fila o ítem (ej. "1.", "1").
    2. El título o modelo del producto (ej. "2/7 OVILLOS MIA" o "4/7 OVILLOS MIA" o "COTTON SENSE") es fundamental. Asegúrate de incluir la fracción o medida del modelo si aparece en la descripción (ej. "2/7", "4/7", "8/6"). Nunca omitas estas fracciones de medida.
    3. Si al final de la descripción aparece un código de color (ej. "M001", "M050", "M059") o un nombre de color (ej. "CRUDO", "NEGRO", "ROSA"), inclúyelo también en "producto_detectado".
    4. TABLAS CON ENCABEZADOS DE SECCIÓN / AGRUPACIONES:
       - Si el documento tiene la descripción agrupada bajo encabezados de sección que indican el nombre del modelo del producto (ej. "DOLLY COTTON 8/3", "2/7 OVILLOS MIA", "CASHMILON 2/7") y debajo de ese encabezado se listan las filas de colores o códigos (ej. "M002 BLANCO", "M050 NEGRO"), debes ANTEPONER el modelo/encabezado de sección al color/código de cada fila correspondiente.
       - Cada fila en la lista JSON final debe ser autocontenida y tener el modelo y el color completo (ej. "DOLLY COTTON 8/3 M002 BLANCO"). Nunca devuelvas un "producto_detectado" que contenga únicamente el color o código sin el modelo principal del producto al que pertenece.
    
    Ejemplos de limpieza esperada de descripciones:
    - Entrada en fila simple: "1 Paq. Hilado 2/7 OVILLOS MIA M001 CRUDO" -> "producto_detectado": "2/7 OVILLOS MIA M001 CRUDO"
    - Entrada en fila simple: "1 Paq. Hilado COTTON SENSE OVILLOS M050 NEGRO" -> "producto_detectado": "COTTON SENSE OVILLOS M050 NEGRO"
    - Entrada en fila simple: "4/7 OVILLOS MIA M059 ROCA" -> "producto_detectado": "4/7 OVILLOS MIA M059 ROCA"
    - Entrada en formato de tabla agrupada:
      ```
      DOLLY COTTON 8/3
      1 Paq. M002 BLANCO    10
      1 Paq. M050 NEGRO     5
      ```
      -> Debe extraerse como:
      [
        {"producto_detectado": "DOLLY COTTON 8/3 M002 BLANCO", "cantidad": 10},
        {"producto_detectado": "DOLLY COTTON 8/3 M050 NEGRO", "cantidad": 5}
      ]
      
    FORMATO DE SALIDA:
    Debes devolver el resultado estrictamente en formato JSON como una lista de objetos. Cada objeto debe tener los siguientes campos:
    - "producto_detectado": El nombre del producto limpio con su color/variante y fracción de modelo (ej. "2/7 OVILLOS MIA M001 CRUDO").
    - "cantidad": El número de cantidad (positivo o negativo) detectado (ej. 3, -10). Si no se especifica signo en remitos, asume que es positivo. Si es una nota manuscrita, respeta el signo.
    
    JSON Esperado:
    [
      {"producto_detectado": "2/7 OVILLOS MIA M001 CRUDO", "cantidad": 3},
      {"producto_detectado": "COTTON SENSE OVILLOS M050 NEGRO", "cantidad": 5}
    ]
    
    No incluyas explicaciones ni formato markdown fuera del JSON (no uses bloques de código ```json). Devuelve únicamente el JSON válido.
    """
    
    # Procesar archivo según tipo
    if mime_type.startswith('image/'):
        # Cargar con PIL
        img = Image.open(uploaded_file)
        response = model.generate_content(
            [prompt, img],
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
    elif mime_type == 'application/pdf':
        # Reset file pointer just in case
        uploaded_file.seek(0)
        pdf_bytes = uploaded_file.read()
        response = model.generate_content(
            [
                prompt,
                {
                    "mime_type": "application/pdf",
                    "data": pdf_bytes
                }
            ],
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
    else:
        raise ValueError(f"Tipo de archivo no soportado para OCR: {mime_type}")
        
    resp_text = response.text.strip()
    
    # Si viene envuelto en markdown json blocks, removerlos
    if resp_text.startswith("```"):
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[-1].split("```")[0].strip()
        else:
            resp_text = resp_text.split("```")[-1].split("```")[0].strip()
        
    try:
        data = json.loads(resp_text)
        return data
    except json.JSONDecodeError as je:
        raise ValueError(f"La IA no devolvió un JSON válido. Respuesta obtenida: {resp_text}")
