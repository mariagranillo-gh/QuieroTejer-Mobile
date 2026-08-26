// ─── CONFIGURACIÓN DE ESTADO GLOBAL ───
const state = {
    user: null,
    variants: [],
    models: [],
    selectedVariant: null,
    selectedCreateModelId: null,
    adjustmentQuantity: 0
};

// ─── ELEMENTOS DEL DOM ───
const DOM = {
    // Pantallas
    screens: document.querySelectorAll('.screen'),
    screenLogin: document.getElementById('screen-login'),
    screenHome: document.getElementById('screen-home'),
    screenStock: document.getElementById('screen-stock'),
    screenAlerts: document.getElementById('screen-alerts'),
    screenCreateColor: document.getElementById('screen-create-color'),
    screenUploadRemito: document.getElementById('screen-upload-remito'),
    screenReports: document.getElementById('screen-reports'),

    // Login
    loginForm: document.getElementById('login-form'),
    usernameInput: document.getElementById('username'),
    passwordInput: document.getElementById('password'),
    loginError: document.getElementById('login-error'),

    // Home
    homeUserGreeting: document.getElementById('home-user-greeting'),
    userRoleBadge: document.getElementById('user-role-badge'),
    btnLogout: document.getElementById('btn-logout'),
    btnGoToStock: document.getElementById('go-to-stock'),
    btnGoToCreateColor: document.getElementById('go-to-create-color'),
    btnGoToAlerts: document.getElementById('go-to-alerts'),
    btnGoToUploadRemito: document.getElementById('go-to-upload-remito'),
    btnGoToReports: document.getElementById('go-to-reports'),

    // Ajuste de Stock
    btnBackFromStock: document.getElementById('back-from-stock'),
    selectModel: document.getElementById('select-model'),
    selectColor: document.getElementById('select-color'),
    stockContainer: document.getElementById('stock-reference-container'),
    adjustSection: document.getElementById('adjustment-controls'),
    manualAdjustInput: document.getElementById('manual-adjust-input'),
    adjSign: document.getElementById('adj-sign'),
    btnSaveStock: document.getElementById('btn-save-stock'),
    stockFeedback: document.getElementById('stock-feedback'),

    // Agregar Color
    btnBackFromCreateColor: document.getElementById('back-from-create-color'),
    createSelectModel: document.getElementById('create-select-model'),
    createModelsDropdown: document.getElementById('create-models-dropdown-list'),
    createColorName: document.getElementById('create-color-name'),
    createInitialStock: document.getElementById('create-initial-stock'),
    btnCreatePlus1: document.getElementById('btn-create-plus-1'),
    btnCreatePlus5: document.getElementById('btn-create-plus-5'),
    btnCreatePlus10: document.getElementById('btn-create-plus-10'),
    btnCreateReset: document.getElementById('btn-create-reset'),
    btnSaveNewColor: document.getElementById('btn-save-new-color'),
    createColorFeedback: document.getElementById('create-color-feedback'),

    // Alertas / Consulta de Stock
    btnBackFromAlerts: document.getElementById('back-from-alerts'),
    alertsModel: document.getElementById('alerts-model'),
    alertsColor: document.getElementById('alerts-color'),
    alertsOperator: document.getElementById('alerts-operator'),
    alertsLimit: document.getElementById('alerts-limit'),
    btnShareWhatsApp: document.getElementById('btn-share-whatsapp'),
    alertsList: document.getElementById('alerts-list'),
    alertsLoading: document.getElementById('alerts-loading'),
    btnSyncCatalog: document.getElementById('btn-sync-catalog'),

    // Subir Remito
    btnBackFromUploadRemito: document.getElementById('back-from-upload-remito'),
    remitoFileInput: document.getElementById('remito-file-input'),
    remitoPreviewContainer: document.getElementById('remito-preview-container'),
    remitoPreviewImg: document.getElementById('remito-preview-img'),
    remitoPreviewFilename: document.getElementById('remito-preview-filename'),
    btnSubmitRemito: document.getElementById('btn-submit-remito'),
    uploadRemitoFeedback: document.getElementById('upload-remito-feedback'),

    // Reportes
    btnBackFromReports: document.getElementById('back-from-reports'),
    reportTotalWeight: document.getElementById('report-total-weight'),
    reportCategoriesContainer: document.getElementById('report-categories-container')
};

// ─── NAVEGACIÓN ENTRE PANTALLAS ───
function showScreen(screenElement) {
    DOM.screens.forEach(s => s.classList.remove('active'));
    screenElement.classList.add('active');
    screenElement.scrollTop = 0;
}

// ─── INICIALIZACIÓN ───
document.addEventListener('DOMContentLoaded', () => {
    const savedUser = localStorage.getItem('qt_mobile_user');
    if (savedUser) {
        state.user = JSON.parse(savedUser);
        setupSession();
    } else {
        showScreen(DOM.screenLogin);
    }
    setupEventListeners();
});

function setupSession() {
    DOM.homeUserGreeting.textContent = `Hola, ${state.user.full_name || state.user.username} 👋`;
    DOM.userRoleBadge.textContent = state.user.role;
    
    // Solo permitir visualizar el reporte si el rol es 'admin'
    if (state.user.role === 'admin') {
        DOM.btnGoToReports.style.display = 'flex';
    } else {
        DOM.btnGoToReports.style.display = 'none';
    }
    
    showScreen(DOM.screenHome);
    fetchVariants();
    fetchModels();
}

// ─── CARGA DE MODELOS EN MEMORIA ───
async function fetchModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        if (data.success) {
            state.models = data.models;
        } else {
            console.error("Error al cargar modelos:", data.error);
        }
    } catch (err) {
        console.error("Fallo de conexión al cargar modelos:", err);
    }
}

// ─── CARGA DE VARIANTES EN MEMORIA ───
async function fetchVariants() {
    try {
        const response = await fetch('/api/variants');
        const data = await response.json();
        if (data.success) {
            state.variants = data.variants;
            populateModelsDatalist();
        } else {
            console.error("Error al cargar variantes:", data.error);
        }
    } catch (err) {
        console.error("Fallo de conexión al cargar variantes:", err);
    }
}

// Llenar el datalist para autocompletar modelos
function populateModelsDatalist() {
    DOM.selectModel.value = '';
    DOM.selectColor.innerHTML = '<option value="">Seleccione un color...</option>';
    DOM.selectColor.disabled = true;
    DOM.stockContainer.classList.add('hidden');
    DOM.adjustSection.classList.add('hidden');
}

function getValidModels() {
    const modelsSet = new Set();
    state.variants.forEach(v => {
        const parts = v.display_name.split(' - ');
        if (parts.length > 0) {
            modelsSet.add(parts[0]);
        }
    });
    return modelsSet;
}

function setupSearchableSelect(inputId, dropdownId, getOptionsCallback, onSelectCallback) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    
    input.addEventListener('focus', () => {
        renderOptions(input.value);
    });
    
    input.addEventListener('input', () => {
        renderOptions(input.value);
    });
    
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    });

    function renderOptions(filterText) {
        const query = filterText.trim().toUpperCase();
        const allOptions = getOptionsCallback();
        
        const filtered = allOptions.filter(opt => opt.toUpperCase().includes(query));
        
        if (filtered.length === 0) {
            dropdown.innerHTML = '<div class="custom-dropdown-item" style="color: var(--text-muted); cursor: default;">No se encontraron resultados</div>';
        } else {
            dropdown.innerHTML = '';
            filtered.forEach(opt => {
                const item = document.createElement('div');
                item.className = 'custom-dropdown-item';
                item.textContent = opt;
                item.addEventListener('click', () => {
                    input.value = opt;
                    dropdown.classList.add('hidden');
                    onSelectCallback(opt);
                });
                dropdown.appendChild(item);
            });
        }
        dropdown.classList.remove('hidden');
    }
}

// Manejar cambios en el campo autocompletable de modelo
function handleModelChange() {
    const typedModel = DOM.selectModel.value.trim();
    const validModels = getValidModels();

    DOM.stockContainer.classList.add('hidden');
    DOM.adjustSection.classList.add('hidden');
    DOM.stockFeedback.style.display = 'none';
    state.selectedVariant = null;

    // Solo cargar los colores si el valor ingresado corresponde a un modelo real
    if (!typedModel || !validModels.has(typedModel)) {
        DOM.selectColor.innerHTML = '<option value="">Seleccione un color...</option>';
        DOM.selectColor.disabled = true;
        return;
    }

    // Filtrar las variantes por modelo
    const colors = state.variants.filter(v => {
        return v.display_name.startsWith(typedModel + ' - ');
    }).map(v => {
        const parts = v.display_name.split(' - ');
        return {
            id: v.id,
            color_name: parts.slice(1).join(' - '),
            stock: v.stock
        };
    });

    // Llenar selector de color
    DOM.selectColor.innerHTML = '<option value="">Seleccione un color...</option>';
    colors.sort((a, b) => a.color_name.localeCompare(b.color_name)).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.color_name;
        DOM.selectColor.appendChild(opt);
    });

    DOM.selectColor.disabled = false;
}

// Manejar selección de variante/color y cargar stock en tiempo real
async function handleColorChange() {
    const variantId = parseInt(DOM.selectColor.value);
    DOM.stockFeedback.style.display = 'none';
    
    if (isNaN(variantId)) {
        DOM.stockContainer.classList.add('hidden');
        DOM.adjustSection.classList.add('hidden');
        state.selectedVariant = null;
        return;
    }

    state.selectedVariant = state.variants.find(v => v.id === variantId);
    
    if (state.selectedVariant) {
        // Inicializar controles de ajuste táctil a 0
        state.adjustmentQuantity = 0;
        DOM.manualAdjustInput.value = '';
        DOM.adjSign.textContent = '';
        DOM.adjustSection.classList.remove('hidden');

        // Cargar stocks (local y en vivo de Tiendanube)
        await fetchLiveStock(variantId);
    }
}

// Consultar stock local y en Tiendanube por API
async function fetchLiveStock(variantId) {
    DOM.stockContainer.innerHTML = '⏳ Cargando información de stock...';
    DOM.stockContainer.classList.remove('hidden');

    try {
        const response = await fetch(`/api/live_stock?variant_id=${variantId}`);
        const data = await response.json();
        
        if (data.success) {
            // Actualizar stock local en caché por si cambió en segundo plano
            state.selectedVariant.stock = data.local_stock;
            const idx = state.variants.findIndex(v => v.id === variantId);
            if (idx !== -1) {
                state.variants[idx].stock = data.local_stock;
            }

            // Mostrar la línea de referencia solo con el stock de Tiendanube
            DOM.stockContainer.innerHTML = `
                ☁️ **Stock en Tiendanube:** ${data.tiendanube_stock}
            `;
        } else {
            DOM.stockContainer.innerHTML = `⚠️ Error al obtener stock: ${data.error}`;
        }
    } catch (err) {
        DOM.stockContainer.innerHTML = '⚠️ Fallo al conectar con el servidor móvil.';
    }
}

// ─── CARGA Y FILTRADO DE CONSULTA DE STOCK ───
async function fetchAlerts() {
    DOM.alertsLoading.style.display = 'block';
    DOM.alertsList.innerHTML = '';
    
    const limit = DOM.alertsLimit ? DOM.alertsLimit.value : 10;
    const operator = DOM.alertsOperator ? DOM.alertsOperator.value : '>=';
    
    try {
        const response = await fetch(`/api/alerts?min_stock=${encodeURIComponent(limit)}&operator=${encodeURIComponent(operator)}`);
        const data = await response.json();
        DOM.alertsLoading.style.display = 'none';
        
        if (data.success) {
            state.alerts = data.alerts;
            renderAlertsList(data.alerts);
        } else {
            DOM.alertsList.innerHTML = `<div class="alerts-status error">Error: ${data.error}</div>`;
        }
    } catch (err) {
        DOM.alertsLoading.style.display = 'none';
        DOM.alertsList.innerHTML = `<div class="alerts-status error">Error de conexión con el servidor.</div>`;
    }
}

function handleAlertsModelChange() {
    const typedModel = DOM.alertsModel.value.trim();
    const validModels = getValidModels();

    if (!typedModel || !validModels.has(typedModel)) {
        DOM.alertsColor.innerHTML = '<option value="">Todos los colores...</option>';
        DOM.alertsColor.disabled = true;
        return;
    }

    // Filtrar los colores del modelo ingresado
    const colors = new Set();
    state.variants.forEach(v => {
        if (v.display_name.startsWith(typedModel + ' - ')) {
            const parts = v.display_name.split(' - ');
            colors.add(parts.slice(1).join(' - '));
        }
    });

    DOM.alertsColor.innerHTML = '<option value="">Todos los colores...</option>';
    Array.from(colors).sort().forEach(colorName => {
        const opt = document.createElement('option');
        opt.value = colorName;
        opt.textContent = colorName;
        DOM.alertsColor.appendChild(opt);
    });
    DOM.alertsColor.disabled = false;
}

function renderAlertsList(alerts) {
    const modelVal = DOM.alertsModel.value.trim().toUpperCase();
    const colorVal = DOM.alertsColor.value.trim().toUpperCase();
    
    let filteredAlerts = alerts;
    if (modelVal) {
        filteredAlerts = filteredAlerts.filter(a => a.model_name.toUpperCase().includes(modelVal));
    }
    if (colorVal) {
        filteredAlerts = filteredAlerts.filter(a => a.color_name.toUpperCase().includes(colorVal));
    }

    if (filteredAlerts.length === 0) {
        DOM.alertsList.innerHTML = '<div class="alerts-status">No se encontraron productos con ese criterio.</div>';
        return;
    }

    DOM.alertsList.innerHTML = '';
    filteredAlerts.forEach(a => {
        const card = document.createElement('div');
        card.className = 'alert-card';
        
        const stock = a.stock ?? 0;
        let badgeClass = 'available';
        let badgeText = `${stock} u`;
        
        if (stock <= 0) {
            badgeClass = 'critical';
            badgeText = 'Sin Stock (0 u)';
        } else if (stock <= 10) {
            badgeClass = 'low';
            badgeText = `${stock} u`;
        }

        card.innerHTML = `
            <div class="alert-info">
                <div class="alert-model">${a.model_name}</div>
                <div class="alert-color">${a.color_name}</div>
            </div>
            <span class="alert-badge ${badgeClass}">${badgeText}</span>
        `;
        DOM.alertsList.appendChild(card);
    });
}

// ─── EVENT LISTENERS ───
function setupEventListeners() {
    
    // FORMULARIO LOGIN
    DOM.loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        DOM.loginError.textContent = '';
        
        const username = DOM.usernameInput.value.trim();
        const password = DOM.passwordInput.value.trim();

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await response.json();
            
            if (data.success) {
                state.user = data.user;
                localStorage.setItem('qt_mobile_user', JSON.stringify(data.user));
                setupSession();
            } else {
                DOM.loginError.textContent = data.error || 'Credenciales inválidas.';
            }
        } catch (err) {
            DOM.loginError.textContent = 'Error de conexión con el servidor.';
        }
    });

    // CERRAR SESIÓN
    DOM.btnLogout.addEventListener('click', () => {
        state.user = null;
        localStorage.removeItem('qt_mobile_user');
        DOM.usernameInput.value = '';
        DOM.passwordInput.value = '';
        showScreen(DOM.screenLogin);
    });

    // RUTA HASTA SECCIONES
    DOM.btnGoToStock.addEventListener('click', () => {
        DOM.selectModel.value = '';
        handleModelChange();
        showScreen(DOM.screenStock);
    });

    DOM.btnGoToCreateColor.addEventListener('click', () => {
        DOM.createSelectModel.value = '';
        state.selectedCreateModelId = null;
        DOM.createColorName.value = '';
        DOM.createInitialStock.value = '0';
        DOM.createColorFeedback.style.display = 'none';
        showScreen(DOM.screenCreateColor);
    });

    DOM.btnGoToAlerts.addEventListener('click', () => {
        DOM.alertsModel.value = '';
        DOM.alertsColor.innerHTML = '<option value="">Seleccione un color...</option>';
        DOM.alertsColor.disabled = true;
        fetchAlerts();
        showScreen(DOM.screenAlerts);
    });

    DOM.btnGoToUploadRemito.addEventListener('click', () => {
        DOM.remitoFileInput.value = '';
        DOM.remitoPreviewContainer.style.display = 'none';
        DOM.btnSubmitRemito.style.display = 'none';
        DOM.uploadRemitoFeedback.style.display = 'none';
        showScreen(DOM.screenUploadRemito);
    });

    DOM.btnGoToReports.addEventListener('click', () => {
        loadReportData();
        showScreen(DOM.screenReports);
    });

    DOM.btnBackFromStock.addEventListener('click', () => showScreen(DOM.screenHome));
    DOM.btnBackFromCreateColor.addEventListener('click', () => showScreen(DOM.screenHome));
    DOM.btnBackFromAlerts.addEventListener('click', () => showScreen(DOM.screenHome));
    DOM.btnBackFromUploadRemito.addEventListener('click', () => showScreen(DOM.screenHome));
    DOM.btnBackFromReports.addEventListener('click', () => showScreen(DOM.screenHome));

    // EVENTOS SUBIR REMITO DESDE ARCHIVO
    DOM.remitoFileInput.addEventListener('change', handleRemitoFileSelect);
    DOM.btnSubmitRemito.addEventListener('click', handleRemitoUploadSubmit);

    // EVENTOS INPUT MODELO Y COLOR
    DOM.selectModel.addEventListener('input', handleModelChange);
    DOM.selectColor.addEventListener('change', handleColorChange);

    // BOTONES DE AJUSTE RÁPIDO (+1, -1, etc.)
    document.querySelectorAll('.btn-adjust').forEach(btn => {
        btn.addEventListener('click', () => {
            const val = parseInt(btn.getAttribute('data-val'));
            state.adjustmentQuantity += val;
            updateAdjustmentInput();
        });
    });

    // CONTROL INPUT MANUAL DE CANTIDAD
    DOM.manualAdjustInput.addEventListener('input', () => {
        const val = parseInt(DOM.manualAdjustInput.value);
        state.adjustmentQuantity = isNaN(val) ? 0 : val;
        updateSignLabel();
    });

    // GUARDAR AJUSTE
    DOM.btnSaveStock.addEventListener('click', saveStockAdjustment);

    // SINCRONIZAR CATÁLOGO COMPLETO
    DOM.btnSyncCatalog.addEventListener('click', syncCatalog);

    // FILTROS DE ALERTAS EN VIVO
    DOM.alertsModel.addEventListener('input', () => {
        handleAlertsModelChange();
        fetchAlerts();
    });
    DOM.alertsColor.addEventListener('change', fetchAlerts);
    DOM.alertsOperator.addEventListener('change', fetchAlerts);
    DOM.alertsLimit.addEventListener('change', fetchAlerts);
    if (DOM.btnShareWhatsApp) {
        DOM.btnShareWhatsApp.addEventListener('click', shareStockOnWhatsApp);
    }

    // Configurar selectores autocompletables personalizados (estilo dropdown)
    setupSearchableSelect('select-model', 'models-dropdown-list', 
        () => Array.from(getValidModels()).sort(), 
        (val) => {
            handleModelChange();
        }
    );

    setupSearchableSelect('alerts-model', 'alerts-models-list', 
        () => Array.from(getValidModels()).sort(), 
        (val) => {
            handleAlertsModelChange();
            fetchAlerts();
        }
    );
}

function updateAdjustmentInput() {
    DOM.manualAdjustInput.value = state.adjustmentQuantity === 0 ? '' : state.adjustmentQuantity;
    updateSignLabel();
}

function updateSignLabel() {
    if (state.adjustmentQuantity > 0) {
        DOM.adjSign.textContent = '+';
        DOM.adjSign.style.color = 'var(--success)';
        DOM.manualAdjustInput.style.color = 'var(--success)';
    } else if (state.adjustmentQuantity < 0) {
        DOM.adjSign.textContent = '';
        DOM.adjSign.style.color = 'var(--danger)';
        DOM.manualAdjustInput.style.color = 'var(--danger)';
    } else {
        DOM.adjSign.textContent = '';
        DOM.manualAdjustInput.style.color = 'var(--primary-hover)';
    }
}

// ─── GUARDAR AJUSTE Y SINCRONIZAR ───
async function saveStockAdjustment() {
    if (!state.selectedVariant || state.adjustmentQuantity === 0) {
        showFeedback("Por favor indique una cantidad de ajuste diferente de 0.", "error");
        return;
    }

    DOM.btnSaveStock.disabled = true;
    DOM.btnSaveStock.textContent = "💾 Sincronizando...";
    DOM.stockFeedback.style.display = 'none';

    try {
        const response = await fetch('/api/adjust_stock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                variant_id: state.selectedVariant.id,
                quantity: state.adjustmentQuantity,
                username: state.user.username
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Mostrar mensaje exitoso
            showFeedback(data.message, data.sync_success ? "success" : "warning");
            
            // Recargar información de stock actual (local y Tiendanube) en la línea de referencia
            await fetchLiveStock(state.selectedVariant.id);

            // Reiniciar inputs de ajuste a 0
            state.adjustmentQuantity = 0;
            updateAdjustmentInput();
        } else {
            showFeedback(`Error: ${data.error}`, "error");
        }
    } catch (err) {
        showFeedback("Fallo de conexión al enviar el ajuste de stock.", "error");
    } finally {
        DOM.btnSaveStock.disabled = false;
        DOM.btnSaveStock.textContent = "💾 Guardar y Sincronizar";
    }
}

function showFeedback(msg, type) {
    DOM.stockFeedback.textContent = msg;
    DOM.stockFeedback.className = `feedback-toast ${type}`;
    DOM.stockFeedback.style.display = 'block';
}

async function syncCatalog() {
    DOM.btnSyncCatalog.disabled = true;
    DOM.btnSyncCatalog.textContent = "⏳ Sincronizando catálogo... (12s)";
    
    try {
        const response = await fetch('/api/sync_catalog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (data.success) {
            alert(data.message);
            // Recargar variantes locales en caché y refrescar pantalla de alertas
            await fetchVariants();
            await fetchModels();
            await fetchAlerts();
        } else {
            alert(`Error de sincronización: ${data.error}`);
        }
    } catch (err) {
        alert("Fallo de conexión al sincronizar el catálogo.");
    } finally {
        DOM.btnSyncCatalog.disabled = false;
        DOM.btnSyncCatalog.textContent = "🔄 Sincronizar con Tiendanube";
    }
}

// ─── LÓGICA DE AGREGAR COLOR ───
function setupCreateModelEvents() {
    setupSearchableSelect(
        'create-select-model',
        'create-models-dropdown-list',
        () => state.models.map(m => m.name),
        (selectedName) => {
            const m = state.models.find(x => x.name.toUpperCase() === selectedName.toUpperCase());
            if (m) {
                state.selectedCreateModelId = m.id;
            }
            DOM.createColorName.focus();
        }
    );

    DOM.createSelectModel.addEventListener('input', () => {
        const typed = DOM.createSelectModel.value.trim().toUpperCase();
        const m = state.models.find(x => x.name.toUpperCase() === typed);
        state.selectedCreateModelId = m ? m.id : null;
    });

    DOM.createColorName.addEventListener('input', (e) => {
        const start = e.target.selectionStart;
        const end = e.target.selectionEnd;
        e.target.value = e.target.value.toUpperCase();
        e.target.setSelectionRange(start, end);
    });

    DOM.btnCreatePlus1.addEventListener('click', () => {
        DOM.createInitialStock.value = parseInt(DOM.createInitialStock.value || 0) + 1;
    });
    DOM.btnCreatePlus5.addEventListener('click', () => {
        DOM.createInitialStock.value = parseInt(DOM.createInitialStock.value || 0) + 5;
    });
    DOM.btnCreatePlus10.addEventListener('click', () => {
        DOM.createInitialStock.value = parseInt(DOM.createInitialStock.value || 0) + 10;
    });
    DOM.btnCreateReset.addEventListener('click', () => {
        DOM.createInitialStock.value = 0;
    });

    DOM.btnSaveNewColor.addEventListener('click', handleSaveNewColor);
}

async function handleSaveNewColor() {
    const modelId = state.selectedCreateModelId;
    const modelName = DOM.createSelectModel.value.trim();
    const colorName = DOM.createColorName.value.trim().toUpperCase();
    const stock = parseInt(DOM.createInitialStock.value || 0);

    if (!modelId) {
        showCreateFeedback("⚠️ Por favor, selecciona un modelo de la lista autocompletable.", "error");
        DOM.createSelectModel.focus();
        return;
    }
    if (!colorName) {
        showCreateFeedback("⚠️ Por favor, ingresa el nombre del nuevo color.", "error");
        DOM.createColorName.focus();
        return;
    }

    DOM.btnSaveNewColor.disabled = true;
    DOM.btnSaveNewColor.textContent = "⏳ Creando y sincronizando con Tiendanube...";
    DOM.createColorFeedback.style.display = 'none';

    try {
        const response = await fetch('/api/create_variant', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_id: modelId,
                color_name: colorName,
                stock: stock,
                username: state.user ? (state.user.full_name || state.user.username) : 'Celular PWA'
            })
        });
        const data = await response.json();

        if (data.success) {
            showCreateFeedback(`✅ ${data.message}`, "success");
            DOM.createColorName.value = '';
            DOM.createInitialStock.value = '0';
            
            // Recargar variantes para que aparezca de inmediato en Ajuste de Stock
            await fetchVariants();
        } else {
            showCreateFeedback(`❌ ${data.error}`, "error");
        }
    } catch (err) {
        showCreateFeedback("❌ Error de conexión al crear el color.", "error");
    } finally {
        DOM.btnSaveNewColor.disabled = false;
        DOM.btnSaveNewColor.textContent = "💾 Guardar y Crear Color";
    }
}

function showCreateFeedback(msg, type) {
    DOM.createColorFeedback.textContent = msg;
    DOM.createColorFeedback.className = `feedback-toast ${type}`;
    DOM.createColorFeedback.style.display = 'block';
}

// ─── COMPARTIR POR WHATSAPP ───
function shareStockOnWhatsApp() {
    const modelVal = DOM.alertsModel.value.trim();
    const colorVal = DOM.alertsColor.value.trim();
    const op = DOM.alertsOperator ? DOM.alertsOperator.value : '>=';
    const limit = DOM.alertsLimit ? DOM.alertsLimit.value : 10;
    
    let list = state.alerts || [];
    if (modelVal) {
        list = list.filter(a => a.model_name.toUpperCase().includes(modelVal.toUpperCase()));
    }
    if (colorVal) {
        list = list.filter(a => a.color_name.toUpperCase().includes(colorVal.toUpperCase()));
    }
    
    if (list.length === 0) {
        alert("No hay productos en la lista para compartir.");
        return;
    }
    
    const grouped = {};
    list.forEach(item => {
        if (!grouped[item.model_name]) {
            grouped[item.model_name] = [];
        }
        grouped[item.model_name].push(item);
    });
    
    const isDisponibles = (op === '>=');
    let text = isDisponibles ? `🧶 *Disponibilidad Mayorista - QuieroTejer*\n` : `🧶 *Faltantes de Stock - QuieroTejer*\n`;
    if (modelVal) text += `📦 *Modelo:* ${modelVal}\n`;
    text += `📊 *Filtro:* Stock ${op} ${limit} u\n\n`;
    
    const sortedModelNames = Object.keys(grouped).sort();
    for (const model of sortedModelNames) {
        const variants = grouped[model];
        // Ordenar variantes alfabéticamente por color
        variants.sort((a, b) => a.color_name.localeCompare(b.color_name));
        
        text += `*${model}:*\n`;
        variants.forEach(v => {
            if (isDisponibles) {
                const weightKg = parseFloat(v.weight || 0.100);
                const totalKg = v.stock * weightKg;
                const floorKg = Math.floor(totalKg);
                text += `  • ${v.color_name}: ${floorKg}k\n`;
            } else {
                text += `  • ${v.color_name}: ${v.stock} u\n`;
            }
        });
        text += `\n`;
    }
    
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            alert("📋 ¡Lista copiada al portapapeles! Ya podés pegarla en WhatsApp.");
        }).catch(() => {
            window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
        });
    } else {
        window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
    }
}

// Llamar inicialización de eventos de agregar color
setupCreateModelEvents();

// ─── LÓGICA DE SUBIR REMITO DESDE EL CELULAR ───
let remitoFileBase64 = null;
let remitoFileName = "";
let remitoFileType = "";

function handleRemitoFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    remitoFileName = file.name;
    remitoFileType = file.type;
    DOM.remitoPreviewFilename.textContent = file.name;
    
    const reader = new FileReader();
    reader.onload = function(evt) {
        remitoFileBase64 = evt.target.result.split(',')[1];
        
        // Si es una imagen, mostrar previsualización
        if (file.type.startsWith('image/')) {
            DOM.remitoPreviewImg.src = evt.target.result;
            DOM.remitoPreviewImg.style.display = 'inline-block';
        } else {
            // Si es PDF u otro, ocultar imagen
            DOM.remitoPreviewImg.style.display = 'none';
        }
        DOM.remitoPreviewContainer.style.display = 'block';
        DOM.btnSubmitRemito.style.display = 'inline-block';
    };
    reader.readAsDataURL(file);
}

async function handleRemitoUploadSubmit() {
    if (!remitoFileBase64) return;
    
    DOM.btnSubmitRemito.disabled = true;
    DOM.btnSubmitRemito.textContent = "⏳ Subiendo remito...";
    DOM.uploadRemitoFeedback.style.display = 'none';
    
    try {
        const response = await fetch('/api/upload_mobile_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: remitoFileName,
                mime_type: remitoFileType,
                file_base64: remitoFileBase64
            })
        });
        const data = await response.json();
        
        if (data.success) {
            showRemitoFeedback("✅ ¡Remito subido con éxito! Ya podés verlo y procesarlo en la PC.", "success");
            DOM.remitoFileInput.value = '';
            DOM.remitoPreviewContainer.style.display = 'none';
            DOM.btnSubmitRemito.style.display = 'none';
        } else {
            showRemitoFeedback(`❌ Error: ${data.error}`, "error");
        }
    } catch (err) {
        showRemitoFeedback("❌ Error de conexión al subir el archivo.", "error");
    } finally {
        DOM.btnSubmitRemito.disabled = false;
        DOM.btnSubmitRemito.textContent = "📤 Subir Remito para PC";
    }
}

function showRemitoFeedback(msg, type) {
    DOM.uploadRemitoFeedback.textContent = msg;
    DOM.uploadRemitoFeedback.className = `feedback-toast ${type}`;
    DOM.uploadRemitoFeedback.style.display = 'block';
}

async function loadReportData() {
    DOM.reportTotalWeight.textContent = "⏳ Cargando...";
    DOM.reportCategoriesContainer.innerHTML = '<div style="text-align: center; color: #64748b; padding: 20px;">Cargando reporte de stock...</div>';
    
    try {
        const response = await fetch('/api/reports');
        const data = await response.json();
        
        if (data.success) {
            // Formatear peso total
            const totalWeight = parseFloat(data.total_weight_kg || 0);
            DOM.reportTotalWeight.textContent = `${totalWeight.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kg`;
            
            // Generar distribución por categorías
            if (data.categories && data.categories.length > 0) {
                let html = '';
                data.categories.forEach(cat => {
                    const catName = cat.main_category || 'SIN CATEGORÍA';
                    const catWeight = parseFloat(cat.total_weight_kg || 0);
                    const catUnits = parseInt(cat.total_units || 0);
                    
                    html += `
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background-color: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
                            <div>
                                <div style="font-weight: 700; color: #334155; font-size: 0.95rem;">${catName}</div>
                                <div style="font-size: 0.8rem; color: #64748b; margin-top: 2px;">${catUnits.toLocaleString('es-AR')} unidades</div>
                            </div>
                            <div style="font-weight: 800; color: #0f172a; font-size: 1.1rem; text-align: right;">
                                ${catWeight.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kg
                            </div>
                        </div>
                    `;
                });
                DOM.reportCategoriesContainer.innerHTML = html;
            } else {
                DOM.reportCategoriesContainer.innerHTML = '<div style="text-align: center; color: #64748b; padding: 20px;">No hay stock activo para reportar.</div>';
            }
        } else {
            DOM.reportTotalWeight.textContent = "Error";
            DOM.reportCategoriesContainer.innerHTML = `<div style="text-align: center; color: #ef4444; padding: 20px;">Error: ${data.error}</div>`;
        }
    } catch (err) {
        DOM.reportTotalWeight.textContent = "Error";
        DOM.reportCategoriesContainer.innerHTML = '<div style="text-align: center; color: #ef4444; padding: 20px;">Error de conexión con el servidor.</div>';
    }
}
