import os
import psycopg2
import psycopg2.extras

def load_local_secrets():
    """
    Carga las credenciales del archivo .streamlit/secrets.toml de forma local
    cuando se ejecutan scripts por consola (fuera de Streamlit).
    """
    secrets_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".streamlit", "secrets.toml")
    if os.path.exists(secrets_path):
        try:
            import toml
            data = toml.load(secrets_path)
            if "postgres" in data:
                return data["postgres"]
        except Exception:
            # Fallback simple si 'toml' no está disponible o falla
            try:
                postgres_sec = {}
                current_section = None
                with open(secrets_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("[") and line.endswith("]"):
                            current_section = line[1:-1].strip()
                        elif current_section == "postgres" and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            postgres_sec[k] = v
                if postgres_sec:
                    return postgres_sec
            except Exception:
                pass
    return None

# Variable global para almacenar el ConnectionProxy que envuelve la conexión viva
_cached_connection = None

class ConnectionProxy:
    def __init__(self, conn):
        object.__setattr__(self, '_conn', conn)
        
    def __getattr__(self, name):
        return getattr(self._conn, name)
        
    def __setattr__(self, name, value):
        setattr(self._conn, name, value)
        
    def __enter__(self):
        return self._conn.__enter__()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)
        
    def close(self):
        # El close del proxy es un no-op para mantener la conexión viva en la caché
        pass
        
    def _original_close(self):
        self._conn.close()

def get_connection():
    """
    Establece, cachea y retorna un proxy de conexión a la base de datos PostgreSQL (Supabase).
    Si ya hay una conexión abierta y activa, la reutiliza.
    """
    global _cached_connection
    
    # Si ya tenemos una conexión y sigue abierta
    if _cached_connection is not None and not _cached_connection.closed:
        try:
            # Comprobar que siga viva
            with _cached_connection.cursor() as cur:
                cur.execute("SELECT 1")
            return _cached_connection
        except Exception:
            # Si falló, descartamos la conexión muerta
            try:
                _cached_connection._original_close()
            except Exception:
                pass
            _cached_connection = None

    postgres_config = None

    # 0. Intentar obtener de variables de entorno (para despliegues en la nube como Render)
    if "DATABASE_URL" in os.environ:
        postgres_config = {"url": os.environ["DATABASE_URL"]}
    elif "DB_HOST" in os.environ:
        postgres_config = {
            "host": os.environ.get("DB_HOST"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "database": os.environ.get("DB_NAME", "postgres"),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD")
        }

    # 1. Intentar obtener de st.secrets (Streamlit)
    if not postgres_config:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "postgres" in st.secrets:
                postgres_config = st.secrets["postgres"]
        except Exception:
            pass

    # 2. Si no, intentar cargar desde secrets.toml localmente
    if not postgres_config:
        postgres_config = load_local_secrets()

    if not postgres_config:
        raise RuntimeError(
            "No se encontraron las credenciales de PostgreSQL. "
            "Asegúrate de configurar la sección [postgres] en .streamlit/secrets.toml localmente "
            "o en la configuración de Secrets en Streamlit Cloud."
        )

    # 3. Establecer conexión
    if "url" in postgres_config:
        conn = psycopg2.connect(postgres_config["url"])
    else:
        conn = psycopg2.connect(
            host=postgres_config.get("host"),
            port=postgres_config.get("port", 5432),
            database=postgres_config.get("database"),
            user=postgres_config.get("user"),
            password=postgres_config.get("password")
        )

    # Configurar RealDictCursor por defecto
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    
    proxy = ConnectionProxy(conn)
    _cached_connection = proxy
    return proxy
