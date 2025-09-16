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
            "history": res.text,
            "created_at": datetime.datetime.utcnow()
        })
        return {"message": "history saved", "title": title_text, "resp": res.text}
    else:
        return {"response": res.text}

# -----------------------------
# API FUNCTION (AssemblyAI + Gemini)
# -----------------------------
def api(file_path: str):
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

    # 4️⃣ Send ONLY transcript text to Gemini
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL"))

    prompt = f"""
You are an expert AI assistant specialized in analyzing meeting recordings, audio discussions, and video content. 
Your job is to take an audio/video transcript and provide a structured, clear, and professional response in ENGLISH ONLY. 
Do NOT use any other language. 
Always keep formatting consistent with headings and bullet points. 
Follow the structure below very strictly:

====================================================================
1. Abstract Summary
   - Provide a short overview (3–5 sentences) of the entire transcript.
   - Keep it professional and concise.
   - Avoid repetition. Focus on the purpose and main discussion.

2. Key Points
   - Extract the most important points from the transcript.
   - Present them in clear bullet points.
   - Each point should be precise, capturing essential details.
   - Do not add unnecessary details, only the key information.
   - Use numbered format (1, 2, 3, …).

3. Action Items
   - List clear, concise, and actionable tasks derived from the discussion.
   - Use numbered format (1, 2, 3, …).
   - Each action should be written as a direct instruction.
   - Make sure action items are practical and easy to follow.

4. Sentiment Analysis
   - Identify the overall sentiment of the discussion: Positive, Neutral, or Negative.
   - Briefly explain WHY you selected that sentiment (1–2 lines).
   - Keep explanation factual and objective, not opinionated.

5. Proper Transcript
   - Provide the cleaned, readable version of the transcript.
   - Remove filler words (uh, um, like, you know).
   - Ensure proper grammar, punctuation, and readability.
   - Keep original meaning intact, but make it professional.

====================================================================
Rules:
- Response MUST always follow the above format.
- Never skip a section, even if content is missing.
- Always keep the output well-formatted with headings and spacing.
- Output should look neat and professional, similar to a business meeting summary.
- Always respond in ENGLISH ONLY. Never use any other language under any circumstances.


TRANSCRIPT:

"""

    res = model.generate_content(
        [prompt, f"This is transcript content: {transcript_text}"],
        generation_config=genai.types.GenerationConfig(
            temperature=1,
        )
    )

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