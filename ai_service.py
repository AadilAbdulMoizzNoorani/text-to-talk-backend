import google.generativeai as genai
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime
from dotenv import load_dotenv
import os
from flask import jsonify
import requests
import time

from auth import check_login
bcrypt = Bcrypt()

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
client = MongoClient(os.getenv('MONGO_DB'))

db = client[os.getenv('DB_NAME')]
history = db["history"]

ASSEMBLY_API_KEY = "3674a77753904f9f91f05d1fc731aa55"  # AssemblyAI Key

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
            "history": res,
            "created_at": datetime.datetime.utcnow()
        })
        return {"message": "history saved", "title": title_text, "resp": res}
    else:
        return {"response": res}

# -----------------------------
# API FUNCTION (AssemblyAI + Gemini)
# -----------------------------
def api(file_path: str):
    import math

    # 1️⃣ Upload audio to AssemblyAI
    headers = {"authorization": ASSEMBLY_API_KEY}

    with open(file_path, "rb") as f:
        upload_res = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=f
        )
    upload_res.raise_for_status()
    audio_url = upload_res.json()["upload_url"]

    # 2️⃣ Start transcription
    transcript_req = {"audio_url": audio_url}
    transcript_res = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json=transcript_req,
        headers=headers
    )
    transcript_res.raise_for_status()
    transcript_id = transcript_res.json()["id"]

    # 3️⃣ Poll for transcription result
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

    # 4️⃣ Split transcript into chunks (e.g., 6000 characters per chunk)
    def chunk_text(text, chunk_size=6000):
        for i in range(0, len(text), chunk_size):
            yield text[i:i+chunk_size]

    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))

    prompt = """
You are an expert AI assistant specialized in analyzing meeting recordings, audio discussions, and video content.
Follow the structure below strictly (Abstract Summary, Key Points, Action Items, Sentiment Analysis, Proper Transcript).
Always answer in ENGLISH ONLY.
"""

    # 5️⃣ Process chunks one by one
    final_response_parts = []
    for i, chunk in enumerate(chunk_text(transcript_text)):
        res = model.generate_content(
            [prompt, f"PART {i+1}: {chunk}"],
            generation_config=genai.types.GenerationConfig(
                temperature=1,
            )
        )
        final_response_parts.append(res.text)

    # 6️⃣ Combine all chunk results
    combined_response = "\n\n".join(final_response_parts)

    # 7️⃣ Save history / return combined result
    return save_history(combined_response)

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
