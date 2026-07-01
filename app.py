from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import OrderedDict
import smtplib
from email.mime.text import MIMEText
import sqlite3
import os
from werkzeug.utils import secure_filename
from mpesa import stk_push
from flask import jsonify
app = Flask(__name__)
app.secret_key = "ecommerce_secret_key"

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Make sure the upload folder actually exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Admin password — change this before deploying anywhere public.
# Better yet, set it as an environment variable: ADMIN_PASSWORD=yourpassword
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "paul")

# Two-level category taxonomy: parent category -> list of subcategories.
# Parents with an empty list show as a plain nav link (no dropdown).
# Existing products tagged with old flat values (e.g. "Men", "Shoes") still
# work fine - they just slot in as leaves under their parent automatically.
CATEGORY_TREE = OrderedDict([
    ("Electronics", ["Phones", "Laptops", "Audio", "Accessories"]),
    ("Clothing", ["Men", "Women", "Kids", "Activewear"]),
    ("Shoes", ["Sneakers", "Formal", "Sports", "Sandals & Slides", "Kids' Shoes"]),
    ("Home", []),
    ("Other", []),
])

CATEGORY_ICONS = {
    "Electronics": "⚡",
    "Clothing": "👕",
    "Shoes": "👟",
    "Home": "🏠",
    "Other": "🛍️",
}


def get_leaf_values_for(category_name):
    """Given a parent OR leaf category name, returns the list of actual
    'category' column values to filter by. Clicking a parent (e.g. 'Shoes')
    matches every subcategory underneath it, plus anything tagged with the
    parent name itself."""
    subs = CATEGORY_TREE.get(category_name)
    if subs:
        return [category_name] + subs
    return [category_name]


def get_category_tree_with_counts():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM products GROUP BY category"
        ).fetchall()
    finally:
        conn.close()

    counts = {row["category"]: row["count"] for row in rows}

    tree = []
    for parent, subs in CATEGORY_TREE.items():
        if subs:
            sub_list = [{"name": s, "count": counts.get(s, 0)} for s in subs]
            parent_count = counts.get(parent, 0) + sum(s["count"] for s in sub_list)
        else:
            sub_list = []
            parent_count = counts.get(parent, 0)

        tree.append({
            "name": parent,
            "icon": CATEGORY_ICONS.get(parent, "🛍️"),
            "count": parent_count,
            "subcategories": sub_list,
        })

    return tree


def get_db():
    conn = sqlite3.connect("store.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates the messages table (for the Contact form) if it doesn't exist yet."""
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


init_db()


# ===================== EMAIL =====================
# Set these as real environment variables before deploying.
# For Gmail: enable 2-Step Verification, then create an "App Password" at
# https://myaccount.google.com/apppasswords - use that, not your normal password.
MAIL_USERNAME = os.environ.get("support@dukastore.co.ke")
MAIL_PASSWORD = os.environ.get("cszz sxlf rtyk ytgo")
MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", 465))
ADMIN_NOTIFY_EMAIL = os.environ.get("admin@dukastore.co.ke", MAIL_USERNAME)


def send_email(to_address, subject, body):
    """Sends a plain-text email. If MAIL_USERNAME/MAIL_PASSWORD aren't set,
    it just prints to the console instead of crashing the app."""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print(f"[EMAIL NOT SENT - not configured] To: {to_address} | Subject: {subject}\n{body}\n")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = MAIL_USERNAME
    msg["To"] = to_address

    try:
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_USERNAME, [to_address], msg.as_string())
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


# ===================== ORDER TRACKING =====================
ORDER_STATUSES = ["Pending Payment", "Paid", "Processing", "Out for Delivery", "Delivered"]

STATUS_BADGE_CLASS = {
    "Pending Payment": "status-pending",
    "Paid": "status-paid",
    "Processing": "status-processing",
    "Out for Delivery": "status-delivery",
    "Delivered": "status-delivered",
    "Payment Failed": "status-failed",
}


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_image(file):
    """Validates and saves an uploaded image. Returns filename or None."""
    if not file or file.filename == "":
        return None

    if not allowed_file(file.filename):
        return None

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def admin_required(f):
    """Redirects to the admin login page unless the session is admin-authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def login_required(f):
    """Redirects to the login page unless a user (or admin) is signed in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") and not session.get("is_admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_globals():
    return {
        "nav_categories": get_category_tree_with_counts(),
        "cart_count": len(session.get("cart", [])),
    }


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    success = False

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message_text = request.form.get("message", "").strip()

        if name and email and message_text:
            conn = get_db()
            try:
                conn.execute(
                    "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)",
                    (name, email, message_text),
                )
                conn.commit()
            finally:
                conn.close()
            success = True

            send_email(
                email,
                "We received your message - Duka Store",
                f"Hi {name},\n\n"
                f"Thanks for reaching out to Duka Store. We've received your message and "
                f"will get back to you soon.\n\n"
                f"Your message:\n{message_text}\n\n"
                f"— Duka Store",
            )

            if ADMIN_NOTIFY_EMAIL:
                send_email(
                    ADMIN_NOTIFY_EMAIL,
                    "New Contact Form Message - Duka Store",
                    f"From: {name} <{email}>\n\nMessage:\n{message_text}",
                )

    return render_template("contact.html", success=success)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/admin/messages")
@admin_required
def admin_messages():
    conn = get_db()
    try:
        messages = conn.execute(
            "SELECT * FROM messages ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()
    return render_template("admin_messages.html", messages=messages)


# Home Page (public landing page — no products shown)
@app.route("/")
def home():
    return render_template("index.html")


# Shop / Product Catalog (must be logged in as a user or admin)
@app.route("/shop")
@login_required
def shop():
    category = request.args.get("category", "").strip()
    query = request.args.get("q", "").strip()
    sort = request.args.get("sort", "").strip()

    leaf_values = get_leaf_values_for(category) if category else []

    conn = get_db()
    try:
        if sort == "bestsellers":
            sql = """
                SELECT p.*, COUNT(oi.id) AS sales_count
                FROM products p
                LEFT JOIN order_items oi ON oi.product_id = p.id
                WHERE 1=1
            """
            params = []

            if leaf_values:
                placeholders = ",".join("?" for _ in leaf_values)
                sql += f" AND p.category IN ({placeholders})"
                params.extend(leaf_values)
            if query:
                sql += " AND p.name LIKE ?"
                params.append(f"%{query}%")

            sql += " GROUP BY p.id ORDER BY sales_count DESC"
        else:
            sql = "SELECT * FROM products WHERE 1=1"
            params = []

            if leaf_values:
                placeholders = ",".join("?" for _ in leaf_values)
                sql += f" AND category IN ({placeholders})"
                params.extend(leaf_values)
            if query:
                sql += " AND name LIKE ?"
                params.append(f"%{query}%")
            if sort == "newest":
                sql += " ORDER BY id DESC"

        products = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return render_template(
        "shop.html",
        products=products,
        selected_category=category,
        search_query=query,
        selected_sort=sort,
    )


# Admin Login
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")

        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin"))

        error = "Incorrect password. Try again."

    return render_template("admin_login.html", error=error)


# Admin Logout
@app.route("/admin-logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


# Admin Dashboard
@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    try:
        products = conn.execute("SELECT * FROM products").fetchall()
    finally:
        conn.close()
    return render_template("admin.html", products=products, category_tree=CATEGORY_TREE)


# Add Product
@app.route("/add-product", methods=["POST"])
@admin_required
def add_product():
    name = request.form.get("name", "").strip()
    price_raw = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "Other").strip() or "Other"

    if not name or not price_raw:
        return "Name and price are required", 400

    try:
        price = float(price_raw)
    except ValueError:
        return "Price must be a number", 400

    filename = save_image(request.files.get("image"))

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO products (name, price, description, image, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, price, description, filename, category),
        )
        conn.commit()
    finally:
        conn.close()

    return redirect("/admin")


# Edit Product Page
@app.route("/edit-product/<int:id>")
@admin_required
def edit_product(id):
    conn = get_db()
    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id=?", (id,)
        ).fetchone()
    finally:
        conn.close()

    if product is None:
        return "Product not found", 404

    return render_template("edit_product.html", product=product, category_tree=CATEGORY_TREE)


# Update Product
@app.route("/update-product/<int:id>", methods=["POST"])
@admin_required
def update_product(id):
    name = request.form.get("name", "").strip()
    price_raw = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "Other").strip() or "Other"

    if not name or not price_raw:
        return "Name and price are required", 400

    try:
        price = float(price_raw)
    except ValueError:
        return "Price must be a number", 400

    filename = save_image(request.files.get("image"))

    conn = get_db()
    try:
        if filename:
            conn.execute(
                """
                UPDATE products
                SET name=?, price=?, description=?, image=?, category=?
                WHERE id=?
                """,
                (name, price, description, filename, category, id),
            )
        else:
            conn.execute(
                """
                UPDATE products
                SET name=?, price=?, description=?, category=?
                WHERE id=?
                """,
                (name, price, description, category, id),
            )
        conn.commit()
    finally:
        conn.close()

    return redirect("/admin")


# Delete Product
@app.route("/delete-product/<int:id>", methods=["POST"])
@admin_required
def delete_product(id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM products WHERE id=?", (id,))
        conn.commit()
    finally:
        conn.close()

    return redirect("/admin")


@app.route("/product/<int:id>")
@login_required
def product_details(id):
    conn = get_db()
    try:
        product = conn.execute(
            "SELECT * FROM products WHERE id=?", (id,)
        ).fetchone()
    finally:
        conn.close()

    if not product:
        return "Product not found", 404

    return render_template("product.html", product=product)


@app.route("/add-to-cart/<int:id>")
def add_to_cart(id):
    cart = session.get("cart", [])
    cart.append(id)
    session["cart"] = cart
    return redirect("/cart")


@app.route("/cart")
def cart():
    cart_ids = session.get("cart", [])

    conn = get_db()
    products = []
    try:
        for product_id in cart_ids:
            product = conn.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if product:
                products.append(product)
    finally:
        conn.close()

    total = sum(product[2] for product in products)

    return render_template("cart.html", products=products, total=total)


@app.route("/remove-from-cart/<int:id>")
def remove_from_cart(id):
    cart = session.get("cart", [])

    if id in cart:
        cart.remove(id)

    session["cart"] = cart

    return redirect("/cart")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/register-user", methods=["POST"])
def register_user():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    hashed_password = generate_password_hash(password)

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
            """,
            (name, email, hashed_password)
        )
        conn.commit()
    finally:
        conn.close()

    return redirect("/login")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/login-user", methods=["POST"])
def login_user():
    email = request.form["email"]
    password = request.form["password"]

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email=?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if user and check_password_hash(user[3], password):
        session["user_id"] = user[0]
        session["user_name"] = user[1]
        return redirect("/")

    return "Invalid email or password"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/checkout")
def checkout():
    if "user_id" not in session:
        return redirect("/login")

    cart_ids = session.get("cart", [])

    if not cart_ids:
        return redirect("/cart")

    conn = get_db()
    try:
        products = []

        for product_id in cart_ids:
            product = conn.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if product:
                products.append(product)

        total = sum(product[2] for product in products)

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO orders (user_id, total, status)
            VALUES (?, ?, ?)
            """,
            (session["user_id"], total, "Pending Payment")
        )

        order_id = cursor.lastrowid

        for product in products:
            cursor.execute(
                """
                INSERT INTO order_items (order_id, product_id, price)
                VALUES (?, ?, ?)
                """,
                (order_id, product[0], product[2])
            )

        conn.commit()

        session["cart"] = []
    finally:
        conn.close()

    return redirect(f"/payment/{order_id}")


@app.route("/payment/<int:order_id>")
def payment(order_id):
    return render_template("payment.html", order_id=order_id)


@app.route("/pay/<int:order_id>", methods=["POST"])
def pay(order_id):
    phone = request.form["phone"].strip()

    # Convert 07XXXXXXXX to 2547XXXXXXXX
    if phone.startswith("07"):
        phone = "254" + phone[1:]

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
    finally:
        conn.close()

    if not order:
        return "Order not found"

    amount = int(order[2])

    result = stk_push(phone, amount)

    print("STK RESPONSE:", result)

    success = isinstance(result, dict) and result.get("ResponseCode") == "0"

    message = None
    if not success:
        message = (
            result.get("ResponseDescription") if isinstance(result, dict) else None
        ) or "Something went wrong while contacting M-Pesa. Please try again."
    else:
        checkout_request_id = result.get("CheckoutRequestID")
        if checkout_request_id:
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE orders SET checkout_request_id = ? WHERE id = ?",
                    (checkout_request_id, order_id),
                )
                conn.commit()
            finally:
                conn.close()

    return render_template(
        "payment_result.html",
        success=success,
        order_id=order_id,
        phone=phone,
        message=message,
    )


@app.route("/show-users")
def show_users():
    conn = get_db()
    try:
        users = conn.execute("SELECT * FROM users").fetchall()
    finally:
        conn.close()

    return str(users)


@app.route("/orders")
@admin_required
def orders():
    conn = get_db()
    try:
        orders = conn.execute(
            """
            SELECT
                orders.id,
                users.name,
                users.email,
                orders.total,
                orders.status,
                orders.created_at
            FROM orders
            JOIN users ON orders.user_id = users.id
            ORDER BY orders.id DESC
            """
        ).fetchall()
    finally:
        conn.close()

    return render_template("orders.html", orders=orders, order_statuses=ORDER_STATUSES, status_badge_class=STATUS_BADGE_CLASS)


@app.route("/admin/orders/<int:order_id>/update-status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    new_status = request.form.get("status", "").strip()

    if new_status not in ORDER_STATUSES:
        return "Invalid status", 400

    conn = get_db()
    try:
        order = conn.execute(
            """
            SELECT orders.id, orders.total, users.email, users.name
            FROM orders
            JOIN users ON orders.user_id = users.id
            WHERE orders.id = ?
            """,
            (order_id,),
        ).fetchone()

        if not order:
            return "Order not found", 404

        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()
    finally:
        conn.close()

    send_email(
        order["email"],
        f"Order #{order_id} Update - Duka Store",
        f"Hi {order['name']},\n\n"
        f"Your order #{order_id} status has been updated to: {new_status}.\n\n"
        f"Track it anytime at: {url_for('my_order_detail', order_id=order_id, _external=True)}\n\n"
        f"Thank you for shopping with Duka Store!",
    )

    return redirect(url_for("orders"))


# ===================== CUSTOMER ORDER TRACKING =====================

@app.route("/my-orders")
@login_required
def my_orders():
    if not session.get("user_id"):
        return redirect(url_for("home"))

    conn = get_db()
    try:
        my_orders_list = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC",
            (session["user_id"],),
        ).fetchall()
    finally:
        conn.close()

    return render_template(
        "my_orders.html",
        orders=my_orders_list,
        status_badge_class=STATUS_BADGE_CLASS,
    )


@app.route("/my-orders/<int:order_id>")
@login_required
def my_order_detail(order_id):
    if not session.get("user_id"):
        return redirect(url_for("home"))

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?",
            (order_id, session["user_id"]),
        ).fetchone()

        if not order:
            return "Order not found", 404

        items = conn.execute(
            """
            SELECT order_items.price, products.name, products.image
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = ?
            """,
            (order_id,),
        ).fetchall()
    finally:
        conn.close()

    return render_template(
        "my_order_detail.html",
        order=order,
        items=items,
        statuses=ORDER_STATUSES,
        current_index=ORDER_STATUSES.index(order["status"]) if order["status"] in ORDER_STATUSES else -1,
    )


@app.route("/my-orders/<int:order_id>/confirm-delivery", methods=["POST"])
@login_required
def confirm_delivery(order_id):
    if not session.get("user_id"):
        return redirect(url_for("home"))

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?",
            (order_id, session["user_id"]),
        ).fetchone()

        if not order:
            return "Order not found", 404

        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            ("Delivered", order_id),
        )
        conn.commit()
    finally:
        conn.close()

    if ADMIN_NOTIFY_EMAIL:
        send_email(
            ADMIN_NOTIFY_EMAIL,
            f"Order #{order_id} Marked Delivered by Customer",
            f"The customer for order #{order_id} has confirmed they received their items.",
        )

    return redirect(url_for("my_order_detail", order_id=order_id))


@app.route("/mpesa-callback", methods=["POST"])
def mpesa_callback():

    data = request.get_json()

    print("M-PESA CALLBACK RECEIVED")
    print(data)

    try:
        stk_callback = data["Body"]["stkCallback"]
        checkout_request_id = stk_callback.get("CheckoutRequestID")
        result_code = stk_callback.get("ResultCode")

        conn = get_db()
        try:
            order = conn.execute(
                """
                SELECT orders.id, orders.total, users.email, users.name
                FROM orders
                JOIN users ON orders.user_id = users.id
                WHERE orders.checkout_request_id = ?
                """,
                (checkout_request_id,),
            ).fetchone()

            if order:
                new_status = "Paid" if result_code == 0 else "Payment Failed"
                conn.execute(
                    "UPDATE orders SET status = ? WHERE id = ?",
                    (new_status, order["id"]),
                )
                conn.commit()

                if result_code == 0:
                    send_email(
                        order["email"],
                        "Payment Received - Duka Store",
                        f"Hi {order['name']},\n\n"
                        f"We've received your payment of KSh {order['total']} for order #{order['id']}. "
                        f"Your order is now being processed.\n\n"
                        f"You can track its progress anytime at: {url_for('my_order_detail', order_id=order['id'], _external=True)}\n\n"
                        f"Thank you for shopping with Duka Store!",
                    )
                else:
                    send_email(
                        order["email"],
                        "Payment Issue - Duka Store",
                        f"Hi {order['name']},\n\n"
                        f"We weren't able to confirm payment for order #{order['id']}. "
                        f"Please try checking out again, or contact us if you believe this is a mistake.\n\n"
                        f"Thank you for shopping with Duka Store!",
                    )
            else:
                print(f"No order found for CheckoutRequestID: {checkout_request_id}")
        finally:
            conn.close()
    except Exception as e:
        print("Error processing M-Pesa callback:", e)

    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Success"
    })


if __name__ == "__main__":
    import os

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
