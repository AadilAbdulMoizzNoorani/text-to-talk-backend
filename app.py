from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import os

# Load env
load_dotenv()

# Custom imports
from auth import register_user, login_user, get_profile, edit_profile, logout_user, bcrypt
from ai_service import api,save_history,get_history, delete_single_history, delete_multiple_history, delete_all_history

app = Flask(__name__)
CORS(app)  # Sab origins allow

# JWT secret key (production me env variable use karo)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-key")

# Init JWT + Bcrypt
jwt = JWTManager(app)
bcrypt.init_app(app)

@app.route("/")
def home():
    return "Hello, API is running!"
    
@app.route("/save-history",methods=['POST'])
def store_history():
    req_data = request.get_json()
    message = req_data.get("req") or req_data.get("message")
    return save_history(message)

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

# -------- Chat Route (Serverless Friendly) --------
@app.route("/chat/", methods=["POST"])
def appi_post():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio = request.files["audio"]

    try:
        # Pass audio bytes directly to API
        result = api(audio.read())  
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
