import os
import sys
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection

# Columnas con valores fijos para todos los productos de QuieroTejer
FIXED_VALUES = {
    "Alto (cm)": 5,
    "Ancho (cm)": 5,
    "Marca": "Quiero Tejer",
    "Sexo": "Unisex",
    "Producto Físico": "SI",
    "Mostrar en tienda": "NO",
    "Nombre de propiedad 1": "COLOR",
}

def build_tags(model_tags, color_name):
    """
    Combina los tags base del modelo con el color del producto en Proper Case.
    Ej: model_tags="Bordo, Lanas, Hilados", color="ROJO PUNZÓ" -> "Bordo, Lanas, Hilados, Rojo Punzó"
    """
    color_proper = color_name.title() if color_name else ""
    if model_tags and str(model_tags).strip():
        return f"{str(model_tags).strip()}, {color_proper}"
    return color_proper

def build_seo_description(base_description, color_name):
    """
    Agrega el color al final de la descripción SEO del modelo en minúsculas.
    Ej: base="Hilado suave...", color="ROJO PUNZÓ" -> "Hilado suave... Color: rojo punzó"
    """
    color_lower = color_name.lower() if color_name else ""
    if base_description and str(base_description).strip():
        base = str(base_description).strip()
        # Evitar duplicar si ya termina con el color
        if not base.endswith(f"Color: {color_lower}"):
            return f"{base} Color: {color_lower}"
        return base
    return f"Color: {color_lower}"


def export_existing_products_custom(csv_path, include_price=True, include_stock=False, include_details=False):
    """
    Genera una planilla de actualización para TiendaNube de productos existentes (tienen url_identifier).
    Permite elegir si exportar Precios, Stock, y/o Detalles (Tags y Descripción).
    """
    conn = get_connection()
    try:
        # Temporarily disable RealDictCursor for pandas
        orig_factory = conn.cursor_factory
        conn.cursor_factory = None
        
        # Recuperar campos necesarios
        query = """
            SELECT v.id, v.url_identifier, v.color_name, m.price, v.stock, m.tags, m.description
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.is_active = TRUE
              AND v.url_identifier IS NOT NULL
              AND v.url_identifier != ''
              AND v.sync_status = 'Pendiente'
        """
        df = pd.read_sql_query(query, conn)
        
        # Restore factory
        conn.cursor_factory = orig_factory

        if df.empty:
            return 0, None
            
        variant_ids = df['id'].tolist()
        df.drop(columns=['id'], inplace=True)

        # Renombrar columnas
        df.rename(columns={
            'url_identifier': 'Identificador de URL',
            'color_name': 'Valor de propiedad 1',
        }, inplace=True)

        df.insert(1, 'Nombre de propiedad 1', 'COLOR')
        
        # Filtrar columnas resultantes según parámetros
        cols_to_keep = ['Identificador de URL', 'Nombre de propiedad 1', 'Valor de propiedad 1']
        
        if include_price:
            df.rename(columns={'price': 'Precio'}, inplace=True)
            cols_to_keep.append('Precio')
            
        if include_stock:
            df.rename(columns={'stock': 'Stock'}, inplace=True)
            cols_to_keep.append('Stock')
            
        if include_details:
            df.rename(columns={'tags': 'Tags', 'description': 'Descripción'}, inplace=True)
            cols_to_keep.extend(['Tags', 'Descripción'])
            
        df = df[cols_to_keep]

        df.to_csv(csv_path, index=False, sep=';', encoding='utf-8-sig')
        
        import datetime
        exec_id = f"EXP-EXT-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Actualizar a Exportado en la DB y limpiar previous_stock
        cursor = conn.cursor()
        placeholders = ",".join(["%s"] * len(variant_ids))
        update_query = f"""
            UPDATE product_variants
            SET sync_status = 'Exportado', execution_id = %s, previous_stock = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
        """
        cursor.execute(update_query, [exec_id] + variant_ids)
        conn.commit()
        
        return len(df), exec_id
    finally:
        conn.close()


def export_new_products(csv_path):
    """
    Genera un Excel completo para dar de alta nuevos modelos o variantes en TiendaNube.
    Toma las variantes con sync_status = 'Pendiente' que aún no tienen url_identifier.
    Aplica lógica dinámica de tags (con color en Proper Case) y SEO description (con color al final).
    Incluye columnas fijas y valores de peso del modelo.
    """
    conn = get_connection()
    try:
        # Temporarily disable RealDictCursor for pandas
        orig_factory = conn.cursor_factory
        conn.cursor_factory = None
        
        query = """
            SELECT v.id AS variant_id, v.product_model_id, m.name AS model_name, m.category,
                   v.color_name, m.price, v.stock, v.mpn_comment, m.description,
                   m.tags, m.seo_title, m.seo_description, m.weight,
                   v.url_identifier
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE (v.url_identifier IS NULL OR v.url_identifier = '')
              AND v.sync_status = 'Pendiente'
        """
        new_variants = pd.read_sql_query(query, conn)
        
        # Restore factory
        conn.cursor_factory = orig_factory

        if new_variants.empty:
            return 0, None

        import datetime
        exec_id = f"EXP-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
        cursor = conn.cursor()

        # Columnas estándar de TiendaNube en el orden oficial
        columns = [
            "Identificador de URL", "Nombre", "Categorías",
            "Nombre de propiedad 1", "Valor de propiedad 1",
            "Nombre de propiedad 2", "Valor de propiedad 2",
            "Nombre de propiedad 3", "Valor de propiedad 3",
            "Precio", "Precio promocional", "Peso (kg)",
            "Alto (cm)", "Ancho (cm)", "Profundidad (cm)",
            "Stock", "SKU", "Código de barras", "Mostrar en tienda",
            "Envío sin cargo", "Descripción", "Tags",
            "Título para SEO", "Descripción para SEO", "Marca",
            "Producto Físico", "MPN (Número de pieza del fabricante)",
            "Sexo", "Rango de edad", "Costo"
        ]

        data = []
        for i, (_, row) in enumerate(new_variants.iterrows()):
            color = str(row["color_name"]).strip() if row["color_name"] else ""
            model_name = str(row["model_name"]).strip()
            
            # Generar Identificador de URL único combinando Modelo + Color
            import re
            import unicodedata
            raw_handle_name = f"{model_name} {color}".strip().lower()
            normalized_name = ''.join(c for c in unicodedata.normalize('NFD', raw_handle_name) if unicodedata.category(c) != 'Mn')
            custom_handle = re.sub(r'[^a-z0-9]+', '-', normalized_name)
            custom_handle = re.sub(r'-+', '-', custom_handle).strip('-')
            
            row_dict = {col: "" for col in columns}

            row_dict["Identificador de URL"] = custom_handle
            row_dict["Nombre"] = model_name
            row_dict["Categorías"] = row["category"] if row["category"] else ""
            row_dict["Nombre de propiedad 1"] = "COLOR"
            row_dict["Valor de propiedad 1"] = color
            row_dict["Precio"] = row["price"]
            row_dict["Peso (kg)"] = row["weight"] if row["weight"] else 0.100

            # Columnas fijas del negocio
            row_dict["Alto (cm)"] = 5
            row_dict["Ancho (cm)"] = 5
            row_dict["Marca"] = "Quiero Tejer"
            row_dict["Sexo"] = "Unisex"
            row_dict["Producto Físico"] = "SI"
            row_dict["Mostrar en tienda"] = "NO"

            row_dict["Stock"] = row["stock"] if row["stock"] else 0
            row_dict["Descripción"] = row["description"] if row["description"] else ""

            # Tags dinámicos: tags del modelo + color en Proper Case
            row_dict["Tags"] = build_tags(row["tags"], color)

            # SEO Title directo del modelo
            row_dict["Título para SEO"] = row["seo_title"] if row["seo_title"] else ""

            # SEO Description: texto del modelo + "Color: <color en minúsculas>"
            row_dict["Descripción para SEO"] = build_seo_description(row["seo_description"], color)

            row_dict["MPN (Número de pieza del fabricante)"] = row["mpn_comment"] if row["mpn_comment"] else ""

            # Costo y SKU quedan vacíos
            row_dict["SKU"] = ""
            row_dict["Costo"] = ""

            data.append(row_dict)
            
            # Guardar el url_identifier generado en la base de datos local y marcar como exportado
            cursor.execute("""
                UPDATE product_variants
                SET url_identifier = %s, sync_status = 'Exportado', execution_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (custom_handle, exec_id, row["variant_id"]))

        export_df = pd.DataFrame(data, columns=columns)
        export_df.to_csv(csv_path, index=False, sep=';', encoding='utf-8-sig')
        
        conn.commit()
        return len(export_df), exec_id
    finally:
        conn.close()
