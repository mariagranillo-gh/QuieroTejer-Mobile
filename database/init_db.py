import sys
import os

# Agregar el directorio raíz al path para poder importar database.connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_connection

def create_tables():
    """
    Crea las tablas de la base de datos si no existen.
    Aplica migraciones automáticas para campos nuevos en PostgreSQL.
    """
    # Definición de las tablas (esquema base adaptado a PostgreSQL)
    sql_create_models = """
    CREATE TABLE IF NOT EXISTS product_models (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        category TEXT,
        price DECIMAL(10, 2) NOT NULL,
        cost DECIMAL(10, 2) DEFAULT 0.00,
        description TEXT,
        tags TEXT,
        seo_title TEXT,
        seo_description TEXT,
        weight DECIMAL(10, 3) DEFAULT 0.100,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    sql_create_variants = """
    CREATE TABLE IF NOT EXISTS product_variants (
        id SERIAL PRIMARY KEY,
        product_model_id INTEGER NOT NULL,
        color_name TEXT NOT NULL,
        sku TEXT,
        stock INTEGER DEFAULT 0,
        previous_stock INTEGER,
        execution_id TEXT,
        url_identifier TEXT,
        mpn_comment TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        sync_status TEXT DEFAULT 'Exportado',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_model_id) REFERENCES product_models (id) ON DELETE CASCADE,
        UNIQUE (product_model_id, color_name)
    );
    """

    sql_create_duplicates = """
    CREATE TABLE IF NOT EXISTS detected_duplicates (
        id SERIAL PRIMARY KEY,
        model_name TEXT,
        color_name TEXT,
        sku TEXT,
        stock INTEGER,
        url_identifier TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    sql_create_config = """
    CREATE TABLE IF NOT EXISTS general_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """

    sql_create_mappings = """
    CREATE TABLE IF NOT EXISTS product_mappings (
        id SERIAL PRIMARY KEY,
        supplier_name TEXT NOT NULL UNIQUE,
        internal_name TEXT NOT NULL
    );
    """

    sql_create_movements_log = """
    CREATE TABLE IF NOT EXISTS stock_movements_log (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source TEXT NOT NULL,
        model_name TEXT NOT NULL,
        color_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        original_stock INTEGER NOT NULL,
        resulting_stock INTEGER NOT NULL,
        user_name TEXT NOT NULL
    );
    """

    sql_create_users = """
    CREATE TABLE IF NOT EXISTS app_users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        full_name VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    );
    """

    # Creación de índices en PostgreSQL
    sql_create_idx_variants_model = "CREATE INDEX IF NOT EXISTS idx_variants_model ON product_variants(product_model_id);"
    sql_create_idx_variants_active = "CREATE INDEX IF NOT EXISTS idx_variants_active ON product_variants(is_active);"
    sql_create_idx_variants_stock = "CREATE INDEX IF NOT EXISTS idx_variants_stock ON product_variants(stock);"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_create_models)
        cursor.execute(sql_create_variants)
        cursor.execute(sql_create_duplicates)
        cursor.execute(sql_create_config)
        cursor.execute(sql_create_mappings)
        cursor.execute(sql_create_movements_log)
        cursor.execute(sql_create_users)
        cursor.execute(sql_create_idx_variants_model)
        cursor.execute(sql_create_idx_variants_active)
        cursor.execute(sql_create_idx_variants_stock)
        
        # Inicialización de la configuración por defecto (ON CONFLICT para Postgres)
        cursor.execute("""
            INSERT INTO general_config (key, value) 
            VALUES ('PathFotos', 'c:\\qt\\fotos')
            ON CONFLICT (key) DO NOTHING
        """)
        
        conn.commit()

        print("Tablas base verificadas/creadas con éxito en PostgreSQL")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

    # Ejecutar migraciones automáticas para columnas nuevas
    run_migrations()

def run_migrations():
    """
    Agrega dinámicamente columnas nuevas a las tablas si ya existen previamente (PostgreSQL).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Migraciones de product_models
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'product_models'
        """)
        models_cols = [row['column_name'] for row in cursor.fetchall()]
        
        migrations_models = {
            'tags': 'TEXT',
            'seo_title': 'TEXT',
            'seo_description': 'TEXT',
            'weight': 'DECIMAL(10, 3) DEFAULT 0.100'
        }
        
        for col, col_type in migrations_models.items():
            if col not in models_cols:
                cursor.execute(f"ALTER TABLE product_models ADD COLUMN {col} {col_type}")
                print(f"Columna '{col}' agregada a la tabla product_models.")
                
        # 2. Migraciones de product_variants
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'product_variants'
        """)
        variants_cols = [row['column_name'] for row in cursor.fetchall()]
        
        if 'sync_status' not in variants_cols:
            cursor.execute("ALTER TABLE product_variants ADD COLUMN sync_status TEXT DEFAULT 'Exportado'")
            print("Columna 'sync_status' agregada a la tabla product_variants.")

        if 'previous_stock' not in variants_cols:
            cursor.execute("ALTER TABLE product_variants ADD COLUMN previous_stock INTEGER")
            print("Columna 'previous_stock' agregada a la tabla product_variants.")

        if 'execution_id' not in variants_cols:
            cursor.execute("ALTER TABLE product_variants ADD COLUMN execution_id TEXT")
            print("Columna 'execution_id' agregada a la tabla product_variants.")
            
        # Crear índice para sync_status ahora que está garantizado que la columna existe
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_variants_sync ON product_variants(sync_status);")
        
        conn.commit()
        print("Migraciones ejecutadas exitosamente en PostgreSQL.")
    except Exception as e:
        conn.rollback()
        print(f"Error en migraciones: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    create_tables()
