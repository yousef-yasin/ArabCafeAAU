const cart = {};
const cartItemsEl = document.getElementById('cart-items');
const cartTotalEl = document.getElementById('cart-total');
const cartPayloadEl = document.getElementById('cart_payload');
const cartCountEl = document.getElementById('cart-count');

function renderCart() {
  const entries = Object.values(cart);
  if (!entries.length) {
    cartItemsEl.innerHTML = '<div class="text-muted">لسا ما أضفت أي منتج.</div>';
    cartTotalEl.textContent = '0.00 د.أ';
    cartCountEl.textContent = '0';
    cartPayloadEl.value = '[]';
    return;
  }

  let total = 0;
  let count = 0;
  cartItemsEl.innerHTML = entries.map(item => {
    const subtotal = item.price * item.qty;
    total += subtotal;
    count += item.qty;
    return `
      <div class="cart-row">
        <div class="d-flex justify-content-between align-items-start gap-2">
          <div>
            <strong>${item.name}</strong>
            <div class="small text-muted mt-1">${item.price.toFixed(2)} د.أ</div>
          </div>
          <strong>${subtotal.toFixed(2)} د.أ</strong>
        </div>
        <div class="d-flex align-items-center gap-2 mt-2">
          <button type="button" class="qty-btn" onclick="changeQty(${item.id}, -1)">-</button>
          <span class="fw-bold">${item.qty}</span>
          <button type="button" class="qty-btn" onclick="changeQty(${item.id}, 1)">+</button>
        </div>
      </div>`;
  }).join('');

  cartCountEl.textContent = String(count);
  cartTotalEl.textContent = `${total.toFixed(2)} د.أ`;
  cartPayloadEl.value = JSON.stringify(entries.map(i => ({ id: i.id, qty: i.qty })));
}

function changeQty(id, delta) {
  if (!cart[id]) return;
  cart[id].qty += delta;
  if (cart[id].qty <= 0) delete cart[id];
  renderCart();
}

document.querySelectorAll('.add-to-cart').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = Number(btn.dataset.id);
    const name = btn.dataset.name;
    const price = Number(btn.dataset.price);
    if (!cart[id]) cart[id] = { id, name, price, qty: 0 };
    cart[id].qty += 1;
    renderCart();
  });
});

renderCart();
