from datetime import datetime
from functools import wraps
from collections import defaultdict
from io import BytesIO
import json
import mimetypes
import os

from flask import Flask, render_template, render_template_string, request, redirect, url_for, flash, session, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'cafeteria.db')
SEED_DIR = os.path.join(BASE_DIR, 'seed')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

db = SQLAlchemy(app)


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class SiteAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_key = db.Column(db.String(100), unique=True, nullable=False)
    filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    data = db.Column(db.LargeBinary, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    show_image = db.Column(db.Boolean, default=True)
    items = db.relationship('MenuItem', backref='category', lazy=True, cascade='all, delete-orphan')


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    price = db.Column(db.Float, nullable=False)
    available = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_mime_type = db.Column(db.String(100), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    building = db.Column(db.String(10), nullable=False, default='I')
    notes = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(30), default='pending')
    total = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    ready_at = db.Column(db.DateTime, nullable=True)
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan', lazy=True)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    item_name = db.Column(db.String(140), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)


def admin_required(func_):
    @wraps(func_)
    def wrapper(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login'))
        return func_(*args, **kwargs)
    return wrapper


def read_seed_file(filename):
    path = os.path.join(SEED_DIR, filename)
    if not os.path.exists(path):
        return None, None, None
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as f:
        return f.read(), mime, os.path.basename(path)


CATEGORY_IMAGE_FILES = {
    'مشروبات ساخنة': 'hot-coffee.png',
    'قهوة باردة': 'iced-coffee.png',
    'موهيتو': 'mojito.png',
    'آيس تي': 'iced-tea.png',
    'بودر ومشروبات آلة': 'powder.png',
    'ميلك شيك': 'milkshake.png',
    'السناك': 'snacks.png',
    'بيتزا من الفرن': 'pizza.png',
    'برغر': 'burger.png',
    'بوكسات عربية': 'box.png',
    'سلطات': 'salad.png',
    'ساندويش خفيف للإفطار': 'breakfast.png',
    'إضافات': None,
}


MENU_DATA = [
    {
        'name': 'مشروبات ساخنة', 'slug': 'hot-coffee', 'sort_order': 1, 'show_image': True,
        'items': [
            ('Double Espresso', 1.25), ('Americano', 1.25), ('Filter Coffee', 1.25),
            ('Latte', 2.00), ('Cappuccino', 2.00), ('Flat White', 2.25),
            ('Dark Mocha', 2.50), ('White Mocha', 2.50), ('Arab Hot Chocolate', 2.00),
            ('Spanish Latte Hot', 2.50), ('Caramel Macchiato Hot', 2.50), ('Extra', 0.25),
        ]
    },
    {
        'name': 'قهوة باردة', 'slug': 'iced-coffee', 'sort_order': 2, 'show_image': True,
        'items': [
            ('Ice Latte', 2.00), ('Ice Americano', 1.50), ('Ice White Mocha', 2.50), ('Ice Dark Mocha', 2.50),
            ('Ice Caramel Macchiato', 2.50), ('Ice Spanish Latte', 2.50), ('Frappe', 2.50), ('Extra', 0.25),
        ]
    },
    {
        'name': 'موهيتو', 'slug': 'mojito', 'sort_order': 3, 'show_image': True,
        'items': [('Strawberry & Mix Berries', 2.00), ('Peach & Mango', 2.00), ('Blueberry & Passion', 2.00)]
    },
    {
        'name': 'آيس تي', 'slug': 'iced-tea', 'sort_order': 4, 'show_image': True,
        'items': [('Peach Ice Tea', 2.00), ('Mango & Peach Ice Tea', 2.00), ('Strawberry Ice Tea', 2.00), ('Mix Berry & Strawberry Ice Tea', 2.00)]
    },
    {
        'name': 'بودر ومشروبات آلة', 'slug': 'powder', 'sort_order': 5, 'show_image': True,
        'items': [('Turkish Coffee', 0.75), ('Nescafe Machine', 0.75), ('Hot Chocolate Machine', 0.75), ('Chai Karak', 0.75), ('Sahlab', 0.75), ('Caramel Cappuccino', 0.75)]
    },
    {
        'name': 'ميلك شيك', 'slug': 'milkshake', 'sort_order': 6, 'show_image': True,
        'items': [('Vanilla Milk Shake', 2.00), ('Strawberry Milk Shake', 2.00), ('Chocolate Milk Shake', 2.00)]
    },
    {
        'name': 'السناك', 'slug': 'snacks', 'sort_order': 7, 'show_image': True,
        'items': [('شاورما عربي', 1.50), ('شاورما عربي دبل', 2.50), ('برغر فرنسي أو تورتيلا', 2.00), ('برغر سوبرم', 2.35), ('برغر بالكريمة', 2.50), ('فاهيتا دجاج', 2.00), ('فاهيتا لحمة', 3.00), ('مكسيكان', 2.00), ('تشيكن باربكيو', 2.35), ('تشيكن ألفريدو', 2.25), ('نونا', 2.25), ('ديناميت', 2.35), ('كوردن بلو', 2.50), ('تشيكن هافاو', 2.25)]
    },
    {
        'name': 'بيتزا من الفرن', 'slug': 'pizza', 'sort_order': 8, 'show_image': True,
        'items': [('بيتزا الفريدو', 2.75), ('بيتزا التوست', 2.75), ('بيتزا بولو', 2.75), ('بيتزا باربكيو', 2.75), ('بيتزا خضار', 2.50), ('بيتزا سلامي', 2.50), ('بيتزا مارجريتا', 2.00), ('بيتزا الفريدو كبير', 4.00), ('بيتزا التوست كبير', 4.00), ('بيتزا بولو كبير', 4.00), ('بيتزا باربكيو كبير', 4.00), ('بيتزا خضار كبير', 3.50), ('بيتزا سلامي كبير', 3.50), ('بيتزا مارجريتا كبير', 3.00)]
    },
    {
        'name': 'برغر', 'slug': 'burger', 'sort_order': 9, 'show_image': True,
        'items': [('سكالوب', 1.50), ('كلاب هاوس برغر', 1.50), ('كرسبي عرب تشكن', 2.50), ('عرب برغر 150 غ', 2.50), ('سماش وايت 150 غ', 2.50), ('ماشروم 150 غ', 2.50), ('عرب كلاسيك 150 غ', 2.50), ('برغر رانشي 150 غ', 2.50), ('سماش برغر 100 غ', 2.00), ('سكالوب كبير', 2.50), ('كلاب هاوس برغر كبير', 2.50), ('كرسبي عرب تشكن كبير', 3.50), ('عرب برغر كبير', 3.50), ('سماش وايت كبير', 3.50), ('ماشروم كبير', 3.50), ('عرب كلاسيك كبير', 3.50), ('برغر رانشي كبير', 3.50), ('سماش برغر كبير', 3.00)]
    },
    {
        'name': 'بوكسات عربية', 'slug': 'boxes', 'sort_order': 10, 'show_image': True,
        'items': [('بوكس البطاطا', 1.00), ('بوكس الودجز', 1.25), ('بوكس البطاطا مع الجبنة', 1.50), ('بوكس الودجز مع الجبنة', 1.75), ('بوكس البرجر', 2.50), ('بوكس البرجر مع الكريمة', 3.00), ('بوكس الصوت دوغ', 2.25)]
    },
    {
        'name': 'سلطات', 'slug': 'salads', 'sort_order': 11, 'show_image': True,
        'items': [('سلطة سيزر', 1.50), ('سلطة يونانية', 2.00), ('سلطة روكا', 1.25), ('سلطة تونا', 2.50), ('إضافة صدر دجاج', 1.00)]
    },
    {
        'name': 'ساندويش خفيف للإفطار', 'slug': 'breakfast', 'sort_order': 12, 'show_image': True,
        'items': [('سنورة مع لبنة', 0.75), ('بيض', 0.75), ('بطاطا ساندويش', 1.00), ('هالابينو', 1.00), ('مكس أجبان', 1.00), ('كبدة', 1.00), ('جبنة فيتا', 1.25), ('حلوم مشوي', 1.50), ('تركي مع مكس أجبان', 1.50), ('هوت دوغ', 1.50)]
    },
    {
        'name': 'إضافات', 'slug': 'extras', 'sort_order': 13, 'show_image': False,
        'items': [('علبة جبنة', 0.25), ('علبة كوكتيل', 0.25), ('علبة زيتون', 0.25), ('علبة جبنة إضافية', 0.25)]
    },
]


def apply_schema_fixes():
    inspector = inspect(db.engine)
    if 'site_asset' not in inspector.get_table_names():
        SiteAsset.__table__.create(db.engine)

    menu_cols = {c['name'] for c in inspector.get_columns('menu_item')}
    alter_statements = []
    if 'image_data' not in menu_cols:
        alter_statements.append('ALTER TABLE menu_item ADD COLUMN image_data BLOB')
    if 'image_mime_type' not in menu_cols:
        alter_statements.append('ALTER TABLE menu_item ADD COLUMN image_mime_type VARCHAR(100)')
    if 'image_filename' not in menu_cols:
        alter_statements.append('ALTER TABLE menu_item ADD COLUMN image_filename VARCHAR(255)')
    for stmt in alter_statements:
        db.session.execute(text(stmt))

    order_cols = {c['name'] for c in inspector.get_columns('order')}
    if 'building' not in order_cols:
        db.session.execute(text("ALTER TABLE 'order' ADD COLUMN building VARCHAR(10) DEFAULT 'I' NOT NULL"))

    if alter_statements or 'building' not in order_cols:
        db.session.commit()


def seed_site_asset(key, seed_filename):
    asset = SiteAsset.query.filter_by(asset_key=key).first()
    if asset and asset.data:
        return
    data, mime, filename = read_seed_file(seed_filename)
    if not data:
        return
    if not asset:
        asset = SiteAsset(asset_key=key)
        db.session.add(asset)
    asset.data = data
    asset.mime_type = mime
    asset.filename = filename


def seed_data():
    if not Admin.query.first():
        admin_username = os.getenv('ADMIN_USERNAME')
        admin_password = os.getenv('ADMIN_PASSWORD')

        if admin_username and admin_password:
            db.session.add(
                Admin(
                    username=admin_username,
                    password_hash=generate_password_hash(admin_password)
                )
            )
    seed_site_asset('logo', 'logo.png')
    seed_site_asset('menu_board', 'menu-board.png')

    if Category.query.count() == 0:
        for cat_data in MENU_DATA:
            category = Category(
                name=cat_data['name'],
                slug=cat_data['slug'],
                sort_order=cat_data['sort_order'],
                show_image=cat_data['show_image']
            )
            db.session.add(category)
            db.session.flush()
            img_bytes, img_mime, img_filename = (None, None, None)
            image_file = CATEGORY_IMAGE_FILES.get(cat_data['name'])
            if image_file:
                img_bytes, img_mime, img_filename = read_seed_file(image_file)

            for idx, item in enumerate(cat_data['items']):
                name, price = item[0], item[1]
                description = item[2] if len(item) > 2 else f"منيو {cat_data['name']} - Arab Cafe"
                db.session.add(MenuItem(
                    name=name,
                    description=description,
                    price=price,
                    featured=idx < 3,
                    category_id=category.id,
                    available=True,
                    image_data=img_bytes if cat_data['show_image'] else None,
                    image_mime_type=img_mime if cat_data['show_image'] else None,
                    image_filename=img_filename if cat_data['show_image'] else None,
                ))
    else:
        # Backfill old databases so images become stored in DB.
        for item in MenuItem.query.filter((MenuItem.image_data.is_(None)) & (MenuItem.category_id.is_not(None))).all():
            image_file = CATEGORY_IMAGE_FILES.get(item.category.name)
            if image_file and item.category.show_image:
                img_bytes, img_mime, img_filename = read_seed_file(image_file)
                item.image_data = img_bytes
                item.image_mime_type = img_mime
                item.image_filename = img_filename

    db.session.commit()

@app.route("/admin/orders_partial")
@admin_required
def admin_orders_partial():
    status_filter = request.args.get("status", "all")

    query = Order.query.order_by(Order.created_at.desc())

    if status_filter != "all":
        query = query.filter_by(status=status_filter)

    orders = query.all()

    return render_template("partials/orders_list.html", orders=orders)


def get_upload_blob(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None, None
    filename = secure_filename(file_storage.filename)
    mime_type = file_storage.mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    data = file_storage.read()
    if not data:
        return None, None, None
    return data, mime_type, filename


@app.context_processor
def inject_globals():
    return {
        'site_name': 'Arab Cafe',
        'student_order_url': url_for('index'),
    }


@app.route('/media/logo')
def media_logo():
    asset = SiteAsset.query.filter_by(asset_key='logo').first()
    if not asset or not asset.data:
        abort(404)
    return send_file(BytesIO(asset.data), mimetype=asset.mime_type or 'image/png', download_name=asset.filename or 'logo.png')


@app.route('/media/asset/<asset_key>')
def site_asset_media(asset_key):
    asset = SiteAsset.query.filter_by(asset_key=asset_key).first_or_404()
    if not asset.data:
        abort(404)
    return send_file(BytesIO(asset.data), mimetype=asset.mime_type or 'application/octet-stream', download_name=asset.filename or asset_key)


@app.route('/media/item/<int:item_id>')
def menu_item_image(item_id):
    item = MenuItem.query.get_or_404(item_id)
    if not item.image_data:
        abort(404)
    return send_file(BytesIO(item.image_data), mimetype=item.image_mime_type or 'image/png', download_name=item.image_filename or f'item-{item.id}.png')


@app.route('/')
def index():
    categories = Category.query.order_by(Category.sort_order, Category.id).all()
    featured_items = MenuItem.query.filter_by(available=True, featured=True).limit(8).all()
    return render_template('student_home.html', categories=categories, featured_items=featured_items)


@app.route('/place-order', methods=['POST'])
def place_order():
    student_name = request.form.get('student_name', '').strip()
    phone = request.form.get('phone', '').strip()
    building = request.form.get('building', '').strip().upper()
    notes = request.form.get('notes', '').strip()
    raw_items = request.form.get('cart_payload', '').strip()

    if not student_name or not phone or not raw_items or building not in {'I', 'B'}:
        flash('لازم تدخل الاسم ورقم التلفون وتختار المبنى وتختار طلب واحد على الأقل.', 'danger')
        return redirect(url_for('index'))

    try:
        cart_items = json.loads(raw_items)
    except Exception:
        flash('صار خطأ ببيانات السلة.', 'danger')
        return redirect(url_for('index'))

    if not cart_items:
        flash('السلة فاضية.', 'danger')
        return redirect(url_for('index'))

    order_items = []
    total = 0
    for cart_item in cart_items:
        menu_item = MenuItem.query.get(int(cart_item['id']))
        qty = int(cart_item['qty'])
        if not menu_item or qty < 1 or not menu_item.available:
            continue
        subtotal = menu_item.price * qty
        total += subtotal
        order_items.append({
            'menu_item_id': menu_item.id,
            'item_name': menu_item.name,
            'quantity': qty,
            'unit_price': menu_item.price,
        })

    if not order_items:
        flash('المنتجات المختارة غير صالحة أو غير متاحة حالياً.', 'danger')
        return redirect(url_for('index'))

    order = Order(student_name=student_name, phone=phone, building=building, notes=notes, total=round(total, 2))
    db.session.add(order)
    db.session.flush()

    for item in order_items:
        db.session.add(OrderItem(order_id=order.id, **item))

    db.session.commit()
    return render_template('order_success.html', order=order)


@app.route('/admin/loginarabcafeaau', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            flash('تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('بيانات الدخول غير صحيحة.', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('تم تسجيل الخروج.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/afdminarabcafeaau123')
@admin_required
def admin_dashboard():
    status = request.args.get('status')
    query = Order.query.order_by(Order.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    orders = query.all()
    stats = {
        'pending': Order.query.filter_by(status='pending').count(),
        'confirmed': Order.query.filter_by(status='confirmed').count(),
        'ready': Order.query.filter_by(status='ready').count(),
        'cancelled': Order.query.filter_by(status='cancelled').count(),
        'total_orders': Order.query.count(),
        'sales_today': round(
            db.session.query(func.coalesce(func.sum(Order.total), 0.0))
            .filter(func.date(Order.created_at) == datetime.utcnow().date().isoformat())
            .scalar() or 0.0, 2
        )
    }
    return render_template('admin_dashboard.html', orders=orders, stats=stats, active_status=status)


@app.route('/admin/reports')
@admin_required
def reports():
    daily_orders = Order.query.order_by(Order.created_at.desc()).all()
    grouped = defaultdict(list)
    for order in daily_orders:
        day = order.created_at.strftime('%Y-%m-%d')
        grouped[day].append(order)

    reports_data = []
    for day, orders in grouped.items():
        reports_data.append({
            'date': day,
            'orders': orders,
            'total_amount': round(sum(order.total for order in orders), 2),
            'total_count': len(orders)
        })

    reports_data.sort(key=lambda x: x['date'], reverse=True)
    grand_total = round(sum(group['total_amount'] for group in reports_data), 2)
    return render_template('reports.html', reports_data=reports_data, grand_total=grand_total)


@app.route('/admin/order/<int:order_id>/confirm', methods=['POST'])
@admin_required
def confirm_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'confirmed'
    order.confirmed_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('print_receipt', order_id=order.id))


@app.route('/admin/order/<int:order_id>/ready', methods=['POST'])
@admin_required
def ready_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'ready'
    order.ready_at = datetime.utcnow()
    db.session.commit()
    flash(f'تم تجهيز الطلب رقم #{order.id}', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/order/<int:order_id>/cancel', methods=['POST'])
@admin_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'cancelled'
    db.session.commit()
    flash(f'تم إلغاء الطلب رقم #{order.id}', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/orders/delete-all', methods=['POST'])
@admin_required
def delete_all_orders():
    deleted_items = OrderItem.query.delete()
    deleted_orders = Order.query.delete()
    db.session.commit()
    flash(f'تم حذف جميع الطلبات ({deleted_orders}) وكل العناصر التابعة إلها ({deleted_items}).', 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/menu', methods=['GET', 'POST'])
@admin_required
def manage_menu():
    categories = Category.query.order_by(Category.sort_order, Category.id).all()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add-category':
            name = request.form.get('category_name', '').strip()
            slug = request.form.get('category_slug', '').strip().lower().replace(' ', '-')
            show_image = request.form.get('show_image') == '1'
            if not name or not slug:
                flash('لازم تدخل اسم القسم وكود القسم.', 'danger')
                return redirect(url_for('manage_menu'))
            if Category.query.filter((Category.name == name) | (Category.slug == slug)).first():
                flash('القسم موجود مسبقاً.', 'warning')
                return redirect(url_for('manage_menu'))
            db.session.add(Category(name=name, slug=slug, sort_order=Category.query.count() + 1, show_image=show_image))
            db.session.commit()
            flash('تمت إضافة القسم بنجاح.', 'success')
            return redirect(url_for('manage_menu'))

        if action == 'add-item':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price_raw = request.form.get('price', '0').strip()
            category_id = request.form.get('category_id')
            featured = request.form.get('featured') == '1'
            image_data, image_mime, image_filename = get_upload_blob(request.files.get('image_file'))
            if not name or not category_id:
                flash('الرجاء تعبئة اسم الصنف والقسم.', 'danger')
                return redirect(url_for('manage_menu'))
            try:
                price = float(price_raw)
            except ValueError:
                flash('السعر غير صحيح.', 'danger')
                return redirect(url_for('manage_menu'))
            db.session.add(MenuItem(
                name=name,
                description=description,
                price=price,
                category_id=int(category_id),
                featured=featured,
                available=True,
                image_data=image_data,
                image_mime_type=image_mime,
                image_filename=image_filename,
            ))
            db.session.commit()
            flash('تمت إضافة الصنف ونزل مباشرة عند الطلاب.', 'success')
            return redirect(url_for('manage_menu'))

    items = MenuItem.query.join(Category).order_by(Category.sort_order, MenuItem.id).all()
    return render_template('manage_menu.html', categories=categories, items=items)


@app.route('/admin/menu/<int:item_id>/edit', methods=['POST'])
@admin_required
def edit_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    price_raw = request.form.get('price', '').strip()
    category_id = request.form.get('category_id')
    featured = request.form.get('featured') == '1'
    available = request.form.get('available') == '1'
    remove_image = request.form.get('remove_image') == '1'

    if not name or not category_id or not price_raw:
        flash('لازم تعبّي الاسم والسعر والقسم.', 'danger')
        return redirect(url_for('manage_menu'))

    try:
        price = float(price_raw)
    except ValueError:
        flash('السعر غير صحيح.', 'danger')
        return redirect(url_for('manage_menu'))

    item.name = name
    item.description = description
    item.price = price
    item.category_id = int(category_id)
    item.featured = featured
    item.available = available

    image_data, image_mime, image_filename = get_upload_blob(request.files.get('image_file'))
    if image_data:
        item.image_data = image_data
        item.image_mime_type = image_mime
        item.image_filename = image_filename
    elif remove_image:
        item.image_data = None
        item.image_mime_type = None
        item.image_filename = None

    db.session.commit()
    flash(f'تم تعديل الصنف: {item.name}', 'success')
    return redirect(url_for('manage_menu'))


@app.route('/admin/menu/<int:item_id>/toggle', methods=['POST'])
@admin_required
def toggle_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    item.available = not item.available
    db.session.commit()
    flash(f'تم تحديث حالة المنتج: {item.name}', 'success')
    return redirect(url_for('manage_menu'))


@app.route('/admin/menu/<int:item_id>/delete', methods=['POST'])
@admin_required
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('تم حذف الصنف من المنيو.', 'warning')
    return redirect(url_for('manage_menu'))


@app.route('/receipt/<int:order_id>')
@admin_required
def print_receipt(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('receipt.html', order=order)


with app.app_context():
    db.create_all()
    apply_schema_fixes()
    seed_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))