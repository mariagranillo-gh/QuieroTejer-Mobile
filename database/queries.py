import psycopg2
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import get_connection

def get_dashboard_stats(min_stock=0):
    """
    Retorna estadísticas resumidas de la base de datos para la pantalla principal.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Modelos activos: modelos que tienen al menos una variante activa
        cursor.execute("""
            SELECT COUNT(DISTINCT product_model_id) 
            FROM product_variants 
            WHERE is_active = TRUE
        """)
        modelos_activos = cursor.fetchone()['count'] or 0

        # Variaciones activas: total de variantes activas
        cursor.execute("SELECT COUNT(*) as count FROM product_variants WHERE is_active = TRUE")
        variaciones_activas = cursor.fetchone()['count'] or 0

        # Stock faltante: variantes activas con stock <= min_stock
        cursor.execute("SELECT COUNT(*) as count FROM product_variants WHERE stock <= %s AND is_active = TRUE", (min_stock,))
        stock_faltante = cursor.fetchone()['count'] or 0

        return {
            "modelos_activos": modelos_activos,
            "variaciones_activas": variaciones_activas,
            "stock_faltante": stock_faltante
        }
    finally:
        conn.close()

def get_stock_faltante_list(min_stock=10, operator='>='):
    """
    Retorna la lista de variantes activas filtradas por stock según el operador (>= o <=),
    excluyendo variantes dadas de baja (con mpn_comment) y ordenando alfabéticamente por modelo y color.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        op = ">=" if str(operator).strip() == ">=" else "<="
        cursor.execute(f"""
            SELECT m.name AS model_name, v.color_name, m.price, v.stock, COALESCE(m.weight, 0.100) AS weight
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.stock {op} %s 
              AND v.is_active = TRUE
              AND (v.mpn_comment IS NULL OR TRIM(v.mpn_comment) = '')
            ORDER BY m.name ASC, v.color_name ASC
        """, (min_stock,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_categories():
    """
    Retorna la lista de categorías únicas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT category 
            FROM product_models 
            WHERE category IS NOT NULL AND category != '' 
            ORDER BY category
        """)
        return [row['category'] for row in cursor.fetchall()]
    finally:
        conn.close()

def get_catalog_models(search_query=None, category=None, show_active='Activos'):
    """
    Retorna los modelos de producto según los filtros aplicados.
    
    show_active puede ser:
      - 'Activos': Modelos con al menos una variante activa
      - 'De Baja / Inactivos': Modelos donde todas sus variantes son inactivas
      - 'Todos': Todos los modelos registrados
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT m.* FROM product_models m"
        params = []
        conditions = []

        if category:
            conditions.append("m.category = %s")
            params.append(category)

        if search_query:
            conditions.append("(m.name ILIKE %s OR m.description ILIKE %s)")
            params.append(f"%{search_query}%")
            params.append(f"%{search_query}%")

        if show_active == 'Activos':
            conditions.append("""
                EXISTS (
                    SELECT 1 FROM product_variants v 
                    WHERE v.product_model_id = m.id AND v.is_active = TRUE
                )
            """)
        elif show_active == 'De Baja / Inactivos':
            conditions.append("""
                NOT EXISTS (
                    SELECT 1 FROM product_variants v 
                    WHERE v.product_model_id = m.id AND v.is_active = TRUE
                )
            """)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY m.name"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_variants_for_model(model_id):
    """
    Retorna todas las variantes asociadas a un modelo.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, color_name, sku, stock, url_identifier, mpn_comment, is_active, sync_status
            FROM product_variants
            WHERE product_model_id = %s
            ORDER BY color_name
        """, (model_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def update_model_details(model_id, price, tags, description):
    """
    Actualiza el precio, tags y descripción de un modelo y marca sus variantes como Pendientes de exportar.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE product_models 
            SET price = %s, tags = %s, description = %s
            WHERE id = %s
        """, (price, tags, description, model_id))
        
        # Al cambiar el precio del modelo, encolamos las variantes en Staging (Pendiente)
        cursor.execute("""
            UPDATE product_variants
            SET sync_status = 'Pendiente', 
                previous_stock = COALESCE(previous_stock, stock), 
                execution_id = NULL, 
                updated_at = CURRENT_TIMESTAMP
            WHERE product_model_id = %s
        """, (model_id,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def create_model(name, category, price, cost=0.00, description=None, tags=None, seo_title=None, seo_description=None, weight=0.100):
    """
    Crea un nuevo modelo en la base de datos con los nuevos campos de SEO, Tags y Peso.
    Retorna el ID del modelo insertado.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO product_models (name, category, price, cost, description, tags, seo_title, seo_description, weight)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, category, price, cost, description, tags, seo_title, seo_description, weight))
        model_id = cursor.fetchone()['id']
        conn.commit()
        return model_id
    except psycopg2.IntegrityError:
        raise ValueError(f"El modelo '{name}' ya existe en el catálogo.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def create_variant(model_id, color_name, mpn_comment=None, stock=0):
    """
    Crea una nueva variante (color) para un modelo.
    Nace con sync_status = 'Pendiente'.
    Evalúa si la variante debe ser inactiva de acuerdo al mpn_comment.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        is_active = True
        if mpn_comment and ("baja" in mpn_comment.lower() or "test" in mpn_comment.lower()):
            is_active = False

        # SKU y URL son nulos de manera predeterminada para evitar autogeneración local
        cursor.execute("""
            INSERT INTO product_variants (product_model_id, color_name, sku, stock, url_identifier, mpn_comment, is_active, sync_status)
            VALUES (%s, %s, NULL, %s, NULL, %s, %s, 'Pendiente')
            RETURNING id
        """, (model_id, color_name, stock, mpn_comment, is_active))
        variant_id = cursor.fetchone()['id']
        conn.commit()
        return variant_id
    except psycopg2.IntegrityError:
        raise ValueError(f"El color '{color_name}' ya está registrado para este modelo.")
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_variant_details(variant_id, is_active, mpn_comment=None, stock=0):
    """
    Actualiza el estado de actividad, información de MPN y stock de una variante y la encola como Pendiente.
    Guarda el stock anterior en previous_stock para control en Staging.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Obtener stock actual de la DB
        cursor.execute("SELECT stock, previous_stock, sync_status FROM product_variants WHERE id = %s", (variant_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Variante no encontrada.")
            
        current_db_stock = row['stock'] or 0
        current_prev_stock = row['previous_stock']
        current_sync_status = row['sync_status']
        
        # Si ya está en staging (Pendiente) y previous_stock no es NULL, conservamos el previous_stock original
        if current_sync_status == 'Pendiente' and current_prev_stock is not None:
            new_prev_stock = current_prev_stock
        else:
            new_prev_stock = current_db_stock
            
        cursor.execute("""
            UPDATE product_variants
            SET is_active = %s, 
                mpn_comment = %s, 
                stock = %s, 
                previous_stock = %s,
                sync_status = 'Pendiente', 
                execution_id = NULL, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (is_active, mpn_comment, stock, new_prev_stock, variant_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_staging_variants(status='Pendiente'):
    """
    Trae las variantes de staging de acuerdo a su estado de sincronización (Pendiente, Exportado, Error, Todos).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT v.id AS variant_id, v.execution_id, m.name AS model_name, v.color_name, m.price, v.stock, v.previous_stock, v.sync_status, v.sku, v.mpn_comment, v.url_identifier, m.description, m.weight, m.category, m.tags, m.seo_title, m.seo_description
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
        """
        params = []
        if status != 'Todos':
            query += " WHERE v.sync_status = %s"
            params.append(status)
        query += " ORDER BY m.name, v.color_name"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def update_variants_sync_status(variant_ids, new_status, execution_id=False):
    """
    Actualiza masivamente el estado de sincronización de un conjunto de IDs de variante.
    Si se marca como Exportado (o algo distinto de Pendiente), limpia previous_stock.
    """
    if not variant_ids:
        return True
    conn = get_connection()
    try:
        cursor = conn.cursor()
        placeholders = ",".join(["%s"] * len(variant_ids))
        
        # Si el nuevo estado es distinto de Pendiente, limpiamos previous_stock
        prev_stock_part = ""
        if new_status != 'Pendiente':
            prev_stock_part = ", previous_stock = NULL"
            
        if execution_id is not False:
            query = f"""
                UPDATE product_variants
                SET sync_status = %s, execution_id = %s{prev_stock_part}, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, [new_status, execution_id] + list(variant_ids))
        else:
            query = f"""
                UPDATE product_variants
                SET sync_status = %s{prev_stock_part}, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, [new_status] + list(variant_ids))
            
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_models_for_matching():
    """
    Retorna una lista de diccionarios con id, name, price de todos los modelos.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, price FROM product_models")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def update_model_price(model_id, price):
    """
    Actualiza el precio de un modelo y marca sus variantes como Pendientes en Staging.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE product_models 
            SET price = %s
            WHERE id = %s
        """, (price, model_id))
        
        # Encolar variantes en Staging (Pendiente)
        cursor.execute("""
            UPDATE product_variants
            SET sync_status = 'Pendiente', execution_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE product_model_id = %s
        """, (model_id,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_variant_locally(variant_id):
    """
    Elimina físicamente una variante de la base de datos por su ID.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_variants WHERE id = %s", (variant_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_model_locally(model_id):
    """
    Elimina físicamente un modelo (y por cascada sus variantes) de la base de datos por su ID.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_models WHERE id = %s", (model_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_active_variants_with_urls():
    """
    Retorna todas las variantes activas en la base de datos local que poseen un identificador de URL.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT v.id AS variant_id, m.id AS model_id, m.name AS model_name, v.color_name, v.sku, v.stock, v.url_identifier
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.is_active = TRUE AND v.url_identifier IS NOT NULL AND v.url_identifier != ''
            ORDER BY m.name, v.color_name
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def delete_orphan_models():
    """
    Elimina físicamente los modelos que no tienen ninguna variante asociada.
    Retorna la cantidad de modelos eliminados.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_models WHERE id NOT IN (SELECT DISTINCT product_model_id FROM product_variants)")
        count = cursor.rowcount
        conn.commit()
        return count
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_detected_duplicates():
    """
    Retorna los duplicados detectados en el último proceso de importación.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT model_name, color_name, sku, stock, url_identifier
            FROM detected_duplicates
            ORDER BY model_name, color_name
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_config_value(key, default=None):
    """
    Retorna el valor de una clave de configuración desde la tabla general_config.
    Si la clave no existe, retorna el valor default.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM general_config WHERE key = %s", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default
    finally:
        conn.close()

def set_config_value(key, value):
    """
    Guarda o actualiza una clave de configuración en general_config.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO general_config (key, value)
            VALUES (%s, %s)
            ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value
        """, (key, value))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_product_mappings():
    """
    Retorna todos los mapeos de equivalencias registrados.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, supplier_name, internal_name FROM product_mappings ORDER BY supplier_name")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def add_product_mapping(supplier_name, internal_name):
    """
    Agrega o actualiza una regla de mapeo de equivalencias.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO product_mappings (supplier_name, internal_name)
            VALUES (%s, %s)
            ON CONFLICT(supplier_name) DO UPDATE SET internal_name = EXCLUDED.internal_name
        """, (supplier_name.strip().upper(), internal_name.strip().upper()))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_product_mapping(mapping_id):
    """
    Elimina un mapeo de equivalencia por su ID.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM product_mappings WHERE id = %s", (mapping_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_stock_movements_logs():
    """
    Retorna la lista de logs de movimientos de stock ordenados por fecha descendente.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, created_at, source, model_name, color_name, quantity, original_stock, resulting_stock, user_name
            FROM stock_movements_log
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def apply_stock_movement(variant_id, quantity, source_name="Procesador Stock", user_name="Admin", replace_mode=False):
    """
    Aplica un movimiento de stock a una variante:
    - Recupera el stock actual de la variante.
    - Calcula el resultante (sumando o reemplazando según replace_mode).
    - Si la variante ya estaba en Staging (Pendiente), conserva el previous_stock original,
      de lo contrario setea el stock actual como previous_stock.
    - Actualiza el stock en la DB.
    - Registra el movimiento en stock_movements_log.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Recuperar info actual de la variante
        cursor.execute("""
            SELECT v.stock, v.previous_stock, v.sync_status, m.name AS model_name, v.color_name
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.id = %s
        """, (variant_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Variante con ID {variant_id} no encontrada.")
            
        current_db_stock = row['stock'] or 0
        current_prev_stock = row['previous_stock']
        current_sync_status = row['sync_status']
        model_name = row['model_name']
        color_name = row['color_name']
        
        if replace_mode:
            resulting_stock = quantity
            quantity_change = resulting_stock - current_db_stock
        else:
            resulting_stock = current_db_stock + quantity
            quantity_change = quantity
        
        # Determinar el previous_stock
        if current_sync_status == 'Pendiente' and current_prev_stock is not None:
            new_prev_stock = current_prev_stock
        else:
            new_prev_stock = current_db_stock
            
        # 2. Actualizar tabla product_variants
        cursor.execute("""
            UPDATE product_variants
            SET previous_stock = %s,
                stock = %s,
                sync_status = 'Pendiente',
                execution_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_prev_stock, resulting_stock, variant_id))
        
        # 3. Registrar log del movimiento
        cursor.execute("""
            INSERT INTO stock_movements_log (source, model_name, color_name, quantity, original_stock, resulting_stock, user_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (source_name, model_name, color_name, quantity_change, current_db_stock, resulting_stock, user_name))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_all_active_display_variants():
    """
    Retorna id, display_name (MODELO - COLOR) y weight de todas las variantes activas.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.id, m.name || ' - ' || v.color_name AS display_name, m.weight, v.stock
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.is_active = TRUE
            ORDER BY m.name, v.color_name
        """)
        rows = cursor.fetchall()
        res = []
        for row in rows:
            d = dict(row)
            if d.get('weight') is not None:
                d['weight'] = float(d['weight'])
            res.append(d)
        return res
    finally:
        conn.close()


def update_variant_url_identifier(variant_id, url_identifier):
    """
    Actualiza el url_identifier de una variante en la base de datos local.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE product_variants
            SET url_identifier = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (url_identifier, variant_id))
        conn.commit()
        return True
    finally:
        conn.close()


def get_app_users():
    """
    Retorna la lista de todos los usuarios registrados.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, full_name, created_at, last_login FROM app_users ORDER BY username")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_user_by_username(username):
    """
    Retorna los datos de un usuario por su nombre de usuario.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash, role, full_name, created_at, last_login FROM app_users WHERE LOWER(username) = LOWER(%s)", (username.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_app_user(username, password, role='user', full_name=None):
    """
    Crea un nuevo usuario de la aplicación con la contraseña encriptada.
    """
    from services.security import hash_password
    conn = get_connection()
    try:
        cursor = conn.cursor()
        pw_hash = hash_password(password)
        cursor.execute("""
            INSERT INTO app_users (username, password_hash, role, full_name)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (username.strip().lower(), pw_hash, role, full_name))
        new_id = cursor.fetchone()['id']
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_app_user_password(user_id, new_password):
    """
    Actualiza la contraseña de un usuario encriptándola previamente.
    """
    from services.security import hash_password
    conn = get_connection()
    try:
        cursor = conn.cursor()
        pw_hash = hash_password(new_password)
        cursor.execute("UPDATE app_users SET password_hash = %s WHERE id = %s", (pw_hash, user_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_app_user_role(user_id, new_role):
    """
    Actualiza el rol de un usuario.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE app_users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_app_user(user_id):
    """
    Elimina un usuario de la aplicación.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_user_last_login(user_id):
    """
    Registra el timestamp del último inicio de sesión del usuario.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE app_users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_variants_without_url():
    """
    Retorna todas las variantes activas o inactivas que no tienen un identificador de URL.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.id AS variant_id, m.name AS model_name, v.color_name, v.sku, v.stock, v.sync_status
            FROM product_variants v
            JOIN product_models m ON v.product_model_id = m.id
            WHERE v.url_identifier IS NULL OR TRIM(v.url_identifier) = ''
            ORDER BY m.name, v.color_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()




