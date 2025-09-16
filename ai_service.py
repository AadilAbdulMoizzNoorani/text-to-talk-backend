import google.generativeai as genai
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from pymongo import MongoClient
from bson.objectid import ObjectId
from gridfs import GridFS
import datetime
from dotenv import load_dotenv
import os
from flask import jsonify
import requests
import time

from auth import check_login

bcrypt = Bcrypt()
load_dotenv()

# -----------------------------
# MongoDB + GridFS Setup
# -----------------------------
client = MongoClient(os.getenv('MONGO_DB'))
db = client[os.getenv('DB_NAME')]
history = db["history"]
fs = GridFS(db)  # GridFS object

# -----------------------------
# Gemini AI Setup
# -----------------------------
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# -----------------------------
# AssemblyAI API Key
# -----------------------------
ASSEMBLY_API_KEY = os.getenv("ASSEMBLY_API_KEY") or "3674a77753904f9f91f05d1fc731aa55"

# -----------------------------
# SAVE HISTORY
# -----------------------------
def save_history(res):
    login_status = check_login()
    title_prompt = f"""
        Read the following summary and generate a short professional title (max 10 words).
        It should look like a meeting note headline.

        Summary:
        {res}
    """
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))
    title_res = model.generate_content(
        [title_prompt],
        generation_config=genai.types.GenerationConfig(
            temperature=0.5,
            max_output_tokens=5000,
        )
    )
    title_text = title_res.text.strip()
    user_data = login_status.get_json()

    if user_data.get("logged_in"):
        user_id = user_data.get("user_id")
        history.insert_one({
            "user_id": user_id,
            "title": title_text,
            "history": res.text,
            "created_at": datetime.datetime.utcnow()
        })
        return {"message": "history saved", "title": title_text, "resp": res.text}
    else:
        return {"response": res.text}

# -----------------------------
# API FUNCTION (AssemblyAI + Gemini)
# -----------------------------
def api(file_ref):
    """
    file_ref: str (local path) ya dict (MongoDB GridFS)
    """
    # 1️⃣ Read audio bytes
    if isinstance(file_ref, dict):
        # GridFS se audio read karo
        file_id = ObjectId(file_ref["file_id"])
        audio_bytes = fs.get(file_id).read()
    else:
        # Local file path
        with open(file_ref, "rb") as f:
            audio_bytes = f.read()

    # 2️⃣ Upload to AssemblyAI
    headers = {"authorization": ASSEMBLY_API_KEY}
    upload_res = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers=headers,
        data=audio_bytes
    )
    upload_res.raise_for_status()
    audio_url = upload_res.json()["upload_url"]

    # 3️⃣ Start transcription
    transcript_req = {"audio_url": audio_url}
    transcript_res = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json=transcript_req,
        headers=headers
    )
    transcript_res.raise_for_status()
    transcript_id = transcript_res.json()["id"]

    # 4️⃣ Poll for transcription result
    transcript_text = None
    while True:
        poll_res = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
            headers=headers
        )
        poll_res.raise_for_status()
        status = poll_res.json()["status"]
        if status == "completed":
            transcript_text = poll_res.json()["text"]
            break
        elif status == "error":
            return {"error": "Transcription failed", "details": poll_res.json()}
        time.sleep(3)

    # 5️⃣ Send transcript to Gemini AI
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))
    prompt = f"""
You are an expert AI assistant specialized in analyzing meeting recordings, audio discussions, and video content. 
Your job is to take an audio/video transcript and provide a structured, clear, and professional response in ENGLISH ONLY. 
Do NOT use any other language. 
Always keep formatting consistent with headings and bullet points. 
Follow the structure below strictly:

====================================================================
1. Abstract Summary
2. Key Points
3. Action Items
4. Sentiment Analysis
5. Proper Transcript

TRANSCRIPT:

"""

    res = model.generate_content(
        [prompt, f"This is transcript content: {transcript_text}"],
        generation_config=genai.types.GenerationConfig(
            temperature=1,
        )
    )

    # 6️⃣ Save history
    return save_history(res)

# -----------------------------
# HISTORY MANAGEMENT FUNCTIONS
# -----------------------------
def delete_single_history(history_id):
    history_data = history.find_one({"_id": ObjectId(history_id)})
    if history_data:
        history.delete_one({"_id": ObjectId(history_id)})
        return "history deleted"
    else:
        return {"id": history_id}

def get_history(user_id):
    history_Data = history.find({"user_id": user_id})
    if history_Data:
        record = []
        for records in history_Data:
            records["_id"] = str(records["_id"])
            record.append(records)
        return {"history_record": record}
    else:
        return "Sorry! No record Available"

def delete_all_history(user_id):
    result = history.delete_many({"user_id": user_id})
    if result.deleted_count > 0:
        return f"{result.deleted_count} history entries deleted"
    else:
        return "no history found of user"

def delete_multiple_history(history_ids):
    obj_ids = [ObjectId(h_id) for h_id in history_ids]
    result = history.delete_many({"_id": {"$in": obj_ids}})
    if result.deleted_count > 0:
        return f"{result.deleted_count} history entries deleted"
    else:
        return "no history found for the selected entries"
