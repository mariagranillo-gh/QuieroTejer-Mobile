import os
import sys
import shutil
import unicodedata
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.queries import get_config_value, create_variant

def normalize_dir_name(name):
    """
    Normaliza el nombre de una carpeta para comparación:
    Convierte a mayúsculas, quita acentos y espacios adicionales.
    """
    if not name:
        return ""
    name = str(name).strip().upper()
    # Eliminar acentos
    name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return ' '.join(name.split())

def scan_and_import_photos_for_model(model_id, model_name, stock=0, mpn_comment=None):
    """
    Escanea la carpeta de un modelo dentro de la ruta configurada en general_config,
    detecta los colores de las fotos, da de alta las variantes que falten y
    mueve los archivos procesados a la carpeta de 'Completados'.
    
    Retorna un diccionario con estadísticas del proceso.
    """
    # 1. Obtener ruta base
    base_path = get_config_value('PathFotos', r'c:\qt\fotos')
    
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"La ruta base de fotos '{base_path}' no existe en el sistema. Configúrala correctamente.")
        
    # 2. Buscar la carpeta del modelo de forma case-insensitive y sin acentos
    model_norm = normalize_dir_name(model_name)
    matched_dir = None
    
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path) and item.upper() != "COMPLETADOS":
            if normalize_dir_name(item) == model_norm:
                matched_dir = item_path
                break
                
    if not matched_dir:
        raise FileNotFoundError(f"No se encontró la carpeta para el modelo '{model_name}' dentro de '{base_path}'.")
        
    # 3. Escanear archivos de imagen
    valid_extensions = ('.jpg', '.jpeg', '.png')
    files_to_process = []
    
    for file in os.listdir(matched_dir):
        if file.lower().endswith(valid_extensions):
            files_to_process.append(file)
            
    stats = {
        'total_found': len(files_to_process),
        'created': 0,
        'omitted': 0,
        'errors': []
    }
    
    if not files_to_process:
        return stats
        
    # 4. Crear directorio de Completados para el modelo
    folder_basename = os.path.basename(matched_dir)
    completados_dir = os.path.join(base_path, "Completados", folder_basename)
    os.makedirs(completados_dir, exist_ok=True)
    
    # 5. Procesar cada imagen
    for file in files_to_process:
        color_name = os.path.splitext(file)[0].strip().upper()
        
        src_path = os.path.join(matched_dir, file)
        dest_path = os.path.join(completados_dir, file)
        
        try:
            # Intentar dar de alta la variante
            create_variant(
                model_id=model_id,
                color_name=color_name,
                mpn_comment=mpn_comment,
                stock=stock
            )
            stats['created'] += 1
            
            # Mover archivo
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(src_path, dest_path)
            
        except ValueError as val_err:
            # Caso en que la variante ya existe (IntegrityError controlado)
            stats['omitted'] += 1
            
            # Se mueve el archivo igualmente porque ya fue procesado y existe en la base
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                shutil.move(src_path, dest_path)
            except Exception as move_err:
                stats['errors'].append(f"Error al mover archivo duplicado {file}: {move_err}")
                
        except Exception as e:
            # Cualquier otro error inesperado (permisos, base bloqueada, etc.)
            stats['errors'].append(f"Error con {file}: {str(e)}")
            
    return stats
