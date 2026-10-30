/**
 * ShopFlow E-Commerce Web Application - Frontend Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
  // Initialize Bootstrap Tooltips & Popovers
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

  // Auto-dismiss alerts after 5 seconds
  const autoDismissAlerts = document.querySelectorAll('.alert-dismissible');
  autoDismissAlerts.forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      if (bsAlert) bsAlert.close();
    }, 5000);
  });

  // Setup AJAX Add to Cart
  setupAddToCartForms();

  // Setup Cart Quantity Buttons on Cart Page
  setupCartControls();

  // Setup Product Detail controls and resilient image fallbacks
  setupProductDetailControls();
});

/**
 * Display a modern Toast notification
 */
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const bgClass = type === 'success' ? 'bg-success text-white' :
                  type === 'danger' ? 'bg-danger text-white' :
                  type === 'warning' ? 'bg-warning text-dark' : 'bg-primary text-white';

  const iconClass = type === 'success' ? 'bi-check-circle-fill' :
                    type === 'danger' ? 'bi-x-circle-fill' :
                    type === 'warning' ? 'bi-exclamation-triangle-fill' : 'bi-info-circle-fill';

  const toastHtml = `
    <div class="toast align-items-center ${bgClass} border-0 shadow" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="d-flex">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="bi ${iconClass} fs-5"></i>
          <div>${message}</div>
        </div>
        <button type="button" class="btn-close ${type === 'warning' ? '' : 'btn-close-white'} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', toastHtml);
  const toastElement = container.lastElementChild;
  const toast = new bootstrap.Toast(toastElement, { delay: 4000 });
  toast.show();

  toastElement.addEventListener('hidden.bs.toast', () => {
    toastElement.remove();
  });
}

/**
 * Handle product quantity controls and image fallback placeholders
 */
function setupProductDetailControls() {
  const quantityInput = document.getElementById('quantityInput');

  document.querySelectorAll('[data-quantity-action]').forEach(button => {
    button.addEventListener('click', () => {
      if (!quantityInput) return;

      const currentValue = Number.parseInt(quantityInput.value, 10) || 1;
      const minimum = Number.parseInt(quantityInput.min, 10) || 1;
      const maximum = Number.parseInt(quantityInput.max, 10) || 999;
      const step = button.dataset.quantityAction === 'increase' ? 1 : -1;
      quantityInput.value = Math.min(maximum, Math.max(minimum, currentValue + step));
    });
  });

  document.querySelectorAll('[data-fallback-src]').forEach(image => {
    image.addEventListener('error', () => {
      const fallbackSrc = image.dataset.fallbackSrc;
      if (fallbackSrc && image.src !== fallbackSrc) {
        image.src = fallbackSrc;
      }
    }, { once: true });
  });
}

/**
 * Handle AJAX Add to Cart
 */
function setupAddToCartForms() {
  const forms = document.querySelectorAll('.form-add-to-cart');
  forms.forEach(form => {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const submitBtn = form.querySelector('button[type="submit"]');
      const originalHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Adding...';
      }

      const formData = new FormData(form);
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
          },
          body: formData
        });

        // If redirected to login (unauthenticated)
        if (response.redirected && response.url.includes('/auth/login')) {
          window.location.href = response.url;
          return;
        }

        const data = await response.json();

        if (response.ok && data.success) {
          showToast(data.message, 'success');
          // Update navbar badge
          updateNavbarCartBadge(data.cart_count);
        } else {
          showToast(data.message || 'Could not add item to cart.', 'warning');
        }
      } catch (err) {
        console.error('Add to cart error:', err);
        // Fallback to normal form submit if fetch fails
        form.submit();
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalHtml;
        }
      }
    });
  });
}

/**
 * Update the navbar cart counter badge
 */
function updateNavbarCartBadge(count) {
  const badges = document.querySelectorAll('.cart-badge');
  badges.forEach(badge => {
    badge.innerText = count;
    if (count > 0) {
      badge.classList.remove('d-none');
    } else {
      badge.classList.add('d-none');
    }
  });
}

/**
 * Cart Page Quantity and Removal Controls
 */
function setupCartControls() {
  const cartContainer = document.getElementById('cart-page-container');
  if (!cartContainer) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  // Handle quantity adjustment buttons
  cartContainer.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-cart-qty');
    if (!btn) return;

    const itemId = btn.dataset.itemId;
    const action = btn.dataset.action; // 'increase' or 'decrease'
    const row = document.getElementById(`cart-row-${itemId}`);

    btn.disabled = true;

    try {
      const response = await fetch(`/cart/update/${itemId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ action: action })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        if (data.item_removed) {
          row.remove();
          showToast(data.message, 'info');
          // If no rows left, reload to show empty cart banner
          if (document.querySelectorAll('.cart-item-row').length === 0) {
            window.location.reload();
            return;
          }
        } else {
          // Update row quantity and line subtotal
          const qtyInput = row.querySelector('.qty-input');
          const subtotalEl = row.querySelector('.item-subtotal');
          if (qtyInput) qtyInput.value = data.quantity;
          if (subtotalEl) subtotalEl.innerText = `$${data.item_subtotal.toFixed(2)}`;
        }

        // Update overall cart totals
        updateCartSummary(data);
        updateNavbarCartBadge(data.cart_count);
      } else {
        showToast(data.message || 'Failed to update quantity.', 'warning');
      }
    } catch (err) {
      console.error('Update quantity error:', err);
    } finally {
      btn.disabled = false;
    }
  });
}

function updateCartSummary(data) {
  const subtotalEl = document.getElementById('cart-subtotal');
  const shippingEl = document.getElementById('cart-shipping');
  const grandTotalEl = document.getElementById('cart-grand-total');

  if (subtotalEl) subtotalEl.innerText = `$${data.subtotal.toFixed(2)}`;
  if (shippingEl) {
    shippingEl.innerText = data.shipping_fee > 0 ? `$${data.shipping_fee.toFixed(2)}` : 'FREE';
  }
  if (grandTotalEl) grandTotalEl.innerText = `$${data.grand_total.toFixed(2)}`;
}

/**
 * 1-Click Fill Demo Credentials for Login page
 */
function fillDemoCredentials(role) {
  const inputIdentifier = document.getElementById('username_or_email');
  const inputPassword = document.getElementById('password');

  if (!inputIdentifier || !inputPassword) return;

  if (role === 'admin') {
    inputIdentifier.value = 'admin@shop.com';
    inputPassword.value = 'admin123';
  } else {
    inputIdentifier.value = 'user@shop.com';
    inputPassword.value = 'user123';
  }

  showToast(`Filled ${role.toUpperCase()} credentials. Click 'Sign In' to proceed!`, 'info');
}
