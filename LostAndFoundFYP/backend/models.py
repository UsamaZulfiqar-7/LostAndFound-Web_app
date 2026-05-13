from datetime import datetime
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash


# ================= USER =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    # 🔥 NEW FIELDS FOR GAMIFICATION
    total_points = db.Column(db.Integer, default=0)
    badge = db.Column(db.String(50), default="No Badge")

    profile_image = db.Column(db.String(255), nullable=True) 

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    rewards = db.relationship("Reward", backref="finder", lazy=True)
    notifications = db.relationship("Notification", backref="user", lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


# ================= LOST ITEM =================
class LostItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    item_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    location = db.Column(db.String(100), nullable=False)  # coords
    location_name = db.Column(db.Text)  # 🔥 ADDED (readable address)

    status = db.Column(db.String(20), default="Lost")

    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    qr_code = db.Column(db.String(200))

    image = db.Column(db.String(255), nullable=True)

    chat_requested = db.Column(db.Boolean, default=False)
    chat_approved = db.Column(db.Boolean, default=False)

    # Relationships
    owner = db.relationship("User", backref="lost_items", lazy=True)
    found_item = db.relationship("FoundItem", backref="lost_item", uselist=False, lazy=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= FOUND ITEM =================
class FoundItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    item_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)

    location = db.Column(db.String(100), nullable=False)  # coords
    location_name = db.Column(db.Text)  # 🔥 ADDED (readable address)

    status = db.Column(db.String(20), default="Found")

    finder_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    image = db.Column(db.String(255), nullable=True)

    # AI / MATCHING
    ai_label = db.Column(db.String(100))

    # 🔥 FIXED FK (better practice)
    matched_lost_item_id = db.Column(db.Integer, db.ForeignKey("lost_item.id"))

    is_matched = db.Column(db.Boolean, default=False)

    # Relationships
    finder = db.relationship("User", backref="found_items", lazy=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= REWARD =================
class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    finder_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    points = db.Column(db.Integer)
    status = db.Column(db.String(20), default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= NOTIFICATION =================
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    message = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= CHAT MESSAGE =================
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    lost_item_id = db.Column(db.Integer, db.ForeignKey('lost_item.id'))

    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sender_role = db.Column(db.String(20))  # owner / finder

    message = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    seen = db.Column(db.Boolean, default=False)
