import os
import sys
import re
import unicodedata
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection
from database.queries import get_product_mappings

def normalize_string(s):
    """
    Normaliza una cadena de texto para comparación:
    - Convierte a mayúsculas.
    - Quita acentos y diacríticos.
    - Limpia espacios en blanco extras.
    """
    if pd.isna(s) or s is None:
        return ""
    s = str(s).strip().upper()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split())

def normalize_color(color):
    if not color:
        return ""
    color = normalize_string(color)
    
    # Estandarizar abreviaturas y variantes ortográficas comunes de colores
    color = color.replace("BÉBÉ", "BEBE")
    color = color.replace("TURQUESA", "TURQUEZA")
    
    words = color.split()
    normalized_words = []
    for w in words:
        if w in ("BB", "BEBÉ"):
            normalized_words.append("BEBE")
        elif w == "OSC":
            normalized_words.append("OSCURO")
        elif w == "CL":
            normalized_words.append("CLARO")
        else:
            normalized_words.append(w)
            
    res = " ".join(normalized_words)
    
    # Mapeos específicos de nombres equivalentes
    if res == "ROSA CLARO":
        return "ROSA BEBE"
    if res == "CELESTE CLARO":
        return "CELESTE BEBE"
        
    return res

def strip_prefix_noise(text):
    text = text.strip()
    if not text:
        return text
        
    # Pattern to match noise prefixes at the start of the string repeatedly:
    # 1. Line numbers like "1.", "12.", "1.2."
    # 2. Standalone digits (e.g. "1", "10"), but not fractions (e.g. "2/7")
    # 3. Common packaging or supplier words like "PAQ", "PAQUETE", "HILADO", etc.
    pattern = re.compile(
        r'^(?:'
        r'\d+\.\s*'                                                                           # e.g. "1. ", "12. "
        r'|(?:\d+)(?!\s*/)\b\s*'                                                              # standalone digits but not fractions
        r'|\b(?:PAQ|PAQUETE|PAQUETES|HILADO|HILADOS|BTO|BULTO|BULTOS|CAJA|CAJAS)\b\.?\s*'      # noise words
        r')', 
        re.IGNORECASE
    )
    
    old_text = None
    while text != old_text:
        old_text = text
        text = pattern.sub('', text).strip()
        
    return text

def strip_color_codes(text):
    words = text.split()
    cleaned_words = []
    for w in words:
        is_code = False
        if w.isdigit():
            is_code = True
        elif any(c.isdigit() for c in w) and '/' not in w:
            is_code = True
            
        if not is_code:
            cleaned_words.append(w)
    return " ".join(cleaned_words)

# Lista de palabras de sufijo a remover al final del modelo
MODEL_SUFFIX_PATTERNS = [
    r'\bOVILLO\b',
    r'\bMADEJA\b',
    r'\bMIX\s+MADEJA\b',
    r'\bGRUESO\b',
    r'\bFILA\b',
    r'\bMULTI\b',
]

def get_model_core(model_name):
    core = normalize_string(model_name)
    # Remover patrones de sufijo del final del modelo repetidamente
    old_core = None
    while core != old_core:
        old_core = core
        for pattern in MODEL_SUFFIX_PATTERNS:
            core = re.sub(pattern + r'\s*$', '', core).strip()
    return core

def match_product_by_name(detected_name):
    """
    Intenta emparejar un nombre de producto detectado por OCR/CSV con una variante local.
    Retorna un diccionario con:
      - 'matched': bool (indica si se encontró correspondencia exacta)
      - 'variant_id': int o None
      - 'model_name': str o None
      - 'color_name': str o None
      - 'model_weight': float o None (para conversión de kg a unidades)
      - 'display_name': str o None (formato 'MODELO - COLOR')
    """
    if not detected_name:
        return {'matched': False, 'variant_id': None, 'model_name': None, 'color_name': None, 'model_weight': None, 'display_name': None}
        
    norm_detected = normalize_string(detected_name)
    norm_detected = strip_prefix_noise(norm_detected)
    norm_detected = strip_color_codes(norm_detected)
    
    # 1. Cargar las equivalencias de la base de datos
    mappings = get_product_mappings()
    
    # Ordenar los mapeos por longitud de supplier_name descendente
    # Esto asegura que si tenemos reglas superpuestas (ej: "3/7" y "3/7 FILA"),
    # la más específica ("3/7 FILA") se evalúe y reemplace antes que la general ("3/7").
    mappings = sorted(mappings, key=lambda x: len(str(x.get('supplier_name', ''))), reverse=True)
    
    # Aplicar mapeos: si el supplier_name está presente en la cadena detectada, reemplazamos por el internal_name
    for mapping in mappings:
        sup_norm = normalize_string(mapping['supplier_name'])
        int_norm = normalize_string(mapping['internal_name'])
        
        # Hacemos una coincidencia de palabra completa o prefijo para evitar reemplazar partes de palabras
        if norm_detected.startswith(sup_norm + " "):
            norm_detected = norm_detected.replace(sup_norm, int_norm, 1)
            break
        elif norm_detected == sup_norm:
            norm_detected = int_norm
            break
            
    # 2. Cargar todos los modelos y sus variantes de la base de datos
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT v.id AS variant_id, m.name AS model_name, v.color_name, m.weight
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.is_active = TRUE
        """
        cursor.execute(query)
        db_vars = cursor.fetchall()
    finally:
        conn.close()
        
    if not db_vars:
        return {'matched': False, 'variant_id': None, 'model_name': None, 'color_name': None, 'model_weight': None, 'display_name': None}
        
    # 3. Intentar coincidencia exacta: combinar modelo completo + color
    for row in db_vars:
        model_norm = normalize_string(row['model_name'])
        color_norm = normalize_string(row['color_name'])
        
        combined_1 = normalize_string(f"{model_norm} {color_norm}")
        combined_2 = normalize_string(f"{color_norm} {model_norm}")
        
        if norm_detected == combined_1 or norm_detected == combined_2:
            return {
                'matched': True,
                'variant_id': int(row['variant_id']),
                'model_name': row['model_name'],
                'color_name': row['color_name'],
                'model_weight': float(row['weight']) if row['weight'] else 0.100,
                'display_name': f"{row['model_name']} - {row['color_name']}"
            }

    # 3b. Intentar coincidencia exacta: combinar core del modelo + color
    for row in db_vars:
        model_core = get_model_core(row['model_name'])
        color_norm = normalize_string(row['color_name'])
        
        combined_1 = normalize_string(f"{model_core} {color_norm}")
        combined_2 = normalize_string(f"{color_norm} {model_core}")
        
        if norm_detected == combined_1 or norm_detected == combined_2:
            return {
                'matched': True,
                'variant_id': int(row['variant_id']),
                'model_name': row['model_name'],
                'color_name': row['color_name'],
                'model_weight': float(row['weight']) if row['weight'] else 0.100,
                'display_name': f"{row['model_name']} - {row['color_name']}"
            }
            
    # 4. Coincidencia por prefijo/sufijo del modelo completo con color normalizado:
    best_match = None
    for row in db_vars:
        model_norm = normalize_string(row['model_name'])
        color_norm = normalize_color(row['color_name'])
        
        if norm_detected.startswith(model_norm):
            remainder = norm_detected[len(model_norm):].strip()
            if normalize_color(remainder) == color_norm:
                return {
                    'matched': True,
                    'variant_id': int(row['variant_id']),
                    'model_name': row['model_name'],
                    'color_name': row['color_name'],
                    'model_weight': float(row['weight']) if row['weight'] else 0.100,
                    'display_name': f"{row['model_name']} - {row['color_name']}"
                }
            elif not remainder:
                best_match = {
                    'matched': False,
                    'variant_id': int(row['variant_id']),
                    'model_name': row['model_name'],
                    'color_name': row['color_name'],
                    'model_weight': float(row['weight']) if row['weight'] else 0.100,
                    'display_name': f"{row['model_name']} - {row['color_name']}"
                }
                
        if norm_detected.endswith(model_norm):
            color_part = norm_detected[:-len(model_norm)].strip()
            if normalize_color(color_part) == color_norm:
                return {
                    'matched': True,
                    'variant_id': int(row['variant_id']),
                    'model_name': row['model_name'],
                    'color_name': row['color_name'],
                    'model_weight': float(row['weight']) if row['weight'] else 0.100,
                    'display_name': f"{row['model_name']} - {row['color_name']}"
                }

    # 4b. Coincidencia por prefijo/sufijo del core del modelo con color normalizado:
    for row in db_vars:
        model_core = get_model_core(row['model_name'])
        color_norm = normalize_color(row['color_name'])
        
        if model_core and norm_detected.startswith(model_core):
            remainder = norm_detected[len(model_core):].strip()
            if normalize_color(remainder) == color_norm:
                return {
                    'matched': True,
                    'variant_id': int(row['variant_id']),
                    'model_name': row['model_name'],
                    'color_name': row['color_name'],
                    'model_weight': float(row['weight']) if row['weight'] else 0.100,
                    'display_name': f"{row['model_name']} - {row['color_name']}"
                }
                
        if model_core and norm_detected.endswith(model_core):
            color_part = norm_detected[:-len(model_core)].strip()
            if normalize_color(color_part) == color_norm:
                return {
                    'matched': True,
                    'variant_id': int(row['variant_id']),
                    'model_name': row['model_name'],
                    'color_name': row['color_name'],
                    'model_weight': float(row['weight']) if row['weight'] else 0.100,
                    'display_name': f"{row['model_name']} - {row['color_name']}"
                }

    # Si encontramos una coincidencia parcial de modelo, la retornamos pero marcada como no exacta
    if best_match:
        return best_match
        
    # Si no se encontró nada
    return {'matched': False, 'variant_id': None, 'model_name': None, 'color_name': None, 'model_weight': None, 'display_name': None}
