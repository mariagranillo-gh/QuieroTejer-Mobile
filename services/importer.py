import os
import sys
import pandas as pd
import psycopg2

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection

def clean_decimal(val):
    """
    Limpia y convierte un valor decimal del CSV (que puede venir con formato de miles/decimales europeo o americano)
    a un número flotante estándar de Python.
    """
    if pd.isna(val) or val is None:
        return 0.00
    val_str = str(val).strip()
    if not val_str:
        return 0.00
    
    # Quitar símbolos de moneda si existen
    val_str = val_str.replace('$', '').strip()
    
    # Caso 1: Tiene tanto coma como punto (ej: 3,690.00 o 3.690,00)
    if ',' in val_str and '.' in val_str:
        # Si la coma aparece antes del punto (formato americano: 3,690.00)
        if val_str.find(',') < val_str.find('.'):
            val_str = val_str.replace(',', '')
        else:
            # Formato europeo/latino: 3.690,00
            val_str = val_str.replace('.', '').replace(',', '.')
    # Caso 2: Solo tiene coma (ej: 3690,00 o 3,690)
    elif ',' in val_str:
        # Si tiene 2 decimales después de la coma, asumimos que es separador decimal
        parts = val_str.split(',')
        if len(parts[-1]) == 2:
            val_str = val_str.replace(',', '.')
        else:
            # Si no, asumimos que es separador de miles
            val_str = val_str.replace(',', '')
    
    try:
        return float(val_str)
    except ValueError:
        return 0.00

def import_csv(csv_path):
    """
    Lee el archivo CSV de TiendaNube y realiza un upsert de los modelos y variantes en SQLite.
    Retorna un diccionario con estadísticas de la importación.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"No se encontró el archivo: {csv_path}")

    # Determinar codificación
    encoding = 'utf-8'
    try:
        # Intentar leer una porción pequeña en UTF-8
        with open(csv_path, 'r', encoding='utf-8') as f:
            f.read(1024)
    except UnicodeDecodeError:
        encoding = 'latin-1'

    # Leer el CSV usando pandas
    df = pd.read_csv(csv_path, sep=';', encoding=encoding, dtype=str)

    # Normalizar nombres de columnas mapeándolas de forma insensible a mayúsculas y acentos
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower == 'nombre':
            col_mapping[col] = 'nombre'
        elif col_lower == 'precio':
            col_mapping[col] = 'precio'
        elif col_lower == 'costo':
            col_mapping[col] = 'costo'
        elif col_lower == 'stock':
            col_mapping[col] = 'stock'
        elif col_lower == 'sku':
            col_mapping[col] = 'sku'
        elif col_lower in ['categorías', 'categorias', 'categoría', 'categoria']:
            col_mapping[col] = 'categoria'
        elif col_lower == 'identificador de url':
            col_mapping[col] = 'url_identifier'
        elif col_lower == 'valor de propiedad 1':
            col_mapping[col] = 'color'
        elif 'mpn' in col_lower:
            col_mapping[col] = 'mpn'
        elif col_lower in ['descripción', 'descripcin', 'descripcion']:
            col_mapping[col] = 'descripcion'
        elif col_lower == 'tags':
            col_mapping[col] = 'tags'
        elif col_lower in ['título para seo', 'titulo para seo']:
            col_mapping[col] = 'seo_title'
        elif col_lower in ['descripción para seo', 'descripcin para seo', 'descripcion para seo']:
            col_mapping[col] = 'seo_description'
        elif col_lower in ['peso (kg)', 'peso']:
            col_mapping[col] = 'weight'

    df.rename(columns=col_mapping, inplace=True)

    # Validar columnas requeridas
    required_cols = ['nombre', 'precio', 'color', 'url_identifier']
    for rc in required_cols:
        if rc not in df.columns:
            raise ValueError(f"El CSV no contiene la columna requerida o mapeable: {rc}")

    conn = get_connection()
    cursor = conn.cursor()

    stats = {
        'modelos_nuevos': 0,
        'modelos_actualizados': 0,
        'variantes_nuevas': 0,
        'variantes_actualizadas': 0,
        'total_filas_procesadas': 0
    }

    try:
        from psycopg2.extras import execute_values

        # --- Detección y registro de duplicados ---
        cursor.execute("DELETE FROM detected_duplicates")
        df_temp = df.copy()
        df_temp['nombre_norm'] = df_temp['nombre'].fillna('').str.strip().str.upper()
        df_temp['color_norm'] = df_temp['color'].fillna('ÚNICO').str.strip().str.upper()
        
        dup_mask = df_temp.duplicated(subset=['nombre_norm', 'color_norm'], keep=False)
        df_dups = df[dup_mask].copy()
        
        if not df_dups.empty:
            dup_tuples = []
            for _, row in df_dups.iterrows():
                model_name_val = str(row['nombre']).strip()
                color_name_val = str(row['color']).strip() if 'color' in df.columns and not pd.isna(row['color']) else 'Único'
                sku_val = str(row['sku']).strip() if 'sku' in df.columns and not pd.isna(row['sku']) else None
                try:
                    stock_val = int(float(str(row['stock']).strip())) if 'stock' in df.columns and not pd.isna(row['stock']) else 0
                except ValueError:
                    stock_val = 0
                url_id_val = str(row['url_identifier']).strip() if 'url_identifier' in df.columns and not pd.isna(row['url_identifier']) else None
                dup_tuples.append((model_name_val, color_name_val, sku_val, stock_val, url_id_val))

            insert_dups_query = """
                INSERT INTO detected_duplicates (model_name, color_name, sku, stock, url_identifier)
                VALUES %s
            """
            execute_values(cursor, insert_dups_query, dup_tuples)

        # --- 1. PROCESAR MODELOS EN LOTE ---
        unique_models = {}
        for _, row in df.iterrows():
            stats['total_filas_procesadas'] += 1
            name = str(row['nombre']).strip()
            if not name or pd.isna(row['nombre']):
                continue
            if name not in unique_models:
                unique_models[name] = {
                    'name': name,
                    'category': str(row['categoria']).strip() if 'categoria' in df.columns and not pd.isna(row['categoria']) else None,
                    'description': str(row['descripcion']).strip() if 'descripcion' in df.columns and not pd.isna(row['descripcion']) else None,
                    'price': clean_decimal(row['precio']),
                    'cost': clean_decimal(row['costo']) if 'costo' in df.columns else 0.00,
                    'tags': str(row['tags']).strip() if 'tags' in df.columns and not pd.isna(row['tags']) else None,
                    'seo_title': str(row['seo_title']).strip() if 'seo_title' in df.columns and not pd.isna(row['seo_title']) else None,
                    'seo_description': str(row['seo_description']).strip() if 'seo_description' in df.columns and not pd.isna(row['seo_description']) else None,
                    'weight': clean_decimal(row['weight']) if 'weight' in df.columns else 0.100
                }

        if unique_models:
            # Consultar qué modelos ya existen para calcular estadísticas correctas
            cursor.execute("SELECT id, name FROM product_models WHERE name IN %s", (tuple(unique_models.keys()),))
            existing_models = {r['name']: r['id'] for r in cursor.fetchall()}
            
            for m_name in unique_models.keys():
                if m_name in existing_models:
                    stats['modelos_actualizados'] += 1
                else:
                    stats['modelos_nuevos'] += 1

            # Ejecutar UPSERT masivo de modelos
            model_tuples = [
                (m['name'], m['category'], m['price'], m['cost'], m['description'], m['tags'], m['seo_title'], m['seo_description'], m['weight'])
                for m in unique_models.values()
            ]
            
            upsert_models_query = """
                INSERT INTO product_models (name, category, price, cost, description, tags, seo_title, seo_description, weight)
                VALUES %s
                ON CONFLICT (name) DO UPDATE SET
                    category = EXCLUDED.category,
                    price = EXCLUDED.price,
                    cost = EXCLUDED.cost,
                    description = EXCLUDED.description,
                    tags = EXCLUDED.tags,
                    seo_title = EXCLUDED.seo_title,
                    seo_description = EXCLUDED.seo_description,
                    weight = EXCLUDED.weight
            """
            execute_values(cursor, upsert_models_query, model_tuples)

            # Volver a mapear todos los modelos (nuevos y existentes) a sus IDs en la base de datos
            cursor.execute("SELECT id, name FROM product_models WHERE name IN %s", (tuple(unique_models.keys()),))
            model_id_map = {r['name']: r['id'] for r in cursor.fetchall()}
        else:
            model_id_map = {}

        # --- 2. PROCESAR VARIANTES EN LOTE ---
        if model_id_map:
            # Obtener variantes existentes para los modelos involucrados
            cursor.execute("SELECT id, product_model_id, color_name FROM product_variants WHERE product_model_id IN %s", (tuple(model_id_map.values()),))
            existing_variants = {(r['product_model_id'], r['color_name']): r['id'] for r in cursor.fetchall()}

            variant_tuples = []
            seen_variants = set() # Evitar insertar duplicados en el mismo lote si el CSV los trae repetidos
            
            for _, row in df.iterrows():
                model_name = str(row['nombre']).strip()
                if not model_name or pd.isna(row['nombre']) or model_name not in model_id_map:
                    continue
                model_id = model_id_map[model_name]
                color_name = str(row['color']).strip() if 'color' in df.columns and not pd.isna(row['color']) else 'Único'
                
                # Evitar colisión de llave primaria en el lote de datos a insertar
                v_key = (model_id, color_name)
                if v_key in seen_variants:
                    continue
                seen_variants.add(v_key)

                sku = str(row['sku']).strip() if 'sku' in df.columns and not pd.isna(row['sku']) else None
                url_id = str(row['url_identifier']).strip() if 'url_identifier' in df.columns and not pd.isna(row['url_identifier']) else None
                
                try:
                    stock = int(float(str(row['stock']).strip())) if 'stock' in df.columns and not pd.isna(row['stock']) else 0
                except ValueError:
                    stock = 0

                mpn = str(row['mpn']).strip() if 'mpn' in df.columns and not pd.isna(row['mpn']) else None
                is_active = True
                if mpn and "baja" in mpn.lower():
                    is_active = False

                if v_key in existing_variants:
                    stats['variantes_actualizadas'] += 1
                else:
                    stats['variantes_nuevas'] += 1

                variant_tuples.append((model_id, color_name, sku, stock, url_id, mpn, is_active))

            if variant_tuples:
                upsert_variants_query = """
                    INSERT INTO product_variants (product_model_id, color_name, sku, stock, url_identifier, mpn_comment, is_active)
                    VALUES %s
                    ON CONFLICT (product_model_id, color_name) DO UPDATE SET
                        sku = EXCLUDED.sku,
                        stock = EXCLUDED.stock,
                        url_identifier = EXCLUDED.url_identifier,
                        mpn_comment = EXCLUDED.mpn_comment,
                        is_active = EXCLUDED.is_active,
                        updated_at = CURRENT_TIMESTAMP
                """
                execute_values(cursor, upsert_variants_query, variant_tuples)

        conn.commit()
        return stats
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    # Script para correr desde consola
    csv_file = "tiendanube-20260531.csv"
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    
    print(f"Iniciando importación desde {csv_file}...")
    try:
        res = import_csv(csv_file)
        print("\n¡Importación completada con éxito!")
        print(f"Total filas procesadas: {res['total_filas_procesadas']}")
        print(f"Modelos nuevos creados: {res['modelos_nuevos']}")
        print(f"Modelos existentes actualizados: {res['modelos_actualizados']}")
        print(f"Variantes de color nuevas: {res['variantes_nuevas']}")
        print(f"Variantes de color actualizadas: {res['variantes_actualizadas']}")
    except Exception as ex:
        print(f"Error durante la importación: {ex}")
