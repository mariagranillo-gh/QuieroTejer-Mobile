import http.server
import socketserver
import json
import urllib.parse
import sys
import os
import requests

# Agregar el directorio raíz de la app móvil al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.connection import get_connection
from services.security import verify_password
from database.queries import (
    get_all_active_display_variants,
    get_stock_faltante_list,
    apply_stock_movement,
    get_config_value,
    update_variants_sync_status
)
from services.tiendanube import (
    get_variant_by_url_and_color,
    get_variant_by_sku,
    update_variant_stock_price
)

PORT = int(os.environ.get("PORT", 8080))

class MobileAPIHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Permitir CORS para facilitar desarrollo
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200, "OK")
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/variants":
            try:
                variants = get_all_active_display_variants()
                self.send_json_response(200, {"success": True, "variants": variants})
            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        elif path == "/api/alerts":
            try:
                min_stock = int(query_params.get("min_stock", [10])[0])
                alerts = get_stock_faltante_list(min_stock=min_stock)
                self.send_json_response(200, {"success": True, "alerts": alerts})
            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        elif path == "/api/live_stock":
            try:
                variant_id = int(query_params.get("variant_id", [0])[0])
                if not variant_id:
                    self.send_json_response(400, {"success": False, "error": "Falta variant_id"})
                    return

                # Obtener datos locales
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT v.stock, v.color_name, v.sku, v.url_identifier
                    FROM product_variants v
                    WHERE v.id = %s
                """, (variant_id,))
                var_info = cursor.fetchone()
                conn.close()

                if not var_info:
                    self.send_json_response(404, {"success": False, "error": "Variante no encontrada"})
                    return

                local_stock = var_info['stock'] or 0
                color_name = var_info['color_name']
                sku = var_info['sku']
                url_id = var_info['url_identifier']

                # Consultar Tiendanube
                store_id = get_config_value('TiendaNubeStoreId')
                access_token = get_config_value('TiendaNubeAccessToken')
                user_agent = get_config_value('TiendaNubeUserAgent') or "QuieroTejer (administracion@quierotejer.com)"

                tn_stock = "Desconectado"

                if store_id and access_token and user_agent:
                    tn_var_id = None
                    tn_stock_val = None

                    if sku:
                        sku_res = get_variant_by_sku(store_id, access_token, user_agent, sku)
                        if sku_res.get("success"):
                            tn_var_id = sku_res["variant_id"]
                            tn_stock_val = sku_res["stock"]
                    
                    if not tn_var_id and url_id:
                        url_res = get_variant_by_url_and_color(store_id, access_token, user_agent, url_id, color_name)
                        if url_res.get("success"):
                            tn_var_id = url_res["variant_id"]
                            tn_stock_val = url_res["stock"]

                    if tn_var_id is not None:
                        tn_stock = str(tn_stock_val) if tn_stock_val is not None else "0"
                    else:
                        tn_stock = "No vinculado"

                self.send_json_response(200, {
                    "success": True,
                    "local_stock": local_stock,
                    "tiendanube_stock": tn_stock
                })
            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        # Para cualquier otra ruta que no sea API, servir como archivo estático
        super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/login":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                username = data.get("username", "").strip()
                password = data.get("password", "").strip()

                if not username or not password:
                    self.send_json_response(400, {"success": False, "error": "Falta usuario o contraseña."})
                    return

                # Buscar en la base de datos
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, username, password_hash, role, full_name 
                    FROM app_users 
                    WHERE LOWER(username) = LOWER(%s)
                """, (username,))
                user = cursor.fetchone()
                conn.close()

                if user and verify_password(password, user['password_hash']):
                    self.send_json_response(200, {
                        "success": True,
                        "user": {
                            "username": user['username'],
                            "role": user['role'],
                            "full_name": user['full_name']
                        }
                    })
                else:
                    self.send_json_response(401, {"success": False, "error": "Credenciales inválidas."})
            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        elif path == "/api/adjust_stock":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                variant_id = int(data.get("variant_id"))
                quantity = int(data.get("quantity")) # Positivo para sumas, negativo para restas
                username = data.get("username", "Celular PWA")

                # 1. Aplicar movimiento localmente
                apply_stock_movement(
                    variant_id=variant_id,
                    quantity=quantity,
                    source_name="Ajuste Celular",
                    user_name=username,
                    replace_mode=False
                )

                # Obtener nuevo stock y datos de sincronización local
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT v.stock, v.color_name, v.sku, v.url_identifier, m.name AS model_name
                    FROM product_variants v
                    JOIN product_models m ON v.product_model_id = m.id
                    WHERE v.id = %s
                """, (variant_id,))
                var_info = cursor.fetchone()
                conn.close()

                new_stock = var_info['stock']
                color_name = var_info['color_name']
                sku = var_info['sku']
                url_id = var_info['url_identifier']
                model_name = var_info['model_name']

                # 2. Intentar Sincronización instantánea con Tiendanube
                store_id = get_config_value('TiendaNubeStoreId')
                access_token = get_config_value('TiendaNubeAccessToken')
                user_agent = get_config_value('TiendaNubeUserAgent') or "QuieroTejer (administracion@quierotejer.com)"

                sync_msg = "Ajuste guardado localmente."
                sync_success = False

                if store_id and access_token and user_agent:
                    tn_prod_id = None
                    tn_var_id = None

                    # Buscar variante en Tiendanube por SKU o por URL/Color
                    if sku:
                        sku_res = get_variant_by_sku(store_id, access_token, user_agent, sku)
                        if sku_res.get("success"):
                            tn_prod_id = sku_res["product_id"]
                            tn_var_id = sku_res["variant_id"]
                    
                    if not tn_var_id and url_id:
                        url_res = get_variant_by_url_and_color(store_id, access_token, user_agent, url_id, color_name)
                        if url_res.get("success"):
                            tn_prod_id = url_res["product_id"]
                            tn_var_id = url_res["variant_id"]

                    if tn_prod_id and tn_var_id:
                        # Mandar el nuevo stock a Tiendanube
                        up_res = update_variant_stock_price(
                            store_id, access_token, user_agent,
                            tn_prod_id, tn_var_id,
                            stock=new_stock
                        )
                        if up_res.get("success"):
                            # Marcar como Exportado localmente
                            update_variants_sync_status([variant_id], 'Exportado')
                            sync_msg += " ¡Sincronizado con Tiendanube!"
                            sync_success = True
                        else:
                            sync_msg += f" Error de sincronización: {up_res.get('error')}"
                    else:
                        sync_msg += " No se pudo asociar con el producto en Tiendanube (Falta SKU o URL identificadora)."
                else:
                    sync_msg += " (Sincronización deshabilitada: falta configurar credenciales API)."

                self.send_json_response(200, {
                    "success": True, 
                    "new_stock": new_stock, 
                    "sync_success": sync_success,
                    "message": sync_msg
                })
            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        elif path == "/api/webhook":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                store_id = data.get("store_id") or data.get("user_id")
                event = data.get("event")
                product_id = data.get("id")
                
                print(f"[Webhook] Recibido evento: '{event}' para Store: {store_id}, Product ID: {product_id}")
                
                saved_store_id = get_config_value('TiendaNubeStoreId')
                
                if str(store_id) != str(saved_store_id):
                    print(f"[Webhook] Store ID {store_id} no coincide con el configurado {saved_store_id}. Ignorando.")
                    self.send_json_response(200, {"success": True, "message": "Ignorado por Store ID diferente"})
                    return
                    
                if event == "product/updated" and product_id:
                    access_token = get_config_value('TiendaNubeAccessToken')
                    user_agent = get_config_value('TiendaNubeUserAgent') or "QuieroTejer (administracion@quierotejer.com)"
                    
                    if not access_token:
                        print("[Webhook] Access Token no configurado. Abortando.")
                        self.send_json_response(500, {"success": False, "error": "Access Token no configurado"})
                        return
                        
                    url = f"https://api.tiendanube.com/v1/{store_id}/products/{product_id}"
                    headers = {
                        "Authorization": f"Bearer {str(access_token).strip()}",
                        "User-Agent": user_agent,
                        "Content-Type": "application/json"
                    }
                    
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        product_data = r.json()
                        variants_list = product_data.get("variants", [])
                        
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        updated_count = 0
                        
                        # Obtener handle del producto para fallback de búsqueda por URL
                        url_id_clean = None
                        p_handle = product_data.get("handle", {})
                        if isinstance(p_handle, dict):
                            for val in p_handle.values():
                                if val:
                                    url_id_clean = str(val).strip().lower()
                                    break
                        elif isinstance(p_handle, str) and p_handle:
                            url_id_clean = p_handle.strip().lower()

                        for v in variants_list:
                            sku = v.get("sku")
                            tn_stock = v.get("stock")
                            
                            if tn_stock is None:
                                continue
                                
                            local_var = None
                            
                            # 1. Intentar buscar por SKU
                            if sku:
                                sku_clean = str(sku).strip().upper()
                                if sku_clean:
                                    cursor.execute("""
                                        SELECT id, stock, color_name 
                                        FROM product_variants 
                                        WHERE UPPER(TRIM(sku)) = %s AND is_active = TRUE
                                    """, (sku_clean,))
                                    local_var = cursor.fetchone()
                                    
                            # 2. Fallback a buscar por URL identificadora + Color si no se encontró por SKU
                            if not local_var and url_id_clean:
                                color_name_clean = None
                                for val_obj in v.get("values", []):
                                    if isinstance(val_obj, dict):
                                        for val in val_obj.values():
                                            if val:
                                                color_name_clean = str(val).strip().upper()
                                                break
                                    elif isinstance(val_obj, str) and val_obj:
                                        color_name_clean = val_obj.strip().upper()
                                        break
                                
                                if color_name_clean:
                                    cursor.execute("""
                                        SELECT id, stock, color_name 
                                        FROM product_variants 
                                        WHERE LOWER(TRIM(url_identifier)) = %s AND UPPER(TRIM(color_name)) = %s AND is_active = TRUE
                                    """, (url_id_clean, color_name_clean))
                                    local_var = cursor.fetchone()
                                    
                            if local_var:
                                local_stock = local_var["stock"]
                                if local_stock != tn_stock:
                                    delta = tn_stock - local_stock
                                    
                                    cursor.execute("""
                                        SELECT m.name AS model_name 
                                        FROM product_variants v 
                                        JOIN product_models m ON v.product_model_id = m.id 
                                        WHERE v.id = %s
                                    """, (local_var["id"],))
                                    model_info = cursor.fetchone()
                                    model_name = model_info["model_name"] if model_info else "Modelo Desconocido"
                                    
                                    cursor.execute("""
                                        UPDATE product_variants 
                                        SET stock = %s, updated_at = CURRENT_TIMESTAMP 
                                        WHERE id = %s
                                    """, (tn_stock, local_var["id"]))
                                    
                                    cursor.execute("""
                                        INSERT INTO stock_movements_log (source, model_name, color_name, quantity, original_stock, resulting_stock, user_name)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                                    """, (
                                        "Webhook Tiendanube",
                                        model_name,
                                        local_var["color_name"],
                                        delta,
                                        local_stock,
                                        tn_stock,
                                        "Tiendanube System"
                                    ))
                                    updated_count += 1
                                    print(f"[Webhook] SKU: {sku_clean} actualizado localmente de {local_stock} a {tn_stock} (Diferencia: {delta})")
                        
                        conn.commit()
                        conn.close()
                        self.send_json_response(200, {"success": True, "updated_variants": updated_count})
                        return
                    else:
                        print(f"[Webhook] Error al consultar API de Tiendanube (Código: {r.status_code}): {r.text}")
                        self.send_json_response(500, {"success": False, "error": "Error al consultar API de Tiendanube"})
                        return
                else:
                    print(f"[Webhook] Evento '{event}' no soportado o ID faltante. Ignorando.")
                    self.send_json_response(200, {"success": True, "message": "Evento ignorado"})
                    return
            except Exception as e:
                print(f"[Webhook] Excepción: {e}")
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        elif path == "/api/sync_catalog":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                self.rfile.read(content_length)
            
            try:
                # 1. Cargar credenciales de Tiendanube
                store_id = get_config_value('TiendaNubeStoreId')
                access_token = get_config_value('TiendaNubeAccessToken')
                user_agent = get_config_value('TiendaNubeUserAgent') or "QuieroTejer (administracion@quierotejer.com)"

                if not store_id or not access_token or not user_agent:
                    self.send_json_response(400, {"success": False, "error": "Credenciales de Tiendanube no configuradas."})
                    return

                # 2. Cargar todas las variantes locales para mapear rápido
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, sku, url_identifier, color_name, stock FROM product_variants WHERE is_active = TRUE")
                local_variants = cursor.fetchall()
                
                # Crear diccionarios de búsqueda
                by_sku = {}
                by_url_color = {}
                for lv in local_variants:
                    if lv['sku']:
                        by_sku[str(lv['sku']).strip().upper()] = lv
                    if lv['url_identifier'] and lv['color_name']:
                        key = (str(lv['url_identifier']).strip().lower(), str(lv['color_name']).strip().upper())
                        by_url_color[key] = lv

                # 3. Descargar catálogo completo de Tiendanube
                headers = {
                    "Authorization": f"Bearer {str(access_token).strip()}",
                    "User-Agent": str(user_agent).strip(),
                    "Content-Type": "application/json"
                }
                url = f"https://api.tiendanube.com/v1/{str(store_id).strip()}/products"
                page = 1
                updated_count = 0
                db_updates = []

                while True:
                    response = requests.get(url, headers=headers, params={"per_page": 200, "page": page}, timeout=15)
                    if response.status_code != 200:
                        break
                    products = response.json()
                    if not products:
                        break

                    for p in products:
                        url_id = p.get("handle", {}).get("es", p.get("handle", "")) if isinstance(p.get("handle"), dict) else p.get("handle", "")
                        for v in p.get("variants", []):
                            sku = v.get("sku")
                            stock = v.get("stock")
                            if stock is not None:
                                stock_val = int(stock)
                                matched_lv = None
                                
                                if sku:
                                    matched_lv = by_sku.get(str(sku).strip().upper())
                                
                                if not matched_lv and url_id:
                                    color_name = " / ".join([val.get("es", val.get("en", "")) for val in v.get("values", []) if isinstance(val, dict)])
                                    key = (str(url_id).strip().lower(), str(color_name).strip().upper())
                                    matched_lv = by_url_color.get(key)

                                if matched_lv:
                                    if matched_lv['stock'] != stock_val:
                                        db_updates.append((stock_val, matched_lv['id']))
                                        updated_count += 1

                    page += 1

                # 4. Guardar los cambios en lote
                if db_updates:
                    cursor.executemany("""
                        UPDATE product_variants
                        SET stock = %s, sync_status = 'Exportado', updated_at = NOW()
                        WHERE id = %s
                    """, db_updates)
                    conn.commit()
                
                conn.close()

                self.send_json_response(200, {
                    "success": True, 
                    "message": f"Sincronización completa. Se actualizaron {updated_count} variantes en Supabase."
                })

            except Exception as e:
                self.send_json_response(500, {"success": False, "error": str(e)})
            return

        self.send_error(404, "Endpoint no encontrado")

    def send_json_response(self, status, data):
        class DecimalEncoder(json.JSONEncoder):
            def default(self, obj):
                import decimal
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                return super(DecimalEncoder, self).default(obj)

        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, cls=DecimalEncoder).encode('utf-8'))

if __name__ == "__main__":
    # Asegurar que se sirve desde el directorio correcto
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with socketserver.TCPServer(("", PORT), MobileAPIHandler) as httpd:
        print(f"Servidor móvil corriendo en el puerto {PORT}")
        print(f"Visita http://localhost:{PORT} desde la PC")
        httpd.serve_forever()
