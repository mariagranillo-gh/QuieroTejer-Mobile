import sqlite3
import os
import sys

# Agregar el directorio raíz al path para poder importar database.connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_connection

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quierotejer.db")

def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"Error: No se encontró la base de datos SQLite local en {SQLITE_PATH}")
        sys.exit(1)

    print("Iniciando migración de SQLite a PostgreSQL en la nube...")
    
    # 1. Conectar a ambas bases de datos
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    try:
        pg_conn = get_connection()
        pg_cursor = pg_conn.cursor()
    except Exception as e:
        print(f"Error al conectar con la base de datos PostgreSQL: {e}")
        sqlite_conn.close()
        sys.exit(1)

    try:
        # 2. Limpiar las tablas en PostgreSQL para evitar duplicados
        print("Limpiando tablas existentes en PostgreSQL...")
        pg_cursor.execute("""
            TRUNCATE TABLE 
                product_variants, 
                product_models, 
                detected_duplicates, 
                general_config, 
                product_mappings, 
                stock_movements_log 
            CASCADE;
        """)
        pg_conn.commit()
        print("Tablas limpiadas con éxito.")

        # 3. Migrar 'general_config'
        print("\nMigrando 'general_config'...")
        sqlite_cursor.execute("SELECT key, value FROM general_config")
        rows = sqlite_cursor.fetchall()
        for row in rows:
            pg_cursor.execute(
                "INSERT INTO general_config (key, value) VALUES (%s, %s)",
                (row['key'], row['value'])
            )
        print(f"Migradas {len(rows)} filas de config.")

        # 4. Migrando 'product_models'
        print("\nMigrando 'product_models'...")
        sqlite_cursor.execute("""
            SELECT id, name, category, price, cost, description, tags, seo_title, seo_description, weight, created_at 
            FROM product_models
        """)
        rows = sqlite_cursor.fetchall()
        for row in rows:
            pg_cursor.execute("""
                INSERT INTO product_models (id, name, category, price, cost, description, tags, seo_title, seo_description, weight, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['id'], row['name'], row['category'], row['price'], row['cost'], 
                row['description'], row['tags'], row['seo_title'], row['seo_description'], 
                row['weight'], row['created_at']
            ))
        print(f"Migrados {len(rows)} modelos.")

        # 5. Migrando 'product_variants'
        print("\nMigrando 'product_variants'...")
        sqlite_cursor.execute("""
            SELECT id, product_model_id, color_name, sku, stock, previous_stock, execution_id, url_identifier, mpn_comment, is_active, sync_status, created_at, updated_at 
            FROM product_variants
        """)
        rows = sqlite_cursor.fetchall()
        for row in rows:
            # Convertir is_active a boolean explícitamente para Postgres
            is_active_bool = bool(row['is_active'])
            pg_cursor.execute("""
                INSERT INTO product_variants (id, product_model_id, color_name, sku, stock, previous_stock, execution_id, url_identifier, mpn_comment, is_active, sync_status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['id'], row['product_model_id'], row['color_name'], row['sku'], 
                row['stock'], row['previous_stock'], row['execution_id'], row['url_identifier'], row['mpn_comment'], 
                is_active_bool, row['sync_status'], row['created_at'], row['updated_at']
            ))
        print(f"Migradas {len(rows)} variantes.")

        # 6. Migrando 'detected_duplicates'
        print("\nMigrando 'detected_duplicates'...")
        sqlite_cursor.execute("""
            SELECT id, model_name, color_name, sku, stock, url_identifier, created_at 
            FROM detected_duplicates
        """)
        rows = sqlite_cursor.fetchall()
        for row in rows:
            pg_cursor.execute("""
                INSERT INTO detected_duplicates (id, model_name, color_name, sku, stock, url_identifier, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                row['id'], row['model_name'], row['color_name'], row['sku'], 
                row['stock'], row['url_identifier'], row['created_at']
            ))
        print(f"Migrados {len(rows)} duplicados detectados.")

        # 7. Migrando 'product_mappings'
        print("\nMigrando 'product_mappings'...")
        sqlite_cursor.execute("""
            SELECT id, supplier_name, internal_name 
            FROM product_mappings
        """)
        rows = sqlite_cursor.fetchall()
        for row in rows:
            pg_cursor.execute("""
                INSERT INTO product_mappings (id, supplier_name, internal_name)
                VALUES (%s, %s, %s)
            """, (
                row['id'], row['supplier_name'], row['internal_name']
            ))
        print(f"Migrados {len(rows)} mapeos de equivalencias.")

        # 8. Migrando 'stock_movements_log'
        print("\nMigrando 'stock_movements_log'...")
        sqlite_cursor.execute("""
            SELECT id, created_at, source, model_name, color_name, quantity, original_stock, resulting_stock, user_name 
            FROM stock_movements_log
        """)
        rows = sqlite_cursor.fetchall()
        for row in rows:
            pg_cursor.execute("""
                INSERT INTO stock_movements_log (id, created_at, source, model_name, color_name, quantity, original_stock, resulting_stock, user_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                row['id'], row['created_at'], row['source'], row['model_name'], 
                row['color_name'], row['quantity'], row['original_stock'], 
                row['resulting_stock'], row['user_name']
            ))
        print(f"Migrados {len(rows)} logs de movimientos.")

        # Confirmar inserciones
        pg_conn.commit()

        # 9. Sincronizar secuencias de IDs en PostgreSQL
        print("\nSincronizando secuencias de IDs en PostgreSQL...")
        tables_with_serial = [
            ("product_models", "id"),
            ("product_variants", "id"),
            ("detected_duplicates", "id"),
            ("product_mappings", "id"),
            ("stock_movements_log", "id")
        ]
        
        for table, pkey in tables_with_serial:
            pg_cursor.execute(f"""
                SELECT setval(pg_get_serial_sequence('{table}', '{pkey}'), coalesce(max({pkey}), 1), max({pkey}) IS NOT NULL) 
                FROM {table};
            """)
        pg_conn.commit()
        print("Secuencias de IDs sincronizadas exitosamente.")
        
        print("\n¡MIGRACIÓN COMPLETADA EXITOSAMENTE!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\nError crítico durante la migración: {e}")
        raise e
    finally:
        sqlite_conn.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate()
