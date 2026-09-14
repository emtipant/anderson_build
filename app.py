from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.utils import secure_filename
import sqlite3, os, uuid, json, re

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "anderson.db")
UPLOAD = os.path.join(BASE, "static", "uploads")
os.makedirs(UPLOAD, exist_ok=True)

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-en-produccion"
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
ALLOWED = {"png", "jpg", "jpeg", "webp", "gif", "svg"}


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS products(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL, description TEXT, category TEXT NOT NULL,
      price REAL NOT NULL, old_price REAL DEFAULT 0, stock INTEGER DEFAULT 0,
      image TEXT NOT NULL, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS carousel(
      id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, image TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS nav_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, url TEXT NOT NULL,
      sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS categories(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, image TEXT DEFAULT '',
      sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS pages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL, content TEXT DEFAULT '', image TEXT DEFAULT '',
      sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS page_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT, page_id INTEGER NOT NULL,
      title TEXT NOT NULL, description TEXT DEFAULT '', image TEXT DEFAULT '',
      sort_order INTEGER DEFAULT 0, active INTEGER DEFAULT 1,
      FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE
    );
    """)

    # Compatibilidad con bases creadas por versiones anteriores.
    cols = [r[1] for r in con.execute("PRAGMA table_info(pages)").fetchall()]
    if "image" not in cols:
        con.execute("ALTER TABLE pages ADD COLUMN image TEXT DEFAULT ''")

    # Campos adicionales de productos para la ficha detallada.
    product_cols = [r[1] for r in con.execute("PRAGMA table_info(products)").fetchall()]
    if "details" not in product_cols:
        con.execute("ALTER TABLE products ADD COLUMN details TEXT DEFAULT ''")
    if "colors" not in product_cols:
        con.execute("ALTER TABLE products ADD COLUMN colors TEXT DEFAULT ''")
    if "gallery" not in product_cols:
        con.execute("ALTER TABLE products ADD COLUMN gallery TEXT DEFAULT '[]'")

    if con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        demo = [
          ("Refrigeradora 390L", "Refrigeradora de gran capacidad", "Electrodomésticos", 899, 0, 8, "https://images.unsplash.com/photo-1584568694244-14fbdf83bd30?auto=format&fit=crop&w=600&q=80"),
          ('Televisor Smart TV 55"', "Smart TV de alta definición", "Tecnología", 599, 0, 15, "https://images.unsplash.com/photo-1593784991095-a205069470b6?auto=format&fit=crop&w=600&q=80"),
          ("Lavadora 18kg", "Lavadora de carga superior", "Electrodomésticos", 649, 699, 12, "https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?auto=format&fit=crop&w=600&q=80"),
          ("Laptop HP 15.6", "Laptop para trabajo y estudio", "Tecnología", 669, 699, 20, "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?auto=format&fit=crop&w=600&q=80"),
          ("Moto Shineray XY200", "Motocicleta urbana", "Motos", 1399, 0, 8, "https://images.unsplash.com/photo-1558981806-ec527fa84c39?auto=format&fit=crop&w=600&q=80"),
          ("Parlante JBL PartyBox 110", "Parlante Bluetooth", "Audio y Video", 399, 0, 15, "https://images.unsplash.com/photo-1545454675-3531b543be5d?auto=format&fit=crop&w=600&q=80")
        ]
        con.executemany("INSERT INTO products(name,description,category,price,old_price,stock,image) VALUES(?,?,?,?,?,?,?)", demo)

    if con.execute("SELECT COUNT(*) FROM carousel").fetchone()[0] == 0:
        hero = [
          "https://images.unsplash.com/photo-1556740749-887f6717d7e4?auto=format&fit=crop&w=1600&q=85",
          "https://images.unsplash.com/photo-1607082349566-187342175e2f?auto=format&fit=crop&w=1600&q=85",
          "https://images.unsplash.com/photo-1472851294608-062f824d29cc?auto=format&fit=crop&w=1600&q=85"
        ]
        offers = [
          "https://images.unsplash.com/photo-1607083206968-13611e3d76db?auto=format&fit=crop&w=1600&q=85",
          "https://images.unsplash.com/photo-1555529669-e69e7aa0ba9a?auto=format&fit=crop&w=1600&q=85"
        ]
        for x in hero: con.execute("INSERT INTO carousel(kind,image) VALUES('hero',?)", (x,))
        for x in offers: con.execute("INSERT INTO carousel(kind,image) VALUES('offer',?)", (x,))

    defaults = [
        ("logo", ""),
        ("mini_text", "🚚 Envío nacional | 🛡 Compra 100% segura | ✓ Garantía Anderson")
    ]
    for k, v in defaults:
        if not con.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone():
            con.execute("INSERT INTO settings(key,value) VALUES(?,?)", (k, v))

    if con.execute("SELECT COUNT(*) FROM nav_items").fetchone()[0] == 0:
        nav = [("Inicio", "/", 1), ("Ofertas", "#ofertas", 2), ("Productos", "#productos", 3),
               ("Marcas", "#marcas", 4), ("Novedades", "#novedades", 5), ("Servicios", "#servicios", 6),
               ("Nosotros", "#nosotros", 7), ("Contacto", "#contacto", 8)]
        con.executemany("INSERT INTO nav_items(label,url,sort_order) VALUES(?,?,?)", nav)

    default_categories = [
        ("Electrodomésticos", "", 1), ("Tecnología", "", 2), ("Motos", "", 3), ("Hogar", "", 4),
        ("Audio y Video", "", 5), ("Herramientas", "", 6), ("Celulares", "", 7), ("Deportes", "", 8)
    ]
    if con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        con.executemany("INSERT INTO categories(name,image,sort_order) VALUES(?,?,?)", default_categories)

    default_pages = [
        ("novedades", "NOVEDADES", "Aquí puedes publicar novedades, promociones, lanzamientos y noticias de la tienda.", 1),
        ("servicios", "SERVICIOS", "Agrega todos los servicios que ofrece Almacenes Anderson.", 2),
        ("nosotros", "NOSOTROS", "Escribe aquí la historia, misión, visión y descripción de tu negocio.", 3),
        ("contacto", "CONTACTO", "Agrega teléfonos, WhatsApp, dirección, horarios, correo y cualquier información de contacto.", 4),
    ]
    for slug, title, content, order in default_pages:
        if not con.execute("SELECT 1 FROM pages WHERE slug=?", (slug,)).fetchone():
            con.execute("INSERT INTO pages(slug,title,content,sort_order,image) VALUES(?,?,?,?,?)", (slug,title,content,order,""))

    con.commit(); con.close()


def allowed(name):
    return bool(name and "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED)


def save_upload(file):
    if not file or not file.filename or not allowed(file.filename): return None
    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD, filename))
    return f"/static/uploads/{filename}"


def save_uploads(files):
    saved = []
    for f in files or []:
        image = save_upload(f)
        if image:
            saved.append(image)
    return saved


def product_gallery(row):
    try:
        gallery = json.loads(row["gallery"] or "[]")
        if not isinstance(gallery, list):
            gallery = []
    except (TypeError, json.JSONDecodeError):
        gallery = []
    main = row["image"]
    return [main] + [x for x in gallery if x and x != main]


def delete_local_file(path):
    if not path or not path.startswith("/static/uploads/"): return
    full = os.path.join(BASE, path.lstrip("/"))
    if os.path.isfile(full):
        try: os.remove(full)
        except OSError: pass


def settings_dict(con):
    return {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings").fetchall()}


def page_data(con):
    pages = con.execute("SELECT * FROM pages WHERE active=1 ORDER BY sort_order,id").fetchall()
    result = []
    for p in pages:
        d = dict(p)
        d["items"] = [dict(x) for x in con.execute("SELECT * FROM page_items WHERE page_id=? AND active=1 ORDER BY sort_order,id", (p["id"],)).fetchall()]
        result.append(d)
    return result


@app.route("/")
def index():
    con = db()
    products = con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall()
    hero = con.execute("SELECT * FROM carousel WHERE kind='hero' ORDER BY id").fetchall()
    offers = con.execute("SELECT * FROM carousel WHERE kind='offer' ORDER BY id").fetchall()
    nav = con.execute("SELECT * FROM nav_items WHERE active=1 ORDER BY sort_order,id").fetchall()
    categories = con.execute("SELECT * FROM categories WHERE active=1 ORDER BY sort_order,id").fetchall()
    pages = page_data(con)
    settings = settings_dict(con); con.close()
    return render_template("index.html", products=products, hero=hero, offers=offers, nav=nav, categories=categories, pages=pages,
                           logo=settings.get("logo", ""), mini_text=settings.get("mini_text", ""))


@app.route("/producto/<int:pid>")
def product_detail(pid):
    con = db()
    product = con.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    con.close()
    if not product:
        return "Producto no encontrado", 404
    p = dict(product)
    p["gallery"] = product_gallery(product)
    p["colors_list"] = [x.strip() for x in re.split(r"[,\n]", p.get("colors", "")) if x.strip()]
    con = db(); settings = settings_dict(con); con.close()
    return render_template("product_detail.html", p=p, logo=settings.get("logo", ""), mini_text=settings.get("mini_text", ""))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("user") == "propietario" and request.form.get("password") == "anderson123":
            session["admin"] = True; return redirect(url_for("admin"))
        flash("Usuario o contraseña incorrectos.")
    con = db(); settings = settings_dict(con); con.close()
    return render_template("login.html", logo=settings.get("logo", ""))


@app.route("/admin")
def admin():
    if not session.get("admin"): return redirect(url_for("login"))
    con = db()
    products = con.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    hero = con.execute("SELECT * FROM carousel WHERE kind='hero' ORDER BY id").fetchall()
    offers = con.execute("SELECT * FROM carousel WHERE kind='offer' ORDER BY id").fetchall()
    nav = con.execute("SELECT * FROM nav_items ORDER BY sort_order,id").fetchall()
    categories = con.execute("SELECT * FROM categories ORDER BY sort_order,id").fetchall()
    pages = [dict(p, items=[dict(x) for x in con.execute("SELECT * FROM page_items WHERE page_id=? ORDER BY sort_order,id", (p["id"],)).fetchall()]) for p in con.execute("SELECT * FROM pages ORDER BY sort_order,id").fetchall()]
    settings = settings_dict(con); con.close()
    return render_template("admin.html", products=products, hero=hero, offers=offers, nav=nav, categories=categories, pages=pages,
                           logo=settings.get("logo", ""), mini_text=settings.get("mini_text", ""))


@app.post("/admin/product/add")
def add_product():
    if not session.get("admin"): return redirect(url_for("login"))
    image = save_upload(request.files.get("image"))
    gallery = save_uploads(request.files.getlist("gallery"))
    if not image:
        for x in gallery: delete_local_file(x)
        flash("Selecciona una imagen principal JPG, PNG, WEBP, GIF o SVG.")
        return redirect(url_for("admin"))
    try:
        price=float(request.form.get("price",0)); old=float(request.form.get("old_price",0) or 0); stock=int(request.form.get("stock",0))
    except ValueError:
        delete_local_file(image)
        for x in gallery: delete_local_file(x)
        flash("Precio o stock inválido.")
        return redirect(url_for("admin"))
    con=db()
    con.execute("INSERT INTO products(name,description,category,price,old_price,stock,image,details,colors,gallery) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (request.form.get("name","").strip(), request.form.get("description",""), request.form.get("category","General").strip(), price, old, stock, image, request.form.get("details",""), request.form.get("colors",""), json.dumps(gallery)))
    con.commit(); con.close()
    return redirect(url_for("admin"))


@app.post("/admin/product/<int:pid>/edit")
def edit_product(pid):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); old=con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not old:
        con.close(); return redirect(url_for("admin"))
    new_image=save_upload(request.files.get("image"))
    new_gallery=save_uploads(request.files.getlist("gallery"))
    try:
        price=float(request.form.get("price",0)); old_price=float(request.form.get("old_price",0) or 0); stock=int(request.form.get("stock",0))
        current_gallery=json.loads(old["gallery"] or "[]") if old["gallery"] else []
        if not isinstance(current_gallery,list): current_gallery=[]
        image=new_image or old["image"]
        gallery=current_gallery + new_gallery
        con.execute("""UPDATE products SET name=?,description=?,category=?,price=?,old_price=?,stock=?,image=?,details=?,colors=?,gallery=? WHERE id=?""",
            (request.form.get("name","").strip(), request.form.get("description",""), request.form.get("category","General").strip(), price, old_price, stock, image, request.form.get("details",""), request.form.get("colors",""), json.dumps(gallery), pid))
        con.commit()
    except (ValueError, json.JSONDecodeError):
        if new_image: delete_local_file(new_image)
        for x in new_gallery: delete_local_file(x)
        flash("Datos del producto inválidos.")
    con.close()
    if new_image and old["image"] != new_image: delete_local_file(old["image"])
    return redirect(url_for("admin"))


@app.post("/admin/carousel/<kind>/add")
def add_carousel(kind):
    if not session.get("admin") or kind not in ("hero","offer"): return redirect(url_for("login"))
    con=db()
    for f in request.files.getlist("images"):
        image=save_upload(f)
        if image: con.execute("INSERT INTO carousel(kind,image) VALUES(?,?)",(kind,image))
    con.commit(); con.close(); return redirect(url_for("admin"))


@app.post("/admin/product/<int:pid>/delete")
def delete_product(pid):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); row=con.execute("SELECT image,gallery FROM products WHERE id=?",(pid,)).fetchone(); con.execute("DELETE FROM products WHERE id=?",(pid,)); con.commit(); con.close()
    if row:
        delete_local_file(row["image"])
        try:
            for x in json.loads(row["gallery"] or "[]"):
                delete_local_file(x)
        except (TypeError, json.JSONDecodeError):
            pass
    return redirect(url_for("admin"))


@app.post("/admin/carousel/<int:cid>/delete")
def delete_carousel(cid):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); row=con.execute("SELECT image FROM carousel WHERE id=?",(cid,)).fetchone(); con.execute("DELETE FROM carousel WHERE id=?",(cid,)); con.commit(); con.close()
    if row: delete_local_file(row["image"])
    return redirect(url_for("admin"))


@app.post("/admin/logo")
def update_logo():
    if not session.get("admin"): return redirect(url_for("login"))
    image=save_upload(request.files.get("logo"))
    if not image: flash("Selecciona el archivo del logo."); return redirect(url_for("admin"))
    con=db(); old=con.execute("SELECT value FROM settings WHERE key='logo'").fetchone(); con.execute("INSERT INTO settings(key,value) VALUES('logo',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(image,)); con.commit(); con.close()
    if old: delete_local_file(old[0])
    return redirect(url_for("admin"))


@app.post("/admin/settings")
def update_settings():
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); con.execute("INSERT INTO settings(key,value) VALUES('mini_text',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(request.form.get("mini_text","").strip(),)); con.commit(); con.close(); return redirect(url_for("admin"))


@app.post("/admin/nav/add")
def add_nav():
    if not session.get("admin"): return redirect(url_for("login"))
    label=request.form.get("label","").strip(); target=request.form.get("url","").strip()
    if not label or not target: flash("Escribe el nombre y el enlace del menú."); return redirect(url_for("admin"))
    con=db(); order=con.execute("SELECT COALESCE(MAX(sort_order),0) FROM nav_items").fetchone()[0]; con.execute("INSERT INTO nav_items(label,url,sort_order) VALUES(?,?,?)",(label,target,order+1)); con.commit(); con.close(); return redirect(url_for("admin"))


@app.post("/admin/nav/<int:nid>/delete")
def delete_nav(nid):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); con.execute("DELETE FROM nav_items WHERE id=?",(nid,)); con.commit(); con.close(); return redirect(url_for("admin"))


@app.post("/admin/nav/<int:nid>/edit")
def edit_nav(nid):
    if not session.get("admin"): return redirect(url_for("login"))
    label=request.form.get("label","").strip(); target=request.form.get("url","").strip()
    if label and target:
        con=db(); con.execute("UPDATE nav_items SET label=?,url=? WHERE id=?",(label,target,nid)); con.commit(); con.close()
    return redirect(url_for("admin"))


@app.post("/admin/category/add")
def add_category():
    if not session.get("admin"): return redirect(url_for("login"))
    name=request.form.get("name","").strip(); image=save_upload(request.files.get("image"))
    if not name:
        delete_local_file(image); flash("Escribe el nombre de la categoría."); return redirect(url_for("admin"))
    con=db()
    try:
        order=con.execute("SELECT COALESCE(MAX(sort_order),0) FROM categories").fetchone()[0]
        con.execute("INSERT INTO categories(name,image,sort_order) VALUES(?,?,?)",(name,image or "",order+1)); con.commit()
    except sqlite3.IntegrityError:
        delete_local_file(image); flash("Esa categoría ya existe.")
    con.close(); return redirect(url_for("admin"))


@app.post("/admin/category/<int:cid>/edit")
def edit_category(cid):
    if not session.get("admin"): return redirect(url_for("login"))
    name=request.form.get("name","").strip()
    con=db(); old=con.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
    if not old or not name:
        con.close(); return redirect(url_for("admin"))
    new_image=save_upload(request.files.get("image"))
    image=new_image if new_image else old["image"]
    try:
        con.execute("UPDATE categories SET name=?,image=? WHERE id=?",(name,image,cid)); con.commit()
    except sqlite3.IntegrityError:
        delete_local_file(new_image); flash("Esa categoría ya existe.")
    con.close()
    if new_image and old["image"] and old["image"] != new_image: delete_local_file(old["image"])
    return redirect(url_for("admin"))


@app.post("/admin/category/<int:cid>/delete")
def delete_category(cid):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); row=con.execute("SELECT image FROM categories WHERE id=?",(cid,)).fetchone(); con.execute("DELETE FROM categories WHERE id=?",(cid,)); con.commit(); con.close()
    if row: delete_local_file(row["image"])
    return redirect(url_for("admin"))


@app.post("/admin/page/add")
def add_page():
    if not session.get("admin"): return redirect(url_for("login"))
    title=request.form.get("title","").strip(); slug=request.form.get("slug","").strip().lower().replace(" ","-"); content=request.form.get("content","").strip(); image=save_upload(request.files.get("image"))
    if not title or not slug: delete_local_file(image); flash("Escribe título e identificador."); return redirect(url_for("admin"))
    con=db()
    try:
        order=con.execute("SELECT COALESCE(MAX(sort_order),0) FROM pages").fetchone()[0]; con.execute("INSERT INTO pages(slug,title,content,image,sort_order) VALUES(?,?,?,?,?)",(slug,title,content,image or "",order+1)); con.commit()
    except sqlite3.IntegrityError:
        delete_local_file(image); flash("Ese identificador ya existe. Usa otro.")
    con.close(); return redirect(url_for("admin"))


@app.post("/admin/page/<int:page_id>/edit")
def edit_page(page_id):
    if not session.get("admin"): return redirect(url_for("login"))
    title=request.form.get("title","").strip(); slug=request.form.get("slug","").strip().lower().replace(" ","-"); content=request.form.get("content","").strip()
    if not title or not slug: return redirect(url_for("admin"))
    con=db(); old=con.execute("SELECT image FROM pages WHERE id=?",(page_id,)).fetchone(); new_image=save_upload(request.files.get("image"))
    try:
        image=new_image if new_image else (old["image"] if old else "")
        con.execute("UPDATE pages SET title=?,slug=?,content=?,image=? WHERE id=?",(title,slug,content,image,page_id)); con.commit()
    except sqlite3.IntegrityError:
        delete_local_file(new_image); flash("Ese identificador ya existe.")
    con.close()
    if new_image and old: delete_local_file(old["image"])
    return redirect(url_for("admin"))


@app.post("/admin/page/<int:page_id>/delete")
def delete_page(page_id):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); page=con.execute("SELECT image FROM pages WHERE id=?",(page_id,)).fetchone(); items=con.execute("SELECT image FROM page_items WHERE page_id=?",(page_id,)).fetchall(); con.execute("DELETE FROM page_items WHERE page_id=?",(page_id,)); con.execute("DELETE FROM pages WHERE id=?",(page_id,)); con.commit(); con.close()
    if page: delete_local_file(page["image"])
    for x in items: delete_local_file(x["image"])
    return redirect(url_for("admin"))


@app.post("/admin/page/<int:page_id>/item/add")
def add_page_item(page_id):
    if not session.get("admin"): return redirect(url_for("login"))
    title=request.form.get("title","").strip(); description=request.form.get("description","").strip(); image=save_upload(request.files.get("image"))
    if not title: delete_local_file(image); flash("Escribe el nombre del elemento."); return redirect(url_for("admin"))
    con=db(); order=con.execute("SELECT COALESCE(MAX(sort_order),0) FROM page_items WHERE page_id=?",(page_id,)).fetchone()[0]; con.execute("INSERT INTO page_items(page_id,title,description,image,sort_order) VALUES(?,?,?,?,?)",(page_id,title,description,image or "",order+1)); con.commit(); con.close(); return redirect(url_for("admin"))


@app.post("/admin/page/item/<int:item_id>/edit")
def edit_page_item(item_id):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); old=con.execute("SELECT image FROM page_items WHERE id=?",(item_id,)).fetchone(); title=request.form.get("title","").strip(); description=request.form.get("description","").strip(); new_image=save_upload(request.files.get("image"))
    if title:
        image=new_image if new_image else (old["image"] if old else ""); con.execute("UPDATE page_items SET title=?,description=?,image=? WHERE id=?",(title,description,image,item_id)); con.commit()
    con.close()
    if new_image and old: delete_local_file(old["image"])
    return redirect(url_for("admin"))


@app.post("/admin/page/item/<int:item_id>/delete")
def delete_page_item(item_id):
    if not session.get("admin"): return redirect(url_for("login"))
    con=db(); row=con.execute("SELECT image FROM page_items WHERE id=?",(item_id,)).fetchone(); con.execute("DELETE FROM page_items WHERE id=?",(item_id,)); con.commit(); con.close();
    if row: delete_local_file(row["image"])
    return redirect(url_for("admin"))


@app.get("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))


@app.get("/api/products")
def api_products():
    con=db(); rows=[dict(x) for x in con.execute("SELECT * FROM products WHERE active=1").fetchall()]; con.close(); return jsonify(rows)


init_db()
if __name__ == "__main__": app.run(debug=True)
