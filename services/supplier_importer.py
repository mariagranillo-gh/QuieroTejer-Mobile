import os
import sys
import unicodedata
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.queries import get_all_models_for_matching

def normalize_string(s):
    """
    Normaliza una cadena de texto para comparación:
    - Convierte a mayúsculas.
    - Quita acentos y diacríticos.
    - Limpia espacios en blanco extras.
    """
    if pd.isna(s) or s is None:
        return ""
    # Convertir a string, quitar espacios en los extremos y pasar a mayúsculas
    s = str(s).strip().upper()
    # Eliminar acentos utilizando descomposición unicode
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # Quitar espacios múltiples internos
    return ' '.join(s.split())

def clean_decimal(val):
    """
    Limpia y convierte un valor numérico/moneda a float.
    Soporta formato con o sin signo $ y separadores de miles/decimales.
    """
    if pd.isna(val) or val is None:
        return 0.00
    val_str = str(val).strip()
    if not val_str:
        return 0.00
    
    # Quitar símbolo de pesos
    val_str = val_str.replace('$', '').strip()
    
    # Resolver separador de miles y decimales
    if ',' in val_str and '.' in val_str:
        if val_str.find(',') < val_str.find('.'):
            # Formato americano: 3,500.00
            val_str = val_str.replace(',', '')
        else:
            # Formato europeo/latino: 3.500,00
            val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str:
        parts = val_str.split(',')
        if len(parts[-1]) == 2:
            val_str = val_str.replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
            
    try:
        return float(val_str)
    except ValueError:
        return 0.00

def read_supplier_file(filepath):
    """
    Lee archivos del proveedor (CSV o Excel) de manera dinámica.
    Detecta la codificación y delimitador en caso de ser CSV.
    """
    _, ext = os.path.splitext(filepath.lower())
    if ext in ['.xlsx', '.xls']:
        return pd.read_excel(filepath, dtype=str)
    
    # Detección de codificación para CSV
    encoding = 'utf-8'
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            f.read(1024)
    except UnicodeDecodeError:
        encoding = 'latin-1'
        
    # Detección del delimitador del CSV
    with open(filepath, 'r', encoding=encoding) as f:
        first_line = f.readline()
        if ';' in first_line:
            sep = ';'
        else:
            sep = ','
            
    return pd.read_csv(filepath, sep=sep, encoding=encoding, dtype=str)

def parse_and_match_supplier_sheet(filepath):
    """
    Carga y procesa la planilla de un proveedor, intentando emparejar
    cada producto con los modelos locales mediante cruce inteligente:
      1. Coincidencia directa con Nombre de Modelo
      2. Coincidencia con Producto + Presentacion (ej. Cashmilon 4/7 madeja)
    
    Retorna un diccionario clasificado en 'updated', 'no_change' y 'not_found'.
    """
    df = read_supplier_file(filepath)
    
    # Normalizar nombres de columnas a minúsculas
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower().strip()
        if 'producto' in col_lower:
            col_mapping[col] = 'producto'
        elif 'presentacion' in col_lower or 'presentación' in col_lower:
            col_mapping[col] = 'presentacion'
        elif 'precio' in col_lower:
            col_mapping[col] = 'precio'
            
    df.rename(columns=col_mapping, inplace=True)
    
    # Validaciones mínimas
    if 'producto' not in df.columns or 'precio' not in df.columns:
        raise ValueError("El archivo debe contener las columnas 'Producto' y 'Precio'.")
        
    # Obtener modelos de la base de datos
    db_models = get_all_models_for_matching()
    
    # Mapear modelos de la DB por su nombre normalizado para búsquedas rápidas O(1)
    models_by_name = {normalize_string(m['name']): m for m in db_models}
    
    results = {
        'updated': [],       # Coincide y cambia el precio
        'no_change': [],     # Coincide y mantiene el precio
        'not_found': [],     # No se encontró coincidencia
    }
    
    for _, row in df.iterrows():
        prod_raw = row['producto']
        if pd.isna(prod_raw) or not str(prod_raw).strip():
            continue
            
        pres_raw = row['presentacion'] if 'presentacion' in df.columns and not pd.isna(row['presentacion']) else ""
        price_raw = row['precio']
        
        new_price = clean_decimal(price_raw)
        
        # Generar las claves de búsqueda normalizadas
        prod_norm = normalize_string(prod_raw)
        pres_norm = normalize_string(pres_raw)
        
        match_key_1 = prod_norm
        match_key_2 = normalize_string(f"{prod_raw} {pres_raw}")
        
        matched_model = None
        
        # 1. Buscar coincidencia exacta por nombre
        if match_key_1 in models_by_name:
            matched_model = models_by_name[match_key_1]
        # 2. Buscar coincidencia por nombre + presentacion (ej: Cashmilon 4/7 Madeja)
        elif match_key_2 in models_by_name:
            matched_model = models_by_name[match_key_2]
            
        if matched_model:
            model_id = matched_model['id']
            model_name = matched_model['name']
            old_price = float(matched_model['price'])
            
            info = {
                'model_id': model_id,
                'model_name': model_name,
                'old_price': old_price,
                'new_price': new_price,
                'producto_raw': prod_raw,
                'presentacion_raw': pres_raw
            }
            
            if abs(old_price - new_price) > 0.01:
                results['updated'].append(info)
            else:
                results['no_change'].append(info)
        else:
            results['not_found'].append({
                'producto_raw': prod_raw,
                'presentacion_raw': pres_raw,
                'precio_raw': price_raw
            })
            
    return results
