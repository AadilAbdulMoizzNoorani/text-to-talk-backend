from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from gridfs import GridFS
import os
from dotenv import load_dotenv

# Load env
load_dotenv()

# Custom imports
from auth import register_user, login_user, get_profile, edit_profile, logout_user, bcrypt
from ai_service import api, get_history, delete_single_history, delete_multiple_history, delete_all_history

app = Flask(__name__)
CORS(app)

# JWT
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-key")
jwt = JWTManager(app)
bcrypt.init_app(app)

# MongoDB setup
MONGO_URI = os.getenv("MONGO_DB")
DB_NAME = os.getenv("DB_NAME")
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
fs = GridFS(db)

# ---------------------- ROUTES ----------------------

@app.route("/")
def home():
    return "Hello, API is running!"

# -------- Auth Routes --------
@app.route("/auth/register", methods=["POST"])
def register():
    data = request.json
    return register_user(
        data["firstname"], 
        data["lastname"], 
        data["email"], 
        data["password"]
    )

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.json
    return login_user(data["email"], data["password"])

@app.route("/auth/profile", methods=["GET"])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    return get_profile(user_id)

@app.route("/auth/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    data = request.json
    return edit_profile(user_id, data)

# -------- Chat Route (MongoDB GridFS) --------
@app.route("/chat/", methods=["POST"])
def appi_post():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio = request.files["audio"]
    filename = secure_filename(audio.filename)

    # Save to MongoDB GridFS
    file_id = fs.put(audio, filename=filename)

    # GridFS file reference
    file_path = {"file_id": str(file_id), "filename": filename}

    try:
        result = api(file_path)  # ai_service ke liye same, bas file_id pass hoga
        return jsonify({"response": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- History Routes --------
@app.route("/history", methods=['GET'])
def history_route():
    u_id = request.args.get("user_id")
    return get_history(u_id)

@app.route("/delete-history", methods=['DELETE'])
def del_history_route():
    h_id = request.args.get("history_id")
    return delete_single_history(h_id)

@app.route("/delete/all/history", methods=['DELETE'])
def del_all_history_route():
    user_id = request.args.get("user_id")
    return delete_all_history(user_id)

@app.route("/delete/select/history", methods=['POST'])
def del_select_history_route():
    data = request.get_json()
    history_ids = data.get("history_ids", [])
    if not history_ids:
        return jsonify({"message": "no history IDs provided"}), 400
    result = delete_multiple_history(history_ids)
    return jsonify({"message": result})

@app.route("/logout", methods=["POST"])
@jwt_required()
def logout_route():
    return logout_user()

# ---- Serverless compatible: no app.run() ----
