import os
import time
import jwt
import qrcode
import numpy as np
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename

from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input
from tensorflow.keras.preprocessing import image
from tensorflow.keras.models import Model
from sklearn.metrics.pairwise import cosine_similarity

from extensions import db
from models import User, LostItem, FoundItem, Reward, Notification, Message
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
app = Flask(__name__, static_folder="static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "sk_8f92kjsdf9234@#kjsdf9234kjsdf!")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "286841684345-d8v35mfp128cou6v0nu37eurd6b6uae1.apps.googleusercontent.com")

@app.route("/google-login", methods=["POST"])
def google_login():

    try:

        data = request.get_json()

        token = data.get("token")
        selected_role = data.get("role")

        if not token:
            return jsonify({"msg": "Google token missing"}), 400

        # VERIFY TOKEN
        idinfo = id_token.verify_oauth2_token(
            token,
            grequests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo.get("email")
        name = idinfo.get("name", "Google User")

        if not email:
            return jsonify({"msg": "Google email missing"}), 400

        # CHECK USER
        user = User.query.filter_by(email=email).first()

        # ================= NEW USER =================
        if not user:

            if not selected_role:
                return jsonify({
                    "new_user": True,
                    "msg": "Role required"
                }), 200

            user = User(
                name=name,
                email=email,
                role=selected_role
            )

            user.set_password("google_user")

            db.session.add(user)
            db.session.commit()

        # ================= JWT TOKEN =================
        jwt_token = jwt.encode({
            "user_id": user.id,
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(hours=5)
        },
        app.config["SECRET_KEY"],
        algorithm="HS256")

        return jsonify({
            "msg": "Google login successful",
            "token": jwt_token,
            "user_id": user.id,
            "role": user.role,
            "name": user.name,
            "new_user": False
        }), 200

    except ValueError as e:
        print("GOOGLE TOKEN ERROR:", e)
        return jsonify({"msg": "Invalid Google token"}), 401

    except Exception as e:
        print("GOOGLE LOGIN ERROR:", e)
        return jsonify({"msg": "Server error"}), 500
# ================= IMAGE UPLOAD CONFIG =================

# Folder for Lost & Found item images
ITEM_UPLOAD_FOLDER = "static/uploads"
os.makedirs(ITEM_UPLOAD_FOLDER, exist_ok=True)

## Folder for Chat images
CHAT_UPLOAD_FOLDER = "static/chat_images"
os.makedirs(CHAT_UPLOAD_FOLDER, exist_ok=True)


PROFILE_UPLOAD_FOLDER = "static/profile_pics"

os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)



app.config["ITEM_UPLOAD_FOLDER"] = ITEM_UPLOAD_FOLDER
app.config["CHAT_UPLOAD_FOLDER"] = CHAT_UPLOAD_FOLDER

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet" if os.getenv("PORT") else "threading",
    manage_session=False,
    logger=False,
    engineio_logger=False
)
# ===== ONLINE USERS TRACK =====
online_users = set()



# ================= CONFIG =================
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+pymysql://root:@localhost/lostfound_db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# ================= AI MODEL LAZY LOAD =================
_ai_model = None

def get_ai_model():
    global _ai_model
    if _ai_model is None:
        print("[INFO] Loading AI model...")
        base_model = ResNet50(weights="imagenet")
        _ai_model = Model(
            inputs=base_model.input,
            outputs=base_model.layers[-2].output
        )
    return _ai_model

# ================= HOME =================
@app.route("/")
def home():
    return "Backend is running successfully!"

# ================= AUTH =================
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()

    # 🔒 BASIC VALIDATION
    if not data or not data.get("email") or not data.get("password") or not data.get("name") or not data.get("role"):
        return jsonify({"msg": "All fields are required"}), 400

    # 🔒 CHECK EXISTING USER
    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"msg": "Email already exists"}), 409

    # 🔒 CREATE USER
    user = User(
        name=data["name"],
        email=data["email"],
        role=data["role"]
    )
    user.set_password(data["password"])

    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "Account created successfully"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    # 🔒 VALIDATION
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"msg": "Email and password required"}), 400

    user = User.query.filter_by(email=data["email"]).first()

    # 🔒 INVALID LOGIN
    if not user or not user.check_password(data["password"]):
        return jsonify({"msg": "Invalid credentials"}), 401

    # 🔐 CREATE JWT TOKEN (SHORTER EXPIRY)
    token = jwt.encode({
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=2)
    }, app.config["SECRET_KEY"], algorithm="HS256")

    return jsonify({
        "msg": "Login successful",
        "token": token,
        "user_id": user.id,
        "role": user.role,
        "name": user.name
    }), 200


# ================= TOKEN SECURITY =================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        auth_header = request.headers.get("Authorization")

        # 🔒 TOKEN MISSING
        if not auth_header:
            return jsonify({"msg": "Token missing"}), 401

        try:
            # 🔥 FORMAT: Bearer TOKEN
            token = auth_header.split(" ")[1]

            data = jwt.decode(
                token,
                app.config["SECRET_KEY"],
                algorithms=["HS256"]
            )

            current_user = User.query.get(data["user_id"])

            # 🔒 USER NOT FOUND
            if not current_user:
                return jsonify({"msg": "User not found"}), 404

        except jwt.ExpiredSignatureError:
            return jsonify({"msg": "Token expired"}), 401

        except jwt.InvalidTokenError:
            return jsonify({"msg": "Invalid token"}), 401

        except Exception:
            return jsonify({"msg": "Token error"}), 401

        return f(current_user, *args, **kwargs)

    return decorated



# 👇 👇 👇 YAHAN ADD KARO
def admin_required(f):
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        if current_user.role != "admin":
            return jsonify({"msg": "Admin access required"}), 403
        return f(current_user, *args, **kwargs)
    return decorated

# ================= PROFILE IMAGE UPLOAD =================
@app.route("/upload-profile", methods=["POST"])
@token_required
def upload_profile(current_user):

    if "image" not in request.files:
        return jsonify({"msg": "No image uploaded"}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"msg": "No selected file"}), 400

    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ext = file.filename.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"msg": "Invalid file type"}), 400

    filename = secure_filename(f"chat_{current_user.id}_{int(time.time())}.{ext}")


    upload_folder = "static/profile_pics"
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, filename)

    file.save(filepath)

    # 🔒 SAVE TO DB
    current_user.profile_image = filename
    db.session.commit()

    return jsonify({"msg": "Profile image updated successfully"}), 200


# ================= LOST ITEM =================
@app.route("/lost-item", methods=["POST"])
@token_required
def report_lost_item(current_user):

    item_name = request.form.get("item_name")
    description = request.form.get("description")
    location = request.form.get("location")

    # 🔒 VALIDATION
    if not item_name or not description or not location:
        return jsonify({"msg": "All fields are required"}), 400

    image_file = request.files.get("image")
    filename = None

    if image_file and image_file.filename != "":


        # 🔒 FILE TYPE CHECK
        ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
        ext = image_file.filename.rsplit(".", 1)[-1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"msg": "Invalid image type"}), 400

        # 🔒 SAFE NAME
        clean_item_name = secure_filename(item_name)
        filename = f"lost_{clean_item_name}_{int(time.time())}.{ext}"

        os.makedirs(app.config["ITEM_UPLOAD_FOLDER"], exist_ok=True)
        filepath = os.path.join(app.config["ITEM_UPLOAD_FOLDER"], filename)

        image_file.save(filepath)

    # 🔒 SAVE ITEM
    item = LostItem(
        item_name=item_name,
        description=description,
        location=location,
        owner_id=current_user.id,
        status="Lost",
        image=filename
    )

    db.session.add(item)
    db.session.commit()

    # ========= QR CODE =========
    qr_dir = "static/qr_codes"
    os.makedirs(qr_dir, exist_ok=True)

    qr_filename = f"lost_item_{item.id}.png"
    qr_path = f"qr_codes/{qr_filename}"
    full_path = os.path.join("static", qr_path)

    qr_url = f"{request.host_url.rstrip('/')}/qr/{item.id}"
    qr_img = qrcode.make(qr_url)
    qr_img.save(full_path)

    item.qr_code = qr_path
    db.session.commit()

    return jsonify({
        "msg": "Lost item reported successfully",
        "qr_code": qr_path
    }), 201


# ================= GET LOST ITEMS =================
@app.route("/lost-items", methods=["GET"])
def get_lost_items():

    lost_items = LostItem.query.filter(
        LostItem.status != "Returned"
    ).options(db.joinedload(LostItem.owner)).all()

    result = []

    for i in lost_items:
        owner = i.owner

        result.append({
            "id": i.id,
            "item_name": i.item_name,
            "description": i.description,
            "location": i.location,
            "status": i.status,

            # 🔥 THIS IS THE FIX
            "owner_name": owner.name if owner else "Unknown",

            "image": i.image
        })

    return jsonify(result), 200

@app.route("/my-lost-items")
@token_required
def my_lost_items(current_user):

    lost_items = LostItem.query.filter_by(owner_id=current_user.id).all()

    result = []

    for item in lost_items:

        matched_found = FoundItem.query.filter_by(
            matched_lost_item_id=item.id,
            is_matched=True
        ).first()

        result.append({
            "id": item.id,
            "item_name": item.item_name,
            "description": item.description,
            "location": item.location,
            "status": item.status,
            "qr_code": item.qr_code,
            "is_matched": True if matched_found else False,
            "chat_requested": item.chat_requested,
            "chat_approved": item.chat_approved
        })

    return jsonify(result), 200


# ================= FOUND ITEM =================
@app.route("/found-item", methods=["POST"])
@token_required
def report_found_item(current_user):

    item_name = request.form.get("item_name")
    description = request.form.get("description")
    location = request.form.get("location")
    location_name = request.form.get("location_name")

    # 🔒 VALIDATION
    if not item_name or not description:
        return jsonify({"msg": "Item name and description required"}), 400

    image_file = request.files.get("image")
    filename = None

    if image_file and image_file.filename != "":


        # 🔒 FILE TYPE CHECK
        ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
        ext = image_file.filename.rsplit(".", 1)[-1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"msg": "Invalid image type"}), 400

        # 🔒 SAFE FILENAME
        clean_item_name = secure_filename(item_name)
        filename = f"found_{clean_item_name}_{int(time.time())}.{ext}"

        os.makedirs(app.config["ITEM_UPLOAD_FOLDER"], exist_ok=True)
        filepath = os.path.join(app.config["ITEM_UPLOAD_FOLDER"], filename)

        image_file.save(filepath)

    # 🔒 DEFAULTS
    if not location:
        location = "Not specified"

    if not location_name:
        location_name = "Unknown Location"

    # 🔒 SAVE
    item = FoundItem(
        item_name=item_name,
        description=description,
        location=location,
        location_name=location_name,
        finder_id=current_user.id,
        status="Found",
        image=filename
    )

    db.session.add(item)
    db.session.commit()

    return jsonify({
        "msg": "Found item reported successfully",
        "location_name": location_name
    }), 201


# ================= GET FOUND ITEMS =================
@app.route("/found-items", methods=["GET"])
def get_found_items():

    items = FoundItem.query.filter(
    FoundItem.status != "Returned"
    ).all()


    result = []

    for i in items:

        result.append({
            "id": i.id,
            "item_name": i.item_name,
            "description": i.description,

            # ✅ location data
            "location": i.location,
            "location_name": i.location_name,

            "is_matched": i.is_matched,
            "matched_lost_item_id": i.matched_lost_item_id,

            # 🔒 SAFE ACCESS
            "chat_approved": (
                LostItem.query.get(i.matched_lost_item_id).chat_approved
                if i.matched_lost_item_id and LostItem.query.get(i.matched_lost_item_id)
                else False
            ),

            # 🔒 REMOVE finder_id (privacy)
            # "finder_id": i.finder_id ❌ REMOVE

            "image": i.image
        })

    return jsonify(result), 200

@app.route("/my-found-items")
@token_required
def my_found_items(current_user):

    items = FoundItem.query.filter_by(
        finder_id=current_user.id
    ).all()



    return jsonify([
        {
            "id": i.id,
            "item_name": i.item_name,
            "location": i.location,
            "location_name": i.location_name,
            "status": i.status,
            "image": i.image,
            "is_matched": i.is_matched,
            "matched_lost_item_id": i.matched_lost_item_id,
            "chat_approved": (
                LostItem.query.get(i.matched_lost_item_id).chat_approved
                if i.matched_lost_item_id and LostItem.query.get(i.matched_lost_item_id)
                else False
            )
        }
        for i in items
    ])

# ================= FINDER DASHBOARD =================
@app.route("/finder-dashboard")
@token_required
def finder_dashboard(current_user):

    # 🔒 ROLE CHECK
    if current_user.role != "finder":
        return jsonify({"msg": "Access denied"}), 403

    rewards = Reward.query.filter_by(finder_id=current_user.id).all()

    return jsonify({
        "name": current_user.name,
        "total_points": current_user.total_points,
        "badge": current_user.badge,
        "profile_image": current_user.profile_image,
        "rewards": [
            {
                "points": r.points,
                "status": r.status
            } for r in rewards
        ]
    }), 200


# ================= GET USER =================
@app.route("/user/<int:user_id>", methods=["GET"])
@token_required
def get_user(current_user, user_id):

    # 🔒 ONLY SELF ACCESS
    if current_user.id != user_id:
        return jsonify({"msg": "Unauthorized"}), 403

    user = User.query.get(user_id)

    if not user:
        return jsonify({"msg": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "name": user.name,
        "profile_image": user.profile_image
    }), 200


# ================= ADMIN RETURNED ITEMS =================
@app.route("/admin/returned-items", methods=["GET"])
@token_required
def get_returned_items(current_user):

    # 🔒 ADMIN ONLY
    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    returned_lost = LostItem.query.filter_by(status="Returned").all()

    data = []

    for item in returned_lost:
        found_item = FoundItem.query.filter_by(
            matched_lost_item_id=item.id
        ).first()

        owner = User.query.get(item.owner_id)
        finder = User.query.get(found_item.finder_id) if found_item else None

        data.append({
            "lost_id": item.id,
            "item_name": item.item_name,
            "location": item.location,
            "owner_name": owner.name if owner else "Unknown",
            "finder_name": finder.name if finder else "Unknown",
            "image": item.image
        })

    return jsonify(data), 200


# ================= ADMIN STATS =================
@app.route("/admin/stats", methods=["GET"])
@token_required
def admin_stats(current_user):

    # 🔒 ADMIN ONLY
    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    total_lost = LostItem.query.count()
    total_found = FoundItem.query.count()

    matched_items = LostItem.query.filter_by(status="Matched").count()
    returned_items = LostItem.query.filter_by(status="Returned").count()

    return jsonify({
        "total_lost": total_lost,
        "total_found": total_found,
        "matched_items": matched_items,
        "returned_items": returned_items
    }), 200


# ================= TOP FINDERS =================
@app.route("/admin/top-finders")
@token_required
def top_finders(current_user):

    users = User.query.filter_by(role="finder") \
        .order_by(User.total_points.desc()) \
        .limit(3) \
        .all()

    result = []

    for u in users:
        result.append({
            "name": u.name,
            "points": u.total_points,
            "badge": u.badge or "No Badge"
        })

    return jsonify(result), 200


# ================= MATCH ITEM =================
@app.route("/match-item", methods=["POST"])
@token_required
def match_item(current_user):

    # 🔒 ADMIN ONLY
    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    data = request.json

    if not data.get("lost_item_id") or not data.get("found_item_id"):
        return jsonify({"msg": "Missing IDs"}), 400

    lost_item = LostItem.query.get(data["lost_item_id"])
    found_item = FoundItem.query.get(data["found_item_id"])

    if not lost_item or not found_item:
        return jsonify({"msg": "Invalid IDs"}), 404

    # 🔒 prevent duplicate match
    if lost_item.status == "Matched":
        return jsonify({"msg": "Already matched"}), 400

    lost_item.status = "Matched"
    found_item.status = "Matched"
    found_item.is_matched = True
    found_item.matched_lost_item_id = lost_item.id

    # 🔔 notifications
    db.session.add_all([
        Notification(
            user_id=lost_item.owner_id,
            message=f"Your lost item '{lost_item.item_name}' has been matched!"
        ),
        Notification(
            user_id=found_item.finder_id,
            message=f"You successfully matched '{found_item.item_name}'"
        )
    ])

    db.session.commit()

    return jsonify({"msg": "Items matched & notifications sent"}), 200


# ================= QR VIEW =================
@app.route("/qr/<int:item_id>")
def view_qr(item_id):

    item = LostItem.query.get(item_id)

    if not item:
        return "Invalid QR", 404

    owner = User.query.get(item.owner_id)

    # 🔒 HIDE EMAIL (privacy fix)
    return f"""
    <h2>🔍 Lost Item Found</h2>
    <p><b>Item:</b> {item.item_name}</p>
    <p><b>Description:</b> {item.description}</p>
    <hr>
    <h3>👤 Owner Details</h3>
    <p><b>Name:</b> {owner.name}</p>
    <p style='color:green'>Please contact via app 🙏</p>
    """

# ================= NOTIFICATIONS =================
@app.route("/notifications")
@token_required
def get_notifications(current_user):

    notes = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()

    return jsonify([
        {
            "message": n.message,
            "time": n.created_at.strftime("%Y-%m-%d %H:%M")
        } for n in notes
    ])


# ================= REQUEST CHAT =================
@app.route("/request-chat", methods=["POST"])
@token_required
def request_chat(current_user):

    try:
        data = request.get_json()
        lost_item_id = data.get("lost_item_id")

        if not lost_item_id:
            return jsonify({"msg": "Lost item ID missing"}), 400

        item = LostItem.query.get(lost_item_id)

        if not item:
            return jsonify({"msg": "Lost item not found"}), 404

        # 🔒 ONLY OWNER CAN REQUEST CHAT
        if item.owner_id != current_user.id:
            return jsonify({"msg": "Unauthorized"}), 403

        # 🔒 prevent duplicate request
        if item.chat_requested:
            return jsonify({"msg": "Chat already requested"}), 409

        item.chat_requested = True

        # 🔔 notify admin (id=1)
        db.session.add(Notification(
            user_id=1,
            message=f"Chat request for lost item: {item.item_name}"
        ))

        db.session.commit()

        return jsonify({"msg": "Chat request sent to admin"}), 200

    except Exception as e:
        print("REQUEST CHAT ERROR:", e)
        return jsonify({"msg": "Server error"}), 500


# ================= ADMIN APPROVE CHAT =================
@app.route("/admin/approve-chat", methods=["POST"])
@token_required
def admin_approve_chat(current_user):

    # 🔒 ADMIN ONLY
    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    data = request.json
    lost_item_id = data.get("lost_item_id")

    if not lost_item_id:
        return jsonify({"msg": "Lost item ID missing"}), 400

    item = LostItem.query.get(lost_item_id)

    if not item:
        return jsonify({"msg": "Lost item not found"}), 404

    # 🔒 prevent re-approval
    if item.chat_approved:
        return jsonify({"msg": "Already approved"}), 400

    item.chat_approved = True
    item.status = "Chat Approved"

    # 🔔 notify owner
    db.session.add(Notification(
        user_id=item.owner_id,
        message="Chat approved by admin"
    ))

    found = FoundItem.query.filter_by(
        matched_lost_item_id=item.id
    ).first()

    # 🔔 notify finder
    if found:
        db.session.add(Notification(
            user_id=found.finder_id,
            message="Chat approved. You can now chat with owner"
        ))

    db.session.commit()

    return jsonify({"msg": "Chat approved successfully"}), 200

@app.route("/admin/chat-requests", methods=["GET"])
@token_required
def admin_chat_requests(current_user):

    # 🔒 ADMIN ONLY
    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    requests = LostItem.query.filter(
        LostItem.chat_requested == True,
        LostItem.status != "Returned"
    ).all()

    result = []

    for item in requests:
        owner = User.query.get(item.owner_id)

        found = FoundItem.query.filter_by(
            matched_lost_item_id=item.id
        ).first()

        finder = User.query.get(found.finder_id) if found else None

        result.append({
            "lost_item_id": item.id,
            "item_name": item.item_name,
            "owner_name": owner.name if owner else "Unknown",

            # 🔒 EMAIL HIDDEN (privacy fix)
            "finder_name": finder.name if finder else "N/A",

            "chat_approved": item.chat_approved
        })

    return jsonify(result), 200



# ================= JOIN CHAT =================

@socketio.on("join_chat")
def handle_join(data):

    print("JOIN REQUEST:", data)

    user_id = data.get("user_id")
    lost_item_id = data.get("lost_item_id")

    if not user_id or not lost_item_id:
        emit("error", {"msg": "Invalid join data"})
        return

    item = LostItem.query.get(lost_item_id)

    if not item:
        emit("error", {"msg": "Item not found"})
        return

    # ================= FIND MATCHED FINDER =================

    found = FoundItem.query.filter_by(
        matched_lost_item_id=item.id
    ).first()

    # ================= SECURITY CHECK =================

    allowed = (
        int(user_id) == int(item.owner_id)
        or
        (found and int(user_id) == int(found.finder_id))
    )

    if not allowed:
        emit("error", {"msg": "Unauthorized"})
        return

    # ================= JOIN ROOM =================

    room = f"chat_{lost_item_id}"

    join_room(room)

    print(f"USER {user_id} JOINED ROOM {room}")

    # ================= MARK SEEN =================

    Message.query.filter(
        Message.lost_item_id == lost_item_id,
        Message.sender_id != user_id,
        Message.seen == False
    ).update({"seen": True})

    db.session.commit()

    # ================= LOAD CHAT HISTORY =================

    messages = Message.query.filter_by(
        lost_item_id=lost_item_id
    ).order_by(Message.created_at.asc()).all()

    chat_history = []

    for msg in messages:

        chat_history.append({

            "sender_id": msg.sender_id,
            "sender_role": msg.sender_role,
            "message": msg.message,
            "image": msg.image,
            "created_at": msg.created_at.strftime("%H:%M"),
            "seen": msg.seen

        })

    emit("load_messages", chat_history)

    emit("joined", {
        "room": room
    })


# ================= SEND MESSAGE =================

@socketio.on("send_message")
def send_message(data):

    print("MESSAGE RECEIVED:", data)

    try:

        user_id = data.get("sender_id")
        lost_item_id = data.get("lost_item_id")

        if not user_id or not lost_item_id:
            emit("error", {"msg": "Invalid payload"})
            return

        item = LostItem.query.get(lost_item_id)

        if not item:
            emit("error", {"msg": "Item not found"})
            return

        # 🔒 CHAT APPROVED?
        if not item.chat_approved:
            emit("error", {"msg": "Chat not approved"})
            return

        # 🔍 FIND MATCHED FINDER
        found = FoundItem.query.filter_by(
            matched_lost_item_id=item.id
        ).first()

        allowed = (
            int(user_id) == int(item.owner_id)
            or
            (found and int(user_id) == int(found.finder_id))
        )

        if not allowed:
            emit("error", {"msg": "Unauthorized"})
            return

        # 💾 SAVE MESSAGE
        new_message = Message(
            lost_item_id=lost_item_id,
            sender_id=user_id,
            sender_role=data.get("sender_role"),
            message=data.get("message"),
            image=data.get("image"),
            seen=False
        )

        db.session.add(new_message)
        db.session.commit()

        room = f"chat_{lost_item_id}"

        response = {
            "sender_id": new_message.sender_id,
            "sender_role": new_message.sender_role,
            "message": new_message.message,
            "image": new_message.image,
            "created_at": new_message.created_at.strftime("%H:%M"),
            "seen": False
        }

        print("EMITTING TO:", room)

    
        socketio.emit(
            "receive_message",
            response,
            room=room
        )



    except Exception as e:
        print("SEND MESSAGE ERROR:", e)
        emit("error", {"msg": str(e)})

# ================= ADMIN CHAT MONITOR =================

@app.route("/admin/chat-monitor/<int:lost_item_id>")
@token_required
def admin_chat_monitor(current_user, lost_item_id):

    if current_user.role != "admin":
        return jsonify({"msg": "Admin access only"}), 403

    messages = Message.query.filter_by(
        lost_item_id=lost_item_id
    ).order_by(Message.created_at.asc()).all()

    return jsonify([

        {
            "sender": m.sender_role,
            "message": m.message,
            "image": m.image,
            "time": m.created_at.strftime("%Y-%m-%d %H:%M")
        }

        for m in messages

    ])


# ================= CHAT IMAGE UPLOAD =================

@app.route("/upload_chat_image", methods=["POST"])
@token_required
def upload_chat_image(current_user):

    file = request.files.get("image")
    lost_item_id = request.form.get("lost_item_id")

    if not file:
        return jsonify({"msg": "No file uploaded"}), 400

    if not lost_item_id:
        return jsonify({"msg": "Lost item ID missing"}), 400

    # ================= FILE TYPE CHECK =================

    allowed_extensions = ["png", "jpg", "jpeg", "webp"]

    ext = file.filename.split(".")[-1].lower()

    if ext not in allowed_extensions:
        return jsonify({"msg": "Invalid file type"}), 400

    # ================= SAFE FILE NAME =================


    filename = secure_filename(
        f"chat_{current_user.id}_{int(time.time())}.{ext}"
    )

    filepath = os.path.join(
        app.config["CHAT_UPLOAD_FOLDER"],
        filename
    )

    file.save(filepath)

    image_path = f"/static/chat_images/{filename}"

    # ================= RETURN ONLY =================
    # NO DB SAVE HERE
    # send_message socket will save message

    return jsonify({

        "image": image_path,
        "sender_id": current_user.id,
        "created_at": datetime.now().strftime("%H:%M"),
        "seen": False

    })


# ================= ONLINE USERS =================

user_socket_map = {}


# ================= SOCKET CONNECT =================

@socketio.on("connect")
def handle_connect(auth):

    try:

        token = auth.get("token")

        if not token:
            return False

        data = jwt.decode(
            token,
            app.config["SECRET_KEY"],
            algorithms=["HS256"]
        )

        user_id = str(data["user_id"])

        online_users.add(user_id)

        user_socket_map[request.sid] = user_id

        print(f"USER CONNECTED: {user_id}")

        socketio.emit("user_status", {

            "user_id": user_id,
            "online": True

        })

    except Exception as e:

        print("SOCKET CONNECT ERROR:", e)

        return False


# ================= SOCKET DISCONNECT =================

@socketio.on("disconnect")
def handle_disconnect():

    user_id = user_socket_map.get(request.sid)

    if user_id:

        online_users.discard(user_id)

        user_socket_map.pop(request.sid, None)

        print(f"USER DISCONNECTED: {user_id}")

        socketio.emit("user_status", {

            "user_id": user_id,
            "online": False

        })





@app.route("/mark_returned/<int:item_id>", methods=["POST"])
@token_required
def mark_returned(current_user, item_id):

    try:
        lost_item = LostItem.query.get_or_404(item_id)

        # 🔒 OWNER CHECK
        if lost_item.owner_id != current_user.id:
            return jsonify({"msg": "Unauthorized action"}), 403

        if lost_item.status == "Returned":
            return jsonify({"msg": "Item already marked as returned"}), 400

        lost_item.status = "Returned"
        lost_item.chat_approved = False

        found_item = FoundItem.query.filter_by(
            matched_lost_item_id=item_id,
            is_matched=True
        ).first()

        if found_item:
            found_item.status = "Returned"

            reward = Reward(
                finder_id=found_item.finder_id,
                points=50,
                status="approved"
            )
            db.session.add(reward)

            finder = User.query.get(found_item.finder_id)
            if finder:
                finder.total_points += 50
                update_badge(finder)

                db.session.add(Notification(
                    user_id=finder.id,
                    message=f"Item '{lost_item.item_name}' has been returned. You earned 50 points!"
                ))

        db.session.add(Notification(
            user_id=lost_item.owner_id,
            message=f"You marked '{lost_item.item_name}' as successfully returned."
        ))

        db.session.commit()

        return jsonify({
            "msg": "Item marked as returned successfully",
            "status": "Returned"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            "msg": "Something went wrong",
            "error": str(e)
        }), 500


# ================= FEATURE EXTRACTION =================
def extract_features(img_path):

    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)

    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)

    model = get_ai_model()
    features = model.predict(img_array, verbose=0)

    return features.flatten()


def compare_images(img1_path, img2_path):

    features1 = extract_features(img1_path)
    features2 = extract_features(img2_path)

    similarity = cosine_similarity(
        [features1],
        [features2]
    )[0][0]

    return float(similarity)


# ================= CNN SIMILARITY CHECK (PRETRAINED MODEL) =================
@app.route("/admin/check-similarity/<int:found_id>", methods=["GET"])
@token_required
@admin_required
def check_similarity(current_user, found_id):

    found_item = FoundItem.query.get(found_id)
    if not found_item:
        return jsonify({"msg": "Found item not found"}), 404

    if not found_item.image:
        return jsonify({
            "match_found": False,
            "similarity": 0,
            "msg": "Found item has no image"
        })

    found_image_path = os.path.join("static/uploads", found_item.image)
    if not os.path.exists(found_image_path):
        return jsonify({"match_found": False, "similarity": 0, "msg": "Found image file missing"})

    lost_items = LostItem.query.filter(
        LostItem.status.notin_(["Matched", "Returned"])
    ).all()

    best_similarity = 0
    best_match = None

    for lost in lost_items:
        if not lost.image:
            continue

        lost_image_path = os.path.join("static/uploads", lost.image)
        if not os.path.exists(lost_image_path):
            continue

        try:
            similarity = compare_images(found_image_path, lost_image_path)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = lost

        except Exception as e:
            print("Similarity Error:", e)

    THRESHOLD = 0.70

    if best_match and best_similarity >= THRESHOLD:
        return jsonify({
            "match_found": True,
            "found_item_id": found_item.id,
            "lost_item_id": best_match.id,
            "lost_item_name": best_match.item_name,
            "similarity": float(best_similarity)
        })

    return jsonify({
        "match_found": False,
        "found_item_id": found_item.id,
        "lost_item_id": best_match.id if best_match else None,
        "lost_item_name": best_match.item_name if best_match else None,
        "similarity": float(best_similarity)
    })


@app.route("/admin/compare-images", methods=["POST"])
@token_required
@admin_required
def compare_item_images(current_user):

    data = request.json

    if not data.get("lost_item_id") or not data.get("found_item_id"):
        return jsonify({"msg": "Missing item IDs"}), 400

    lost_item = LostItem.query.get(data["lost_item_id"])
    found_item = FoundItem.query.get(data["found_item_id"])

    if not lost_item or not found_item:
        return jsonify({"msg": "Invalid items"}), 404

    if not lost_item.image or not found_item.image:
        return jsonify({"msg": "One of the items has no image"}), 400

    lost_image_path = os.path.join("static/uploads", lost_item.image)
    found_image_path = os.path.join("static/uploads", found_item.image)

    if not os.path.exists(lost_image_path) or not os.path.exists(found_image_path):
        return jsonify({"msg": "One of the image files is missing"}), 400

    similarity = compare_images(lost_image_path, found_image_path)

    THRESHOLD = 0.70

    if similarity >= 0.80:
        label = "Very Strong Match 🔥"
    elif similarity >= 0.70:
        label = "Strong Match ✅"
    elif similarity >= 0.50:
        label = "Possible Match ⚠"
    else:
        label = "Low Match ❌"

    return jsonify({
        "match_found": similarity >= THRESHOLD,
        "lost_item_id": lost_item.id,
        "lost_item_name": lost_item.item_name,
        "lost_item_owner_id": lost_item.owner_id,
        "found_item_id": found_item.id,
        "similarity": round(float(similarity) * 100, 2),
        "result": label
    })


def update_badge(user):
    points = user.total_points or 0

    if points >= 300:
        user.badge = "gold"
    elif points >= 150:
        user.badge = "silver"
    elif points > 0:
        user.badge = "bronze"
    else:
        user.badge = "none"

# ================= ADMIN AUTO CREATE =================
# ================= ADMIN AUTO CREATE =================
def create_admin():
    with app.app_context():
        db.create_all()

        admin_email = "admin@lostfound.com"

        if not User.query.filter_by(email=admin_email).first():
            admin = User(
                name="Admin",
                email=admin_email,
                role="admin"
            )

            # 🔐 Strong password (change if needed)
            admin.set_password(os.getenv("ADMIN_PASSWORD", "Admin@1234"))


            db.session.add(admin)
            db.session.commit()

            print("[SUCCESS] Admin created successfully")
        else:
            print("[INFO] Admin already exists")


create_admin()


# ================= RUN APP =================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=os.getenv("FLASK_DEBUG", "False").lower() == "true",
        allow_unsafe_werkzeug=True
    )

