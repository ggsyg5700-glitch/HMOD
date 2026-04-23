// دالة موحدة لفتح مودال المنتج
function openProductModal(item) {
    const titleEl  = document.getElementById('productModalTitle');
    const idEl     = document.getElementById('edit-product-id');
    const nameEl   = document.getElementById('edit-product-name');
    const priceEl  = document.getElementById('edit-product-price');
    const descEl   = document.getElementById('edit-product-desc');

    if (titleEl)  titleEl.textContent = item ? 'تعديل المنتج' : 'إضافة منتج جديد';
    if (idEl)     idEl.value    = item ? item.id : '';
    if (nameEl)   nameEl.value  = item ? item.name : '';
    if (priceEl)  priceEl.value = item ? item.price : '';
    if (descEl)   descEl.value  = item ? (item.description || '') : '';

    const modalEl = document.getElementById('productModal');
    if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

let productModal = null;

// Ensure functions are global for HTML event handlers
window.showToast = function(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-dark border-0 show mb-2 fade-in shadow-sm`;
    toast.role = 'alert';
    const icon = type === 'success' ? 'fa-check-circle text-success' : type === 'danger' ? 'fa-exclamation-triangle text-danger' : 'fa-info-circle text-info';
    toast.innerHTML = `
        <div class="d-flex p-3">
            <div class="toast-body fw-bold d-flex align-items-center">
                <i class="fas ${icon} fa-lg me-3 ms-3"></i>
                <span>${message}</span>
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 500);
    }, 4000);
};

window.apiCall = async function(url, method = 'GET', body = null) {
    const token = localStorage.getItem('admin_token');
    try {
        const res = await fetch(url, {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': token || ''
            },
            body: body ? JSON.stringify(body) : null
        });
        
        if (res.status === 403 || res.status === 401) {
            localStorage.removeItem('admin_token');
            const authScreen = document.getElementById('auth-screen');
            const mainApp = document.getElementById('main-app');
            if (authScreen) authScreen.style.display = 'flex';
            if (mainApp) mainApp.style.display = 'none';
            return { success: false };
        }
        
        return await res.json();
    } catch (e) {
        console.error('API Call failed:', e);
        return { success: false };
    }
};

window.authenticateUser = async function() {
    const passwordInput = document.getElementById('password-input');
    if (!passwordInput) return;
    const password = passwordInput.value;
    const res = await window.apiCall('/api/auth', 'POST', { password });
    if (res.success) {
        localStorage.setItem('admin_token', res.token);
        const authScreen = document.getElementById('auth-screen');
        const mainApp = document.getElementById('main-app');
        if (authScreen) authScreen.style.display = 'none';
        if (mainApp) {
            mainApp.style.display = 'block';
            mainApp.classList.add('fade-in');
        }
        window.loadStatus();
        window.showToast("تم تسجيل الدخول بنجاح");
    } else {
        window.showToast('كلمة المرور خاطئة!', 'danger');
    }
};

window.refreshSystem = async function() {
    const modalEl = document.getElementById('countdownModal');
    if (!modalEl) return;
    const modal = new bootstrap.Modal(modalEl);
    const textEl = document.getElementById('countdown-text');
    const numEl = document.getElementById('countdown-number');
    
    modal.show();
    if (textEl) textEl.textContent = "سيتم تحديث النظام";
    
    let count = 3;
    if (numEl) numEl.textContent = count;
    
    const timer = setInterval(() => {
        count--;
        if (count > 0) {
            if (numEl) numEl.textContent = count;
        } else if (count === 0) {
            if (numEl) numEl.textContent = "";
            if (textEl) textEl.textContent = "يتم تشغيل النظام";
            if (numEl) numEl.innerHTML = '<i class="fas fa-sync fa-spin"></i>';
        } else if (count === -1) {
            clearInterval(timer);
            window.loadStatus().then(() => {
                setTimeout(() => {
                    modal.hide();
                    window.showToast("تم تحديث حالة النظام بنجاح");
                }, 1000);
            });
        }
    }, 1000);
};

window.loadStatus = async function() {
    const res = await window.apiCall('/api/status');
    if (res.success) {
        const uptimeEl = document.getElementById('stat-uptime');
        const usersEl = document.getElementById('stat-users');
        const balanceEl = document.getElementById('stat-balance');
        const ordersEl = document.getElementById('stat-orders');
        
        if (uptimeEl) uptimeEl.textContent = res.data.uptime || '--';
        if (usersEl) usersEl.textContent = res.data.users_count || '0';
        if (balanceEl) balanceEl.textContent = `${Math.floor(res.data.total_balance)} ل.س`;
        if (ordersEl) ordersEl.textContent = res.data.orders_count || '0';
        
        const stats = res.data.order_stats;
        const statsHtml = `
            <div class="col-12 mt-3 fade-in">
                <div class="card bg-secondary p-3 border-0 rounded-4 shadow-sm">
                    <h5 class="text-accent fw-bold mb-3"><i class="fas fa-chart-pie me-2"></i>لوحة إحصائيات الطلبات للادمن</h5>
                    <div class="d-flex justify-content-around">
                        <div class="text-center" style="cursor:pointer" onclick="window.showSection('orders')">
                            <div class="text-warning h4 mb-0 animate-pulse">${stats.pending}</div>
                            <div class="small text-white-50 fw-bold">قيد الانتظار</div>
                        </div>
                        <div class="text-center" style="cursor:pointer" onclick="window.showSection('orders')">
                            <div class="text-success h4 mb-0">${stats.completed}</div>
                            <div class="small text-white-50 fw-bold">مكتمل</div>
                        </div>
                        <div class="text-center" style="cursor:pointer" onclick="window.showSection('orders')">
                            <div class="text-danger h4 mb-0">${stats.rejected}</div>
                            <div class="small text-white-50 fw-bold">مرفوض</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        const activeContainer = document.getElementById('active-users-list');
        if (activeContainer) {
            let userHtml = '';
            if (res.data.active_users && res.data.active_users.length > 0) {
                userHtml = res.data.active_users.map(u => `
                    <div class="col-md-4 col-sm-6 fade-in mb-2">
                        <div class="d-flex justify-content-between align-items-center p-2 bg-secondary rounded border border-secondary shadow-sm" style="cursor:pointer" onclick="window.showSection('users')">
                            <div class="d-flex flex-column text-end" style="width: 100%;">
                                <span class="text-white small fw-bold">@${u.username}</span>
                                <div class="d-flex justify-content-between align-items-center mt-1">
                                    <span class="badge bg-success" style="font-size: 0.6rem;">متصل</span>
                                    <span class="text-white-50" style="font-size: 0.6rem;">${u.last_seen}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('');
            } else {
                userHtml = '<div class="col-12 text-muted small text-center p-3">لا يوجد مستخدمين نشطين حالياً</div>';
            }
            activeContainer.innerHTML = userHtml + statsHtml;
        }
    }
};

window.loadUsers = async function() {
    const res = await window.apiCall('/api/users');
    if (res.success) {
        const tbody = document.getElementById('users-table');
        if (!tbody) return;
        tbody.innerHTML = res.data.map(u => `
            <tr class="fade-in align-middle">
                <td><strong class="text-white">@${u.username}</strong></td>
                <td><code class='text-accent'>${u.id}</code></td>
                <td><span class='badge bg-success px-3 fs-6'>${u.balance} ل.س</span></td>
                <td class='text-white small'>${u.last_seen || 'غير متوفر'}</td>
                <td>
                    <button class='btn btn-sm btn-info fw-bold' onclick='window.editBalance("${u.id}")'>تعديل الرصيد</button>
                </td>
            </tr>
        `).join('');
    }
};

window.loadOrders = async function() {
    const container = document.getElementById('orders-container');
    if (!container) return;
    container.innerHTML = '<div class="text-center p-5"><i class="fas fa-spinner fa-spin fa-2x text-accent"></i><p class="text-muted mt-3">جاري تحميل الطلبات...</p></div>';
    const res = await window.apiCall('/api/orders');
    if (!res.success) { container.innerHTML = '<p class="text-danger text-center p-4">فشل تحميل الطلبات</p>'; return; }

    window._pendingOrdersMap = {};
    const pending = res.data.filter(o => o.status === 'قيد الانتظار').reverse();
    pending.forEach(o => { window._pendingOrdersMap[o.id] = o; });
    const purchaseCompleted = res.data.filter(o => o.status === 'مكتمل' && !(o.item_name || '').includes("شحن رصيد")).reverse();
    const rechargeCompleted = res.data.filter(o => o.status === 'مكتمل' && (o.item_name || '').includes("شحن رصيد")).reverse();
    const rejected = res.data.filter(o => o.status === 'مرفوض').reverse();

    const statusColor = { 'مكتمل': '#28a745', 'مرفوض': '#dc3545', 'قيد الانتظار': '#ffc107' };
    const statusIcon  = { 'مكتمل': 'fa-check-circle', 'مرفوض': 'fa-times-circle', 'قيد الانتظار': 'fa-hourglass-half' };

    const renderOrder = (o) => {
        const isRecharge = (o.item_name || '').includes('شحن رصيد');
        const transId = o.transaction_id || o.game_id || ((o.item_name || '').match(/\(([^)]+)\)/) || [])[1] || 'N/A';
        const thirdCardLabel = isRecharge ? '<i class="fas fa-receipt me-1"></i>رقم عملية التحويل' : '<i class="fas fa-gamepad me-1"></i>ID اللعبة';
        const thirdCardValue = isRecharge ? transId : (o.game_id || 'N/A');
        return `
        <div style="
            background: linear-gradient(135deg, #1c1c1c 0%, #242424 100%);
            border-radius: 16px;
            border: 1px solid ${statusColor[o.status] || '#444'}44;
            border-right: 4px solid ${statusColor[o.status] || '#444'};
            margin-bottom: 16px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        ">
            <!-- Header -->
            <div style="background: rgba(255,255,255,0.03); padding: 14px 18px; border-bottom: 1px solid #2a2a2a; display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <i class="fas ${statusIcon[o.status] || 'fa-circle'}" style="color: ${statusColor[o.status] || '#888'}; font-size: 1.1rem;"></i>
                    <span style="color: #00d2ff; font-weight: 700; font-size: 1rem;">${o.item_name}</span>
                </div>
                <span style="
                    background: ${statusColor[o.status] || '#444'}22;
                    color: ${statusColor[o.status] || '#888'};
                    border: 1px solid ${statusColor[o.status] || '#444'}66;
                    padding: 4px 14px;
                    border-radius: 20px;
                    font-size: 0.8rem;
                    font-weight: 700;
                ">${o.status}</span>
            </div>
            <!-- Body -->
            <div style="padding: 16px 18px;">
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; text-align: center;">
                    <div style="background: #2a2a2a; border-radius: 10px; padding: 10px 8px;">
                        <div style="color: #888; font-size: 0.7rem; margin-bottom: 4px;"><i class="fas fa-user me-1"></i>الزبون</div>
                        <div style="color: #fff; font-size: 0.85rem; font-weight: 700;">@${o.username || 'N/A'}</div>
                    </div>
                    <div style="background: #2a2a2a; border-radius: 10px; padding: 10px 8px;">
                        <div style="color: #888; font-size: 0.7rem; margin-bottom: 4px;"><i class="fas fa-money-bill me-1"></i>المبلغ</div>
                        <div style="color: #28a745; font-size: 0.9rem; font-weight: 700;">${o.price} ل.س</div>
                    </div>
                    <div style="background: #2a2a2a; border-radius: 10px; padding: 10px 8px;">
                        <div style="color: #888; font-size: 0.7rem; margin-bottom: 4px;">${thirdCardLabel}</div>
                        <div style="color: #00d2ff; font-size: 0.85rem; font-weight: 700;">${thirdCardValue}</div>
                    </div>
                </div>
                <div style="color: #555; font-size: 0.75rem; text-align: right; margin-bottom: ${o.status === 'قيد الانتظار' ? '12px' : '0'};">
                    <i class="fas fa-clock me-1"></i>${o.timestamp_formatted || o.timestamp || ''}
                    &nbsp;&nbsp;<i class="fas fa-fingerprint me-1"></i>#${(o.id || '').substring(0, 8)}
                </div>
                ${o.status === 'قيد الانتظار' ? `
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button onclick="window.confirmApproveOrder('${o.id}', '${(o.username||'').replace(/'/g,'')}', '${o.price||0}', '${(o.item_name||'طلب شحن').replace(/'/g,'')}', '${transId}')" style="
                        background: linear-gradient(135deg, #28a745, #20c745);
                        color: white; border: none; border-radius: 10px;
                        padding: 8px 24px; font-weight: 700; cursor: pointer;
                        font-size: 0.9rem; box-shadow: 0 4px 15px rgba(40,167,69,0.3);
                        transition: all 0.2s;
                    " onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
                        <i class="fas fa-check me-2"></i>قبول
                    </button>
                    <button onclick="window.updateOrderStatus('${o.id}', 'مرفوض')" style="
                        background: linear-gradient(135deg, #dc3545, #ff4757);
                        color: white; border: none; border-radius: 10px;
                        padding: 8px 24px; font-weight: 700; cursor: pointer;
                        font-size: 0.9rem; box-shadow: 0 4px 15px rgba(220,53,69,0.3);
                        transition: all 0.2s;
                    " onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
                        <i class="fas fa-times me-2"></i>رفض
                    </button>
                </div>` : ''}
            </div>
        </div>
    `;
    };

    const sectionHeader = (icon, color, title, count) => `
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid ${color}44;">
            <div style="background: ${color}22; border: 1px solid ${color}44; border-radius: 10px; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">
                <i class="fas ${icon}" style="color: ${color};"></i>
            </div>
            <div>
                <div style="color: ${color}; font-weight: 700; font-size: 1rem;">${title}</div>
                <div style="color: #666; font-size: 0.75rem;">${count} طلب</div>
            </div>
        </div>
    `;

    const emptyMsg = '<div style="text-align:center; padding: 30px; color: #444; background: #1a1a1a; border-radius: 12px; border: 1px dashed #333;"><i class="fas fa-inbox fa-2x mb-2 d-block"></i>لا توجد طلبات</div>';

    container.innerHTML = `
        <div style="margin-bottom: 40px;">
            ${sectionHeader('fa-hourglass-half', '#ffc107', 'قيد الانتظار', pending.length)}
            ${pending.length > 0 ? pending.map(renderOrder).join('') : emptyMsg}
        </div>
        <div style="margin-bottom: 40px;">
            ${sectionHeader('fa-shopping-cart', '#28a745', 'طلبات الشراء المكتملة', purchaseCompleted.length)}
            ${purchaseCompleted.length > 0 ? purchaseCompleted.map(renderOrder).join('') : emptyMsg}
        </div>
        <div style="margin-bottom: 40px;">
            ${sectionHeader('fa-wallet', '#0d6efd', 'عمليات الشحن المكتملة', rechargeCompleted.length)}
            ${rechargeCompleted.length > 0 ? rechargeCompleted.map(renderOrder).join('') : emptyMsg}
        </div>
        <div>
            ${sectionHeader('fa-times-circle', '#dc3545', 'الطلبات المرفوضة', rejected.length)}
            ${rejected.length > 0 ? rejected.map(renderOrder).join('') : emptyMsg}
        </div>
    `;
};

window._goodsCache = [];

window.loadGoods = async function() {
    const container = document.getElementById('goods-container');
    if (!container) return;
    container.innerHTML = '<div class="col-12 text-center p-5"><i class="fas fa-spinner fa-spin fa-2x text-accent"></i><p class="text-muted mt-3">جاري تحميل السلع...</p></div>';
    const res = await window.apiCall('/api/goods');
    if (!res.success) { container.innerHTML = '<p class="text-danger text-center p-4">فشل تحميل السلع</p>'; return; }

    window._goodsCache = res.data;

    container.innerHTML = res.data.map(item => `
        <div class="col-md-4 mb-4 fade-in">
            <div class="card bg-dark border-secondary p-4 h-100 shadow-lg border-2 rounded-4">
                <div class="bg-secondary p-3 rounded-3 mb-3 text-center border border-accent">
                    <h4 class="text-accent fw-bold mb-0">${item.name}</h4>
                </div>
                <p class="text-white-50 small flex-grow-1 text-end" style="line-height: 1.6;">${item.description || 'لا يوجد وصف متاح لهذه السلعة'}</p>
                <div class="d-flex flex-column gap-3 mt-3 pt-3 border-top border-secondary">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="text-muted small fw-bold">السعر:</span>
                        <span class="badge bg-success fs-5 px-3 py-2 shadow-sm">${item.price} ل.س</span>
                    </div>
                    <div class="d-flex gap-2">
                        <button class="btn btn-warning flex-grow-1 fw-bold shadow-sm" data-item-id="${item.id}" onclick="window.editProductById(this.dataset.itemId)">
                            <i class="fas fa-edit me-2"></i> تعديل
                        </button>
                        <button class="btn btn-outline-danger shadow-sm" data-item-id="${item.id}" onclick="window.deleteProduct(this.dataset.itemId)">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `).join('') + `
        <div class="col-md-4 mb-4 fade-in">
            <div class="card bg-dark border-secondary p-3 h-100 d-flex align-items-center justify-content-center rounded-4 shadow-sm" style="cursor: pointer; border-style: dashed; min-height: 250px;" onclick="window.addProduct()">
                <i class="fas fa-plus-circle fa-3x text-accent mb-3"></i>
                <h5 class="text-white fw-bold">إضافة منتج جديد</h5>
            </div>
        </div>
    `;
};

window.editProductById = function(itemId) {
    const item = window._goodsCache.find(i => String(i.id) === String(itemId));
    if (!item) { window.showToast('المنتج غير موجود', 'danger'); return; }
    openProductModal(item);
};

window.editProduct = async function(id) {
    const cached = window._goodsCache.find(i => String(i.id) === String(id));
    if (cached) { openProductModal(cached); return; }
    const res = await window.apiCall('/api/goods');
    if (!res.success) return;
    const item = res.data.find(i => String(i.id) === String(id));
    if (!item) { window.showToast("المنتج غير موجود", "danger"); return; }
    openProductModal(item);
};

window.deleteProduct = async function(id) {
    if (confirm('هل أنت متأكد من حذف هذه السلعة؟')) {
        const res = await window.apiCall(`/api/goods?id=${id}`, 'DELETE');
        if (res.success) {
            window.loadGoods();
            window.showToast("تم الحذف بنجاح");
        } else {
            window.showToast("فشل الحذف", "danger");
        }
    }
};

window.addProduct = function() {
    openProductModal(null);
};

window.saveProductChanges = async function() {
    const idEl = document.getElementById('edit-product-id');
    const nameEl = document.getElementById('edit-product-name');
    const priceEl = document.getElementById('edit-product-price');
    const descEl = document.getElementById('edit-product-desc');

    if (!nameEl || !priceEl) return;

    const id = idEl.value;
    const name = nameEl.value;
    const price = priceEl.value;
    const description = descEl.value;

    if (!name || !price) {
        window.showToast("يرجى ملء الحقول المطلوبة", "danger");
        return;
    }

    const payload = id ? { id, name, price, description } : { name, price, description };
    const res = await window.apiCall('/api/goods', 'POST', payload);
    
    if (res.success) {
        const modalEl = document.getElementById('productModal');
        if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        window.loadGoods();
        window.showToast("تم الحفظ بنجاح");
    } else {
        window.showToast("فشل الحفظ", "danger");
    }
};

window.showSection = function(sectionId) {
    console.log("Switching to section:", sectionId);
    
    // Hide all sections
    const sections = document.getElementsByClassName('content-section');
    for (let s of sections) {
        s.style.display = 'none';
        s.classList.remove('fade-in');
    }
    
    // Show back button if not on status
    const backBtn = document.getElementById('global-back-btn');
    if (backBtn) {
        backBtn.style.setProperty('display', (sectionId === 'status') ? 'none' : 'block', 'important');
    }

    // Show the target section
    const target = document.getElementById(sectionId + '-section');
    if (target) {
        target.style.setProperty('display', 'block', 'important');
        target.classList.add('fade-in');
    }

    // Load data
    if (sectionId === 'status') window.loadStatus();
    else if (sectionId === 'users') window.loadUsers();
    else if (sectionId === 'orders') window.loadOrders();
    else if (sectionId === 'goods') window.loadGoods();
    else if (sectionId === 'settings') window.loadDepositNumbers();
};

window.loadDepositNumbers = async function() {
    const res = await window.apiCall('/api/settings/deposit-numbers');
    if (res.success) {
        const list = document.getElementById('deposit-numbers-list');
        if (!list) return;
        list.innerHTML = res.data.map(num => `
            <div class="list-group-item bg-secondary text-white d-flex justify-content-between align-items-center mb-2 rounded-3 border-0 fade-in shadow-sm p-3">
                <span class="fw-bold fs-5">${num}</span>
                <button class="btn btn-danger btn-sm shadow-sm" onclick="window.deleteDepositNumber('${num}')"><i class="fas fa-trash p-1"></i></button>
            </div>
        `).join('');
    }
};

window.addDepositNumber = async function() {
    const numEl = document.getElementById('new-deposit-number');
    if (!numEl) return;
    const num = numEl.value;
    if (num) {
        const res = await window.apiCall('/api/settings/deposit-numbers', 'POST', { number: num });
        if (res.success) { 
            numEl.value = ''; 
            window.loadDepositNumbers(); 
            window.showToast("تم الإضافة بنجاح");
        }
    }
};

window.deleteDepositNumber = async function(num) {
    const res_check = await window.apiCall('/api/settings/deposit-numbers');
    if (res_check.success && res_check.data.length <= 1) {
        window.showToast("يجب وجود رقم واحد على الأقل", "danger");
        return;
    }

    if (confirm('هل أنت متأكد من الحذف؟')) {
        const res = await window.apiCall('/api/settings/deposit-numbers', 'DELETE', { number: num });
        if (res.success) {
            window.loadDepositNumbers();
            window.showToast("تم الحذف");
        }
    }
};

window.updateOrderStatus = function(id, status, creditAmount) {
    const body = { status };
    if (creditAmount !== undefined && creditAmount !== null) {
        body.credit_amount = creditAmount;
    }
    window.apiCall(`/api/orders/${id}/status`, 'PUT', body).then(res => { 
        if (res.success) {
            window.loadOrders();
            if (creditAmount > 0) {
                window.showToast(`✅ تمت الموافقة وتم إضافة ${creditAmount} ل.س لرصيد الزبون`);
            } else {
                window.showToast(`تم التحديث بنجاح`);
            }
        } else {
            window.showToast(`فشل التحديث: ${res.message || 'خطأ غير معروف'}`, 'danger');
        }
    });
};

window._pendingApproveId = null;
window._pendingApproveUsername = null;

window.confirmApproveOrder = function(id, username, price, itemName, transId) {
    window._pendingApproveId = id;
    window._pendingApproveUsername = username;

    document.getElementById('approve-modal-username').textContent = '@' + (username || 'N/A');
    document.getElementById('approve-modal-price').textContent = (price || '0') + ' ل.س';
    document.getElementById('approve-modal-item').textContent = itemName || 'طلب شحن';
    const transRow = document.getElementById('approve-modal-trans-row');
    const transEl = document.getElementById('approve-modal-trans');
    const isRecharge = (itemName || '').includes('شحن رصيد');
    if (transRow) transRow.style.display = isRecharge ? 'flex' : 'none';
    if (transEl) transEl.textContent = transId || 'N/A';

    const amountInput = document.getElementById('approve-credit-amount');
    if (amountInput) {
        amountInput.value = price || '';
        amountInput.style.borderColor = '#28a74566';
    }

    const modal1 = bootstrap.Modal.getOrCreateInstance(document.getElementById('approveConfirmModal1'));
    modal1.show();
    setTimeout(() => { if (amountInput) amountInput.focus(); }, 400);
};

window._approveStep2 = function() {
    const amountInput = document.getElementById('approve-credit-amount');
    const creditAmount = parseFloat(amountInput ? amountInput.value : 0);

    if (!creditAmount || creditAmount <= 0) {
        if (amountInput) {
            amountInput.style.borderColor = '#dc3545';
            amountInput.focus();
        }
        window.showToast('يرجى إدخال مبلغ صحيح أكبر من صفر', 'danger');
        return;
    }

    window._pendingCreditAmount = creditAmount;

    document.getElementById('approve-modal-username2').textContent = '@' + (window._pendingApproveUsername || 'N/A');
    document.getElementById('approve-modal-price2').textContent = creditAmount.toLocaleString() + ' ل.س';

    const modal1 = bootstrap.Modal.getOrCreateInstance(document.getElementById('approveConfirmModal1'));
    modal1.hide();
    setTimeout(() => {
        const modal2 = bootstrap.Modal.getOrCreateInstance(document.getElementById('approveConfirmModal2'));
        modal2.show();
    }, 300);
};

window._approveCancel = function() {
    window._pendingApproveId = null;
    window._pendingCreditAmount = null;
    window._pendingApproveUsername = null;
};

window._approveConfirmed = function() {
    const modal2 = bootstrap.Modal.getOrCreateInstance(document.getElementById('approveConfirmModal2'));
    modal2.hide();
    if (window._pendingApproveId) {
        window.updateOrderStatus(window._pendingApproveId, 'مكتمل', window._pendingCreditAmount);
        window._pendingApproveId = null;
        window._pendingCreditAmount = null;
        window._pendingApproveUsername = null;
    }
};

window.editBalance = async function(uid) {
    const amount = prompt('أدخل المبلغ المطلوب إضافته أو تعديله:');
    if (amount !== null && !isNaN(amount)) {
        const res = await window.apiCall(`/api/users/${uid}/balance`, 'PUT', { balance: amount });
        if (res.success) {
            window.loadUsers();
            window.showToast("تم تحديث الرصيد بنجاح");
        }
    }
};

window.sendBackupToBot = async function() {
    window.showToast("جاري التجهيز والإرسال...", "info");
    const res = await window.apiCall('/api/backup/send-to-bot', 'POST');
    if (res.success) {
        window.showToast("تم الإرسال للبوت بنجاح");
    } else {
        window.showToast("فشل الإرسال", "danger");
    }
};

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    // Add debugging
    console.log("Dashboard JS Loaded");
    
    // Force auth check on load
    const mainApp = document.getElementById('main-app');
    const authScreen = document.getElementById('auth-screen');
    
    // Always show login on fresh load to ensure password is required
    localStorage.removeItem('admin_token');
    if (mainApp) mainApp.style.display = 'none';
    if (authScreen) authScreen.style.display = 'flex';
    
    // Quick fix for global functions
    window.authenticateUser = window.authenticateUser;
    window.showSection = window.showSection;
    window.addDepositNumber = window.addDepositNumber;
    window.saveProductChanges = window.saveProductChanges;
    
    // Active navigation highlighting
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
        });
    });
});