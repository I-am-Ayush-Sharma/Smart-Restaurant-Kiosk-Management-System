import os
from werkzeug.utils import secure_filename

from flask import Flask, Response, render_template, request, redirect, session, jsonify
import sqlite3



app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 👇 PEHLE function define kar
def init_db():
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category_id INTEGER,
        price INTEGER,
        image TEXT,
        description TEXT
    )
    ''')
    

    cur.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    ''')

    cur.execute("SELECT * FROM categories")
    if not cur.fetchall():
        cur.execute("INSERT INTO categories (name) VALUES ('Fast Food')")
        cur.execute("INSERT INTO categories (name) VALUES ('Drinks')")
        cur.execute("INSERT INTO categories (name) VALUES ('Desserts')")
     
    

    # admin insert
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    ("admin", "admin123", "admin"))
        
    cur.execute("SELECT * FROM users WHERE username='chef'")
    if not cur.fetchone():
        cur.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        ("chef", "chef123", "chef")
    )   
        
    cur.execute('''
    CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    items TEXT,
    total REAL,
    time TEXT,
    status TEXT DEFAULT 'Preparing',
    order_type TEXT DEFAULT 'Dine In',
    chef_visible INTEGER DEFAULT 1
    )   
    ''')

    # Add order_type / chef_visible columns if upgrading from older schema
    cur.execute("PRAGMA table_info(orders)")
    columns = [row[1] for row in cur.fetchall()]
    if 'order_type' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT 'Dine In'")
        columns.append('order_type')
    if 'chef_visible' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN chef_visible INTEGER DEFAULT 1")

    # Migration: rename 'date' to 'time' if exists
    if 'date' in columns and 'time' not in columns:
        cur.execute("ALTER TABLE orders ADD COLUMN time_temp TEXT")
        cur.execute("UPDATE orders SET time_temp = date")
        cur.execute("ALTER TABLE orders DROP COLUMN date")
        cur.execute("ALTER TABLE orders RENAME COLUMN time_temp TO time")

    conn.commit()
    conn.close()

# 👇 AB call kar
init_db()


#root route
@app.route('/')
def home():
    return redirect('/welcome')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username=? AND password=?",
                    (username, password))

        user = cur.fetchone()
        conn.close()

        if user:
            role = user[3]

            if role == 'admin':
                session['admin'] = True
                return redirect('/admin') 

            elif role == 'chef':
                session['chef'] = True
                return redirect('/chef')
            
  

        return "Invalid Credentials ❌"
    
    

    return render_template('login.html')



#admin route fix
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/login')

    return render_template('admin.html')


#chef route
import json
@app.route('/chef')
def chef_dashboard():
    if not session.get('chef'):
        return "Access Denied ❌"

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders WHERE chef_visible=1 ORDER BY id DESC")
    orders = cur.fetchall()

    conn.close()

    # 🔥 decode items
    decoded_orders = []
    for order in orders:
        items = json.loads(order[2])  # 👈 items column index

        decoded_orders.append({
            "id": order[0],
            "name": order[1],
            "items": items,
            "total": order[3],
            "time": order[4],
            "status": order[5],
            "order_type": order[6] if len(order) > 6 else 'Dine In'
        })

    return render_template('chef.html', orders=decoded_orders)


#ready button route
@app.route('/mark_ready/<int:order_id>', methods=['GET', 'POST'])
def mark_ready(order_id):
    if not session.get('chef'):
        if request.method == 'POST':
            return {"success": False, "error": "Access Denied"}, 403
        return redirect('/login')

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("UPDATE orders SET status='Ready' WHERE id=?", (order_id,))
    conn.commit()

    # 🔥 get order info
    cur.execute("SELECT username FROM orders WHERE id=?", (order_id,))
    user = cur.fetchone()

    conn.close()

    if user:
        session['notify'] = f"{user[0]}, your order #{order_id} is READY!"

    if request.method == 'POST':
        return {"success": True, "order_id": order_id, "status": "Ready"}

    return redirect('/chef')

#add menu route
@app.route('/add_menu', methods=['GET', 'POST'])
def add_menu():
    if not session.get('admin'):
        return "Access Denied ❌"

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description'].strip()
        category_id = request.form['category']

        if description == "":
            description = None

        file = request.files['image']

        filename = None
        if file and file.filename != "":
            from werkzeug.utils import secure_filename
            import os
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        cur.execute(
            "INSERT INTO menu (name, price, image, description, category_id) VALUES (?, ?, ?, ?, ?)",
            (name, price, filename, description, category_id)
        )

        conn.commit()
        conn.close()

        return redirect('/menu?admin_view=true')

    # 👇 GET request → show add page
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()

    conn.close()

    return render_template('add_menu.html', categories=categories)


#view menu route
@app.route('/menu')
def menu():
    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    # menu items with category name
    cur.execute("""
        SELECT menu.*, categories.name 
        FROM menu 
        JOIN categories ON menu.category_id = categories.id
        ORDER BY categories.id
    """)
    items = cur.fetchall()

    # 👇 THIS IS THE REAL FIX
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()

    conn.close()

    # Check if this is an admin view (from admin dashboard)
    is_admin_view = request.args.get('admin_view') == 'true'

    return render_template('menu.html', items=items, categories=categories, is_admin_view=is_admin_view)





#delete menu item route
@app.route('/delete_menu/<int:id>')
def delete_menu(id):
    if not session.get('admin'):
        return "Access Denied ❌"

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("DELETE FROM menu WHERE id=?", (id,))
    
    conn.commit()
    conn.close()

    return redirect('/menu?admin_view=true')

#edit menu item route
@app.route('/edit_menu/<int:id>', methods=['GET', 'POST'])
def edit_menu(id):
    if not session.get('admin'):
        return "Access Denied ❌"

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        category_id = request.form['category']   # 👈 ADD THIS

        file = request.files['image']

        # old image fetch
        cur.execute("SELECT image FROM menu WHERE id=?", (id,))
        old_image = cur.fetchone()[0]

        filename = old_image

        if file and file.filename != "":
            from werkzeug.utils import secure_filename
            import os

            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        cur.execute("""
            UPDATE menu 
            SET name=?, price=?, description=?, image=?, category_id=? 
            WHERE id=?
        """, (name, price, description, filename, category_id, id))

        conn.commit()
        conn.close()

        return redirect('/menu?admin_view=true')

    # GET request
    cur.execute("SELECT * FROM menu WHERE id=?", (id,))
    item = cur.fetchone()

    # 👇 categories fetch karo
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()

    conn.close()

    return render_template('edit_menu.html', item=item, categories=categories)



#welcome page route
@app.route('/welcome')
def welcome():
    return render_template('welcome.html')






# Add to cart route (UPDATED)
@app.route('/add_to_cart/<int:item_id>')
def add_to_cart(item_id):

    cart = session.get('cart', [])

    # 🔹 item find
    found = False
    for item in cart:
        if item['id'] == item_id:
            item['quantity'] += 1
            found = True
            break

    if not found:
        # DB se item fetch (simplified)
        conn = sqlite3.connect('database.db')
        cur = conn.cursor()
        cur.execute("""
        SELECT menu.id, menu.name, menu.price, menu.image, categories.name
        FROM menu
        JOIN categories ON menu.category_id = categories.id
        WHERE menu.id=?
        """, (item_id,))
        data = cur.fetchone()
        conn.close()

        if not data:
            return jsonify({"error": "Item not found"}), 404

        cart.append({
        "id": data[0],
        "name": data[1],
        "price": data[2],
        "image": data[3],       # 🔥 add this
        "category": data[4],    # 🔥 add this
        "quantity": 1
        })

    session['cart'] = cart

    # 🔥 total items count
    total_items = sum(item['quantity'] for item in cart)

    return jsonify({"status": "success", "total_items": total_items})


#coupon apply route
@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():
    code = request.form.get('coupon').upper()

    cart = session.get('cart', [])
    subtotal = sum(item['price'] * item.get('quantity', 1) for item in cart)

    valid_coupons = ["SAVE10", "SAVE20", "FLAT50", "FLAT100", "BIGSAVE"]

    if code not in valid_coupons:
        session.pop('coupon', None)
        session['msg'] = "❌ Invalid Coupon"
    
    elif code == "BIGSAVE" and subtotal < 500:
        session.pop('coupon', None)
        session['msg'] = "⚠️ BIGSAVE works only on orders above ₹500"
    
    else:
        session['coupon'] = code
        session['msg'] = f"✅ {code} Applied"

    return redirect('/cart')


#remove coupon route
@app.route('/remove_coupon')
def remove_coupon():
    session.pop('coupon', None)
    session['msg'] = "❌ Coupon removed"
    return redirect('/cart')




#Cart page route
@app.route('/cart')
def cart():

    cart = session.get('cart', [])

    # fix old items
    for item in cart:
        if 'quantity' not in item:
            item['quantity'] = 1

    subtotal = sum(item['price'] * item['quantity'] for item in cart)

    discount = 0
    coupon = session.get('coupon')

    # 🎟️ coupon logic
    if coupon == "SAVE10":
        discount = subtotal * 0.10

    elif coupon == "SAVE20":
        discount = subtotal * 0.20

    elif coupon == "FLAT50":
        discount = 50

    elif coupon == "FLAT100":
        discount = 100

    elif coupon == "BIGSAVE":
        if subtotal >= 500:
            discount = 100

    # ✅ GST AFTER DISCOUNT
    gst = (subtotal - discount) * 0.05

    # ✅ FINAL TOTAL
    total = subtotal - discount + gst

    msg = session.pop('msg', None)

    return render_template(
        'cart.html',
        cart=cart,
        subtotal=subtotal,
        discount=discount,
        gst=gst,
        total=total,
        coupon=coupon,
        msg=msg
    )


#remove from cart route
@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    cart = session.get('cart', [])

    cart = [item for item in cart if item['id'] != item_id]

    session['cart'] = cart

    return redirect('/cart')

#update cart quantity route
@app.route('/update_quantity/<int:item_id>/<string:action>')
def update_quantity(item_id, action):
    cart = session.get('cart', [])

    for item in cart:
        if item['id'] == item_id:
            if action == 'inc':
                item['quantity'] += 1
            elif action == 'dec':
                item['quantity'] -= 1
                if item['quantity'] <= 0:
                    cart.remove(item)
            break

    session['cart'] = cart

    return redirect('/cart')





#place order route
import json
from datetime import datetime

@app.route('/place_order', methods=['POST'])
def place_order():

    cart = session.get('cart', [])
    

    if not cart:
        return "Cart is empty ❌"

    customer_name = request.form.get('customer_name')

    subtotal = sum(item['price'] * item['quantity'] for item in cart)

    discount = 0
    coupon = session.get('coupon')

    if coupon == "SAVE10":
        discount = subtotal * 0.10
    elif coupon == "FLAT50":
        discount = 50

    gst = (subtotal - discount) * 0.05
    total = subtotal - discount + gst

    import json
    from datetime import datetime

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    order_type = session.get('order_type', 'Dine In')

    cur.execute(
    "INSERT INTO orders (username, items, total, time, status, order_type) VALUES (?, ?, ?, ?, ?, ?)",
    (
        customer_name or "Customer",
        json.dumps(cart),
        total,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Preparing",
        order_type
        )
    )
    order_id = cur.lastrowid   # 🔥 KEY POINT

    session['last_order_id'] = order_id
    session['last_order_name'] = customer_name

    conn.commit()
    conn.close()

    # clear cart
    session.pop('cart', None)
    session.pop('coupon', None)

    return redirect(f'/order_status/{order_id}')


# 🔹 specific order (already correct)
@app.route('/order_status/<int:order_id>')
def order_status(order_id):
    import os
    print("USER DB:", os.path.abspath('database.db'))

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    order = cur.fetchone()

    conn.close()

    import json
    if order:
        order = list(order)
        if len(order) == 6:
            order.append('Dine In')
        order[2] = json.loads(order[2])   # 🔥 items decode

    return render_template('order_status.html', order=order)

@app.route('/order_status')
def check_order():

    order_id = request.args.get('order_id')
    order = None

    if order_id:
        conn = sqlite3.connect('database.db')
        cur = conn.cursor()

        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        order = cur.fetchone()

        conn.close()

        import json
        if order:
            order = list(order)
            if len(order) == 6:
                order.append('Dine In')
            order[2] = json.loads(order[2])   # 🔥 items decode

    return render_template('check_status.html', order=order)


#admin view orders route
@app.route('/admin/orders')
def admin_orders():

    if not session.get('admin'):
        return "Access Denied ❌"

    import json

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders ORDER BY id DESC")
    orders = cur.fetchall()

    conn.close()

    # 🔥 decode items
    decoded_orders = []
    for order in orders:
        decoded_orders.append({
            "id": order[0],
            "name": order[1],
            "items": json.loads(order[2]),
            "total": order[3],
            "time": order[4],
            "status": order[5],
            "order_type": order[6] if len(order) > 6 else 'Dine In'
        })

    return render_template('admin_orders.html', orders=decoded_orders)





#check status api route
@app.route('/check_status_api/<int:order_id>')
def check_status_api(order_id):

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT status, username FROM orders WHERE id=?", (order_id,))
    order = cur.fetchone()

    conn.close()

    if order:
        return {
            "status": order[0],
            "name": order[1]
        }

    return {"status": "Not Found"}

#chef orders api route
@app.route('/chef_orders_api')
def chef_orders_api():

    import json

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT * FROM orders WHERE chef_visible=1 ORDER BY id DESC")
    rows = cur.fetchall()

    conn.close()

    orders = []
    for row in rows:
        orders.append({
            "id": row[0],
            "name": row[1],
            "items": json.loads(row[2]),   # ✅ correct
            "total": row[3],               # ✅ correct
            "time": row[4],                # ✅ correct
            "status": row[5],              # ✅ correct
            "order_type": row[6] if len(row) > 6 else "Dine In"
        })

    return {"orders": orders}


@app.route('/reset_orders', methods=['POST'])
def reset_orders():
    if not session.get('chef'):
        return {"success": False, "error": "Access Denied"}, 403

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()
    cur.execute("UPDATE orders SET chef_visible = 0 WHERE chef_visible = 1")
    conn.commit()
    conn.close()

    return {"success": True}


#latest orders api route
@app.route('/latest_order_api')
def latest_order_api():

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT id, username, status FROM orders ORDER BY id DESC LIMIT 1")
    order = cur.fetchone()

    conn.close()

    if order:
        return {
            "id": order[0],
            "name": order[1],
            "status": order[2]
        }

    return {}


#order type selection route
@app.route('/order_type')
def order_type():
    return render_template('order_type.html')

@app.route('/set_order_type/<type>')
def set_order_type(type):
    # Normalize to proper format
    if type.lower() in ['dinein', 'dine in']:
        session['order_type'] = 'Dine In'
    else:
        session['order_type'] = 'Take Away'

    # 🔥 clear old cart only when arriving from the welcome page flow
    session.pop('cart', None)
    session.pop('coupon', None)

    return redirect('/menu')



if __name__ == '__main__':
    app.run(debug=True)

    