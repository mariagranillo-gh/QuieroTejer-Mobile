import requests
import json

def test_tiendanube_connection(store_id, access_token, user_agent):
    """
    Verifica las credenciales de TiendaNube consultando la información básica de la tienda.
    Retorna un diccionario: {"success": bool, "store_name": str, "error": str}
    """
    if not store_id or not access_token or not user_agent:
        return {"success": False, "error": "Credenciales incompletas (falta Store ID, Access Token o User-Agent)."}
    
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/store"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            store_data = response.json()
            # Devolver el nombre principal de la tienda en español o inglés
            name_dict = store_data.get("name", {})
            store_name = name_dict.get("es", name_dict.get("en", "Tienda Sin Nombre"))
            return {"success": True, "store_name": store_name}
        elif response.status_code == 401:
            return {"success": False, "error": "Acceso no autorizado (Access Token inválido o vencido)."}
        elif response.status_code == 404:
            return {"success": False, "error": "Tienda no encontrada (Store ID incorrecto)."}
        else:
            return {"success": False, "error": f"Error del servidor de TiendaNube (Código HTTP: {response.status_code})."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al conectar con TiendaNube."}
    except Exception as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}


def get_variant_by_sku(store_id, access_token, user_agent, sku):
    """
    Busca un producto por SKU de variante en TiendaNube y retorna la información de la variante correspondiente.
    Retorna un diccionario: 
    - Éxito: {"success": True, "product_id": int, "variant_id": int, "price": str, "stock": int}
    - Falla: {"success": False, "error": str}
    """
    if not sku:
        return {"success": False, "error": "Falta el SKU para la búsqueda."}
        
    sku_clean = str(sku).strip().upper()
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products/sku/{sku_clean}"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            product = response.json()
            product_id = product.get("id")
            
            # Buscar la variante con el SKU correspondiente
            for variant in product.get("variants", []):
                var_sku = str(variant.get("sku", "")).strip().upper()
                if var_sku == sku_clean:
                    return {
                        "success": True,
                        "product_id": product_id,
                        "variant_id": variant.get("id"),
                        "price": variant.get("price"),
                        "stock": variant.get("stock")
                    }
            return {"success": False, "error": f"No se encontró ninguna variante con el SKU '{sku}' dentro del producto '{product.get('name', {}).get('es')}'."}
        elif response.status_code == 404:
            return {"success": False, "error": f"SKU '{sku}' no existe en TiendaNube."}
        else:
            return {"success": False, "error": f"Error al buscar SKU (Código HTTP: {response.status_code})."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al consultar el SKU."}
def get_variant_by_url_and_color(store_id, access_token, user_agent, url_identifier, color_name):
    """
    Busca un producto por su url_identifier (handle) en Tiendanube
    y luego busca la variante que corresponda al color indicado.
    Retorna: {"success": bool, "product_id": int, "variant_id": int, "price": str, "stock": int, "error": str}
    """
    if not url_identifier or not color_name:
        return {"success": False, "error": "Faltan parámetros de búsqueda (url_identifier o color_name)."}
        
    handle_clean = str(url_identifier).strip().lower()
    color_clean = str(color_name).strip().upper()
    
    # 1. Buscar productos por el q parameter (que busca handle/nombre)
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    try:
        page = 1
        target_product = None
        
        while True:
            response = requests.get(url, headers=headers, params={"q": handle_clean, "per_page": 100, "page": page}, timeout=15)
            if response.status_code != 200:
                return {"success": False, "error": f"Error al buscar en catálogo de Tiendanube (Código HTTP: {response.status_code})."}
            
            page_products = response.json()
            if not page_products:
                break
                
            for p in page_products:
                p_handles = p.get("handle", {})
                if any(str(val).strip().lower() == handle_clean for val in p_handles.values()):
                    target_product = p
                    break
            
            if target_product:
                break
                
            page += 1
            
        if not target_product:
            return {"success": False, "error": f"No se encontró ningún producto con el identificador de URL '{url_identifier}' en Tiendanube."}
            
        product_id = target_product.get("id")
        
        # 2. Buscar la variante que coincida con el color
        for variant in target_product.get("variants", []):
            values = variant.get("values", [])
            match_color = False
            for val_obj in values:
                if isinstance(val_obj, dict):
                    if any(str(val).strip().upper() == color_clean for val in val_obj.values()):
                        match_color = True
                        break
                elif isinstance(val_obj, str):
                    if val_obj.strip().upper() == color_clean:
                        match_color = True
                        break
            
            if match_color:
                return {
                    "success": True,
                    "product_id": product_id,
                    "variant_id": variant.get("id"),
                    "price": variant.get("price"),
                    "stock": variant.get("stock")
                }
                
        return {"success": False, "error": f"Se encontró el producto '{url_identifier}', pero no tiene ninguna variante con el color '{color_name}'."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al conectar con Tiendanube."}
    except Exception as e:
        return {"success": False, "error": f"Error de búsqueda: {str(e)}"}


def update_variant_stock_price(store_id, access_token, user_agent, product_id, variant_id, price=None, stock=None, mpn=None):
    """
    Actualiza el precio, el stock y/o el MPN de una variante específica en TiendaNube.
    Retorna un diccionario: {"success": bool, "error": str}
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products/{product_id}/variants/{variant_id}"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    payload = {}
    if price is not None:
        payload["price"] = str(price)
    if stock is not None:
        payload["stock"] = int(stock)
    if mpn is not None:
        payload["mpn"] = str(mpn).strip()
        
    if not payload:
        return {"success": True, "no_op": True}
        
    try:
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"Fallo al actualizar variante (Código HTTP: {response.status_code}). Respuesta: {response.text}"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al actualizar la variante en TiendaNube."}
    except Exception as e:
        return {"success": False, "error": f"Error de actualización: {str(e)}"}


def update_product_details(store_id, access_token, user_agent, product_id, description=None, tags=None, seo_title=None, seo_description=None, categories=None):
    """
    Actualiza campos generales de un producto en TiendaNube (descripción, tags, seo, categorías).
    Retorna un diccionario: {"success": bool, "error": str}
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products/{product_id}"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    payload = {}
    if description is not None:
        payload["description"] = {"es": str(description).strip()}
    if tags is not None:
        payload["tags"] = str(tags).strip()
    if seo_title is not None:
        payload["seo_title"] = {"es": str(seo_title).strip()}
    if seo_description is not None:
        payload["seo_description"] = {"es": str(seo_description).strip()}
    if categories is not None:
        payload["categories"] = [int(cat_id) for cat_id in categories]
        
    try:
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"Fallo al actualizar producto (Código HTTP: {response.status_code}). Respuesta: {response.text}"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Tiempo de espera agotado al actualizar detalles del producto en TiendaNube."}
    except Exception as e:
        return {"success": False, "error": f"Error de actualización de detalles: {str(e)}"}


def get_all_tiendanube_products(store_id, access_token, user_agent):
    """
    Trae todos los productos de Tiendanube paginando de a 100 de manera secuencial.
    Retorna un diccionario mapeando handle (identificador_url) -> product_object.
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    catalog = {}
    page = 1
    
    try:
        while True:
            response = requests.get(url, headers=headers, params={"per_page": 100, "page": page}, timeout=15)
            if response.status_code != 200:
                break
                
            page_products = response.json()
            if not page_products:
                break
                
            for p in page_products:
                p_handles = p.get("handle", {})
                if isinstance(p_handles, dict):
                    for val in p_handles.values():
                        if val:
                            catalog[str(val).strip().lower()] = p
                elif isinstance(p_handles, str) and p_handles:
                    catalog[p_handles.strip().lower()] = p
            
            page += 1
            
    except Exception:
        pass
        
    return catalog


def update_product_visibility(store_id, access_token, user_agent, product_id, published):
    """
    Actualiza la visibilidad (publicación) de un producto en TiendaNube.
    Retorna True si la operación fue exitosa, False en caso contrario.
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products/{product_id}"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    payload = {
        "published": bool(published)
    }
    try:
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False


def create_tiendanube_product(
    store_id, access_token, user_agent, 
    name_es, description_es, price, stock, weight, 
    sku=None, brand="Quiero Tejer", published=False,
    color_name=None, categories=None, tags=None,
    seo_title=None, seo_description=None, handle=None
):
    """
    Crea un nuevo producto en TiendaNube con una variante inicial estructurada por color.
    Retorna un diccionario con {"success": True, "product_id": int, "variant_id": int, "handle": str} o {"success": False, "error": str}
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": {
            "es": str(name_es).strip()
        },
        "description": {
            "es": str(description_es).strip() if description_es else ""
        },
        "published": bool(published),
        "brand": str(brand).strip(),
        "attributes": [
            {
                "es": "COLOR"
            }
        ],
        "variants": [
            {
                "values": [
                    {
                        "es": str(color_name).strip() if color_name else "Único"
                    }
                ],
                "price": str(price),
                "stock": int(stock) if stock is not None else 0,
                "weight": str(weight) if weight is not None else "0.100"
            }
        ]
    }
    
    if handle:
        payload["handle"] = {
            "es": str(handle).strip().lower()
        }
        
    if sku:
        payload["variants"][0]["sku"] = str(sku).strip()
        
    if categories:
        payload["categories"] = [int(cat_id) for cat_id in categories]
        
    if tags:
        payload["tags"] = str(tags).strip()
        
    if seo_title:
        payload["seo_title"] = {
            "es": str(seo_title).strip()
        }
        
    if seo_description:
        payload["seo_description"] = {
            "es": str(seo_description).strip()
        }
        
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 201:
            data = response.json()
            product_id = data.get("id")
            variants = data.get("variants", [])
            variant_id = variants[0].get("id") if variants else None
            
            handle_data = data.get("handle", {})
            handle = ""
            if isinstance(handle_data, dict):
                for val in handle_data.values():
                    if val:
                        handle = val
                        break
            elif isinstance(handle_data, str):
                handle = handle_data
                
            return {
                "success": True,
                "product_id": product_id,
                "variant_id": variant_id,
                "handle": handle
            }
        else:
            return {"success": False, "error": f"Código HTTP {response.status_code}. Respuesta: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_tiendanube_categories(store_id, access_token, user_agent):
    """
    Obtiene todas las categorías de la tienda en TiendaNube.
    Retorna una lista de diccionarios con las categorías, o una lista vacía si falla.
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/categories"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def create_tiendanube_category(store_id, access_token, user_agent, name_es, parent_id=None):
    """
    Crea una nueva categoría en TiendaNube, opcionalmente asignándole un padre.
    Retorna el ID de la nueva categoría si es exitoso, o None si falla.
    """
    url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/categories"
    headers = {
        "Authorization": f"Bearer {str(access_token).strip()}",
        "User-Agent": str(user_agent).strip(),
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": {
            "es": str(name_es).strip()
        },
        "parent": parent_id if parent_id is not None else None
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 201:
            data = response.json()
            return data.get("id")
    except Exception:
        pass
    return None
