from flask import Flask, request, jsonify, render_template_string

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

from youtubesearchpython import VideosSearch
import google.generativeai as genai
import webbrowser
import os
import requests
from datetime import datetime, timedelta

from dotenv import load_dotenv


import os
from dotenv import load_dotenv

import json

CACHE_FILE = "summary_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

cache = load_cache()



# Load .env file
load_dotenv()

# Check environment variable
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise ValueError("❌ GOOGLE_API_KEY is not loading from .env")

print("✅ API key loaded:", api_key[:6] + "..." + api_key[-4:])

# Configure genai
genai.configure(api_key=api_key)
print("✅ genai configured successfully")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


print("RAILWAY ENV PORT =", os.environ.get("PORT"))

app = Flask(__name__)


# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 5000))
#     print(f"Starting Flask on port {port}")
#     app.run(host="0.0.0.0", port=port)



HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hot Off the Press</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>

</head>
<body>
    <div class="container">
    <h2>Hot Off the Press</h2>



    <form id="actionForm" action="/" method="post">
        <input type="hidden" name="action" value="generate_action_items">
        <input type="hidden" name="summaries_text" value="{{ summaries_text | e }}">
        <button id="actionButton" type="submit" style="
        padding: 12px 18px;
        font-size: 16px;
        border-radius: 6px;
        cursor: pointer;
        ">Action Items</button>
    </form>

    <script>
    const button = document.getElementById("actionButton");
    const form = document.getElementById("actionForm");

    // Check if user already clicked it before
    if (localStorage.getItem("actionUsed") === "true") {
        button.disabled = true;
        button.textContent = "Already generated";
    }

    form.addEventListener("submit", function (e) {
        // If it's already used, prevent submission
        if (localStorage.getItem("actionUsed") === "true") {
        e.preventDefault();
        return;
        }

        // Set localStorage flag to lock it down
        localStorage.setItem("actionUsed", "true");
        button.disabled = true;
        button.textContent = "Generating...";
    });
    </script>




        {% if action_items %}
        <div style="margin-top: 1em; padding: 1em; border: 1px solid #ccc; background: #f9f9f9;">
            <h3>📝 Action Items:</h3>
            <p>{{ action_items }}</p>
        </div>
        {% endif %}

    <div id="chat-wrapper">
    <div id="chat-log" style="display: flex; flex-direction: column;"></div>
    </div>



    <textarea id="chat-input" placeholder="Ask..." rows="4" style="width: 100%; padding: 8px;"></textarea>


    <script>
    const chatLog = document.getElementById("chat-log");
    const chatInput = document.getElementById("chat-input");

    // Load stored messages
    const storedChat = JSON.parse(localStorage.getItem("chatHistory") || "[]");
    storedChat.forEach(msg => addMessage(msg.role, msg.content));

    function addMessage(role, content) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `chat-msg ${role === "user" ? "user-msg" : "assistant-msg"}`;
        msgDiv.innerHTML = marked.parse(content);  // 👈 Use markdown rendering
        chatLog.appendChild(msgDiv);
        chatLog.scrollTop = chatLog.scrollHeight;
    }


    async function sendToServer(message) {
        const formData = new FormData();
        formData.append("action", "chat_message");
        formData.append("chat_input", message);

        const res = await fetch("/", {
            method: "POST",
            body: formData
        });

        const text = await res.text();
        const parser = new DOMParser();
        const htmlDoc = parser.parseFromString(text, 'text/html');

        const responseEl = htmlDoc.querySelector("#chat-response");
        return responseEl ? responseEl.textContent.trim() : "⚠️ No response";
    }


    chatInput.addEventListener("keydown", async (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const msg = chatInput.value.trim();
        if (!msg) return;

        addMessage("user", msg);
        chatInput.value = "";

        const history = JSON.parse(localStorage.getItem("chatHistory") || "[]");
        history.push({ role: "user", content: msg });
        localStorage.setItem("chatHistory", JSON.stringify(history));

        const reply = await sendToServer(msg);
        addMessage("assistant", reply);
        history.push({ role: "assistant", content: reply });
        localStorage.setItem("chatHistory", JSON.stringify(history));
    }
    });

    document.addEventListener("DOMContentLoaded", () => {
    const resetBtn = document.getElementById("reset-chat");
    if (resetBtn) {
        resetBtn.addEventListener("click", () => {
        localStorage.removeItem("chatHistory");
        document.getElementById("chat-log").innerHTML = "";
        document.getElementById("chat-input").value = "";
        });
    }
    });


    </script>
    <button id="reset-chat" style="
    margin-top: 10px;
    padding: 12px 18px;
    font-size: 16px;
    border-radius: 6px;
    cursor: pointer;
    ">🧹 Reset Chat</button>

        

        <hr>
        <h2>News Watcher</h2>
        {% if videos %}
        <ul>
            {% for video in videos %}
                <li>
                    <strong>{{ video['title'] }}</strong> — <a href="{{ video['link'] }}" target="_blank">Watch</a>
                    {% if video['summary'] %}
                        <p><em>{{ video['summary'] }}</em></p>
                    {% elif video['error'] %}
                        <p style="color: red;"><strong>Error:</strong> {{ video['error'] }}</p>
                    {% endif %}
                </li>
            {% endfor %}
        </ul>
        {% endif %}
    </div>


    <!-- Hidden chat response to parse in JS -->
    <div id="chat-response" style="display: none;">{{ chat_response | safe }}</div>

</body>
</html>
"""


def clean_transcript(transcript):
    cleaned_lines = []
    seen_lines = set()

    for line in transcript:
        if isinstance(line, dict):
            text = line.get('text', '')
        else:
            text = getattr(line, 'text', '')

        if not text or text in seen_lines:
            continue
        seen_lines.add(text)

        cleaned_lines.append(text)

    return "\n".join(cleaned_lines)


def generate_summary(text):
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            f"""Summarize in detail (2 sentences):\n{text}""",
            generation_config=genai.types.GenerationConfig(max_output_tokens=500)
        )
        return response.text.strip()
    except Exception as e:
        return f"Error generating summary: {e}"

def search_youtube_videos(query="msnbc trump musk"):
    now = datetime.utcnow()
    yesterday = now - timedelta(days=2)
    published_after = yesterday.isoformat("T") + "Z"
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "maxResults": 5,
        "key": YOUTUBE_API_KEY
    }
    res = requests.get(url, params=params)
    res.raise_for_status()
    data = res.json()
    videos = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        import html
        title = html.unescape(item["snippet"]["title"])
        link = f"https://www.youtube.com/watch?v={video_id}"
        videos.append({"title": title, "link": link})
    return videos


# def search_youtube_videos(query="msnbc trump musk"):
#     return [
#         {"title": "House Democrats Say Trump Must Fire Musk in 50 Days", "link": "Sm_tCsKNrag"},
#         {"title": "Peter Navarro Says Tariffs are the Only Defense", "link": "aeM8v_idbg0"},
#     ]



@app.route('/', methods=['GET', 'POST'])
def home():

    summaries_text = ""
    action_items_text = None
    videos_data = []
    videos = search_youtube_videos()
    chat_response_text = None

    if request.method == "GET":
        for video in videos:
            try:
                raw_link = video.get("link", "")
                print(f"🔍 Processing video: {raw_link}")

                # Support both full URLs and raw video IDs
                if "watch?v=" in raw_link:
                    video_id = raw_link.split("watch?v=")[-1].split("&")[0]
                elif "youtu.be/" in raw_link:
                    video_id = raw_link.split("youtu.be/")[-1].split("?")[0]
                else:
                    video_id = raw_link  # assume it's just a video ID

                print(f"🎬 Extracted video ID: {video_id}")

                if video_id in cache:
                    summary = cache[video_id]
                else:
                    # Safely try fetching transcript
                    transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                    transcript_obj = transcripts.find_transcript([
                        "en", "ko", "fr", "es", "zh", "zh-Hans", "zh-Hant", "ja"
                    ])
                    raw_transcript = transcript_obj.fetch()
                    transcript_text = clean_transcript(raw_transcript)
                    summary = generate_summary(transcript_text)
                    cache[video_id] = summary
                    save_cache(cache)

                summaries_text += summary + "\n\n"
                videos_data.append({**video, "summary": summary})

            except TranscriptsDisabled:
                print(f"⚠️ Transcripts disabled for {raw_link}")
                videos_data.append({**video, "summary": None, "error": "Transcripts are disabled."})

            except Exception as e:
                print(f"❌ Error processing {raw_link}: {e}")
                videos_data.append({**video, "summary": None, "error": str(e)})




    elif request.method == "POST":
        action = request.form.get("action")
        summaries_text = request.form.get("summaries_text", "")  # <- crucial
        raw_summaries = summaries_text

        if action == "generate_action_items":
            try:
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(
                    f"""These are summaries of 5 recent news videos:\n{raw_summaries}\n\n
                    Please synthesize the themes into a cohesive summary, and suggest 1–2 things a regular U.S. citizen should begin to consider or take action on (in two sentences). Respond as a thoughtful advisor, no more than 4 sentences. """,
                    generation_config=genai.types.GenerationConfig(max_output_tokens=500)
                )
                action_items_text = response.text.strip()
            except Exception as e:
                action_items_text = f"Error generating action items: {e}"

        
        elif action == "chat_message":
            chat_input = request.form.get("chat_input", "")
            if chat_input.strip():
                try:
                    model = genai.GenerativeModel("gemini-2.0-flash")
                    response = model.generate_content(chat_input)
                    chat_response_text = response.text.strip()
                except Exception as e:
                    chat_response_text = f"Error: {e}"

        # Repopulate video bullets (from cache only)
        for video in videos:
            video_id = video["link"].split("watch?v=")[-1].split("&")[0]
            summary = cache.get(video_id, None)
            videos_data.append({**video, "summary": summary})

    return render_template_string(
        HTML_TEMPLATE,
        videos=videos_data,
        summary=None,
        transcript=None,
        error=None,
        summaries_text=summaries_text,
        action_items=action_items_text,
        chat_response=chat_response_text
    )


# Connect to ngrok with reserved username




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway uses 8080 in your case
    print(f"🚀 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)

