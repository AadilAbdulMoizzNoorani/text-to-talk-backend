from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
import tempfile
from dotenv import load_dotenv
import os
# Auth functions (auth.py me define karna)
from auth import register_user, login_user, get_profile, edit_profile,logout_user, bcrypt
# AI Service
from ai_service import api,get_history,delete_single_history,delete_multiple_history,delete_all_history
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # sab origins allow

# JWT secret key (production me env variable use karo)
app.config["JWT_SECRET_KEY"] = "super-secret-key"

# Init JWT + Bcrypt
jwt = JWTManager(app)
bcrypt.init_app(app)


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


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/chat/", methods=["POST"])
def appi_post():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio = request.files["audio"]
    filename = secure_filename(audio.filename)
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    audio.save(save_path)  # File permanent folder mein save ho gayi

    try:
        result = api(save_path)  # Ab AI ko ye path send karo
        return jsonify({"response": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
@app.route("/history", methods=['GET'])
def history() :
    u_id = request.args.get("user_id")
    return get_history(u_id)
@app.route("/delete-history", methods=['DELETE'])
def del_history() :
    h_id = request.args.get("history_id")
    return delete_single_history(h_id)

@app.route("/delete/all/history", methods=['DELETE'])
def del_all_history() :
    user_id = request.args.get("user_id")
    return delete_all_history(user_id)
@app.route("/delete/select/history", methods=['POST'])
def del_select_history() :
    data = request.get_json()
    history_ids = data.get("history_ids", [])  # frontend se ye array bhejna

    if not history_ids:
        return jsonify({"message": "no history IDs provided"}), 400

    result = delete_multiple_history(history_ids)
    return jsonify({"message": result})
@app.route("/logout", methods=["POST"])
@jwt_required()
def logout_route():
    return logout_user()

if __name__ == "__main__":
    app.run(debug=True)
