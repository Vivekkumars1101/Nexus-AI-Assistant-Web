import streamlit as st
import os
import json
import re
import webbrowser
import pywhatkit
import datetime
import threading
from pathlib import Path
from PIL import Image
from io import BytesIO

# --- API & LIBRARY IMPORTS ---
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- CRITICAL FIX: Load .env file at startup ---
load_dotenv() 

# --- 0. Configuration and Memory Setup ---

MEMORY_FILE = Path("assistant_memory.json")

def load_memory():
    """Loads long-term memory notes from the JSON file."""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: Memory file is corrupted, starting with empty long-term memory.")
            return []
    return []

def save_memory(notes):
    """Saves the current list of long-term notes to the JSON file."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(notes, f, indent=4)

# Global memory storage
PERSONAL_NOTES = load_memory()


# --- 1. Global Tool Setup and Definitions ---

def tool_output(text):
    """Prints tool execution text to the console/log for debugging."""
    print(f"[TOOL LOG] {text}")
    return text

AVAILABLE_TOOLS = {}
def add_tool(func):
    """Decorator to automatically add functions to the AVAILABLE_TOOLS map."""
    AVAILABLE_TOOLS[func.__name__] = func
    return func

# Standard Web/Time Tools
@add_tool
def web_search(query: str):
    """Searches the web using Google and opens the default browser to the search results."""
    tool_output(f"Opening web search for: {query}")
    try:
        webbrowser.open_new_tab(f"https://www.google.com/search?q={query}")
        return f"I have opened a web search for '{query}' in a new tab."
    except Exception as e:
        return f"Error simulating web search: {e}"

@add_tool
def play_on_youtube(topic: str):
    """Opens YouTube and searches for the video topic."""
    tool_output(f"Switching to direct YouTube search for: {topic}")
    
    search_query = f"{topic} song" 
    url = f"https://www.youtube.com/results?search_query={search_query}"
    
    try:
        webbrowser.open_new_tab(url)
        return f"I have successfully searched for '{topic}' on YouTube and opened the results in a new tab for you, VIVEK."
    except Exception as e:
        return f"I encountered an error trying to open YouTube. Details: {e}"

@add_tool
def check_current_time():
    """Returns the current local time."""
    now = datetime.datetime.now().strftime("%I:%M %p")
    return f"The current time is {now}"

# Memory Tools
@add_tool
def add_personal_note(note_text: str):
    """Saves a piece of personal information or a key preference for later retrieval."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PERSONAL_NOTES.append({'time': timestamp, 'note': note_text})
    save_memory(PERSONAL_NOTES)
    return f"Note successfully saved: '{note_text}'."

@add_tool
def retrieve_personal_notes(query: str):
    """Returns all stored personal notes for the AI to process."""
    if not PERSONAL_NOTES:
        return "I have no personal notes saved yet."
    note_strings = [f"Time: {n['time']}, Note: {n['note']}" for n in PERSONAL_NOTES]
    return "The user's stored notes are:\n" + "\n".join(note_strings)

# Utility Tools
@add_tool
def open_application(app_name: str):
    """Simulates the command to open an application."""
    tool_output(f"Simulating launch of application: {app_name}")
    return f"I have sent the command to launch the application '{app_name}'. (Note: This is simulated in the web environment.)"

@add_tool
def set_reminder(time_string: str, reminder_text: str):
    """Simulates setting a reminder."""
    tool_output(f"Simulating reminder set for {time_string}.")
    return f"I have set a reminder for '{reminder_text}' in {time_string}. I will notify you then. (Note: Notification is simulated.)"


# --- 2. STREAMLIT STATE AND CLIENT INITIALIZATION ---

st.set_page_config(page_title="Nexus AI Web Assistant", layout="centered")
st.title("🧠 Nexus AI Web Assistant")

# --- API KEY & CLIENT INITIALIZATION ---
if "GEMINI_API_KEY" not in os.environ:
     st.error("FATAL ERROR: GEMINI_API_KEY environment variable not set. Please set your key.")
     st.stop()

try:
    client = genai.Client()
except Exception as e:
    st.error(f"Failed to initialize Gemini Client: {e}")
    st.stop()


if "chat_session" not in st.session_state:
    
    tool_list = list(AVAILABLE_TOOLS.values())
    
    tool_config = types.GenerateContentConfig(
        tools=tool_list,
        # *** System Instruction refined to prioritize internal knowledge ***
        system_instruction="You are a dedicated, witty, and highly capable personal AI assistant named 'Nexus'. Your name is NEXUS.AI and the user's name is VIVEK. **Only use the web_search tool for requests requiring current, real-time data (like news or stock prices), or for opening a specific website/video. For general knowledge and definitions (like 'what is RAM'), answer using your internal knowledge base directly.** You process image requests if a file is uploaded, and use tools to perform actions. Keep responses concise and professional."
    )

    st.session_state.chat_session = client.chats.create(
        model='gemini-2.5-flash', 
        config=tool_config
    )
    st.session_state.messages = []


def handle_multimodal_request(image_data, prompt):
    """Handles multimodal requests directly by sending image and prompt."""
    
    contents = [image_data, prompt]
    
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=contents
    )
    
    return response.text


def handle_full_request(prompt):
    """Handles standard text and tool-use requests via the chat session."""
    
    tool_responses = []
    
    # 1. Send the initial prompt
    response = st.session_state.chat_session.send_message(prompt)
    
    # 2. Check for and execute tool calls
    while response.function_calls:
        st.markdown(f"**🤖 Nexus executing tool...**") 
        tool_responses = []
        
        for function_call in response.function_calls:
            tool_name = function_call.name
            tool_args = dict(function_call.args)
            
            if tool_name in AVAILABLE_TOOLS:
                function_to_call = AVAILABLE_TOOLS[tool_name]
                tool_result = function_to_call(**tool_args)
                
                tool_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={'result': tool_result}
                    )
                )
        # 3. Send tool results back to the model (FIXED: Positional Argument)
        response = st.session_state.chat_session.send_message(tool_responses) 
    
    # 4. Return the final text response from the model
    return response.text


# --- 3. FRONTEND LAYOUT AND LOGIC ---

# Display all messages from the session history
for message in st.session_state.messages:
    # Set custom avatar icon for user (🧑‍💻) and assistant (🤖)
    avatar = "🧑‍💻" if message["role"] == "user" else "🤖"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"]) 

# --- Multimodal File Uploader in the sidebar ---
uploaded_file = st.sidebar.file_uploader("Upload Image for Analysis", type=["jpg", "jpeg", "png"])
st.sidebar.markdown("---")
st.sidebar.markdown("**Note:** Uploaded images will be sent along with your next text prompt.")


# Process user input
if prompt := st.chat_input("Ask Nexus a question or command a task..."):
    
    # 1. Add user message to history and display it
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)

    # 2. Get and display Nexus's response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Nexus is thinking..."):
            
            # --- Determine if this is a MULTIMODAL request ---
            if uploaded_file is not None:
                try:
                    # Read image data
                    image_data = Image.open(uploaded_file)
                    
                    # Call the specialized multimodal handler
                    response_text = handle_multimodal_request(image_data, prompt)
                
                except Exception as e:
                    response_text = f"Error processing image: {e}"
            
            else:
                # --- Standard TEXT/TOOL request ---
                response_text = handle_full_request(prompt)
        
        st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
