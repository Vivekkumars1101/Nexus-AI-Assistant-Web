import speech_recognition as sr
import pyttsx3
import datetime
import time
import os
import webbrowser
import pywhatkit
import json
from pathlib import Path
import threading
import subprocess 
import re 
from tkinter import filedialog
from PIL import Image
from tkinter import scrolledtext
import tkinter as tk
from tkinter import messagebox

from dotenv import load_dotenv

import customtkinter as ctk

from google import genai
from google.genai import types

# --- CRITICAL FIX 1: Load .env file at startup ---
load_dotenv() 
# ------------------------------------------------

# --- 0. Configuration and Memory Setup ---

MEMORY_FILE = Path("assistant_memory.json")
CHAT_HISTORY_FILE = Path("chat_history.json") 

def load_memory():
    """Loads long-term memory notes from the JSON file."""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: Memory file is corrupted, starting with an empty long-term memory.")
            return []
    return []

def save_memory(notes):
    """Saves the current list of long-term notes to the JSON file."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(notes, f, indent=4)

def load_chat_history():
    """Loads chat history from JSON file for persistence."""
    if CHAT_HISTORY_FILE.exists():
        with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_chat_history(history):
    """Saves the current chat history list to JSON file."""
    serializable_history = []
    
    for content in history:
        serializable_parts = [
            {'text': part.text} 
            for part in content.parts if part.text
        ]
        if serializable_parts:
            serializable_history.append({
                'role': content.role,
                'parts': serializable_parts
            })
        
    with open(CHAT_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(serializable_history, f, indent=4)


PERSONAL_NOTES = load_memory()
print(f"Loaded {len(PERSONAL_NOTES)} personal notes from memory.")

# --- 1. Global Tool Setup ---

AVAILABLE_TOOLS = {}
def add_tool(func):
    """Decorator to automatically add functions to the AVAILABLE_TOOLS map."""
    AVAILABLE_TOOLS[func.__name__] = func
    return func

global_app_speak = lambda text: print(f"Assistant: {text}") 

# --- 2. Tool Definitions ---

@add_tool
def web_search(query: str):
    """Searches the web using Google and opens the default browser to the search results."""
    global_app_speak(f"Searching the web for: {query}")
    try:
        pywhatkit.search(query)
        return f"I have opened your default browser to the search results for '{query}'."
    except Exception as e:
        return f"Error opening the web browser: {e}"

@add_tool
def play_on_youtube(topic: str):
    """Opens YouTube and plays a video related to the given topic."""
    global_app_speak(f"Attempting to play '{topic}' on YouTube.")
    try:
        pywhatkit.playonyt(topic)
        return f"Video for '{topic}' is now playing on YouTube."
    except Exception as e:
        return f"I was unable to play the video on YouTube: {e}"

@add_tool
def check_current_time():
    """Returns the current local time."""
    now = datetime.datetime.now().strftime("%I:%M %p")
    return f"The current time is {now}"

@add_tool
def add_personal_note(note_text: str):
    """Saves a piece of personal information or a key preference for later retrieval."""
    global_app_speak("Acknowledged. Saving a personal note.")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PERSONAL_NOTES.append({'time': timestamp, 'note': note_text})
    save_memory(PERSONAL_NOTES)
    return f"I have successfully remembered the note: '{note_text}'"

@add_tool
def retrieve_personal_notes(query: str):
    """Returns all stored personal notes for the AI to process."""
    if not PERSONAL_NOTES:
        return "I have no personal notes saved yet."
    note_strings = [f"Time: {n['time']}, Note: {n['note']}" for n in PERSONAL_NOTES]
    return "The user's stored notes are:\n" + "\n".join(note_strings)

def reminder_worker(delay_seconds, reminder_text):
    """The function run by the background thread to wait and speak the reminder."""
    print(f"\nScheduler: Timer started for {delay_seconds} seconds.")
    time.sleep(delay_seconds)
    global_app_speak(f"REMINDER! {reminder_text}")
    print("\nListening...")

def parse_time_to_seconds(time_string: str) -> int:
    """Converts a time phrase (e.g., '5 minutes and 10 seconds') into total seconds."""
    time_string = time_string.lower()
    parts = time_string.split()
    total_seconds = 0
    try:
        for i, part in enumerate(parts):
            if part.isdigit():
                value = int(part)
                if i + 1 < len(parts):
                    unit = parts[i+1]
                    if 'second' in unit: total_seconds += value
                    elif 'minute' in unit: total_seconds += value * 60
                    elif 'hour' in unit: total_seconds += value * 3600
        if total_seconds == 0 and parts and parts[0].isdigit():
             total_seconds = int(parts[0]) * 60
    except Exception: return 0 
    return max(0, min(total_seconds, 3600))

@add_tool
def set_reminder(time_string: str, reminder_text: str):
    """Sets a reminder that will speak the message after the specified time has passed."""
    delay = parse_time_to_seconds(time_string)
    if delay <= 0: return "I could not understand the duration for the reminder. Please be specific."
    
    timer_thread = threading.Thread(target=reminder_worker, args=(delay, reminder_text))
    timer_thread.daemon = True
    timer_thread.start()
    
    minutes, seconds = divmod(delay, 60)
    time_display = f"{minutes} minutes and {seconds} seconds" if minutes > 0 else f"{seconds} seconds"
    return f"Reminder set successfully! I will remind you to '{reminder_text}' in {time_display}."

@add_tool
def open_application(app_name: str):
    """Opens a common application on the user's operating system."""
    global_app_speak(f"Using open_application tool to launch: {app_name}")
    app_name = app_name.lower().replace(" ", "")
    
    app_map = {
        'notepad': 'notepad.exe',
        'calculator': 'calc.exe',
        'browser': 'chrome.exe', 
        'terminal': 'cmd.exe',
        'settings': 'start ms-settings:', 
        'control panel': 'explorer shell:controlpanel',
        'explorer': 'explorer.exe',
        'steam': r'C:\Program Files (x86)\Steam\steam.exe' 
    }
    
    executable = app_map.get(app_name, app_name) 

    try:
        subprocess.Popen(executable, shell=True) 
        return f"Successfully launched the application: {app_name}."
    except FileNotFoundError:
        return f"Error: The application '{app_name}' could not be found or launched. Check the full path."
    except Exception as e:
        return f"An unknown error occurred while trying to launch {app_name}: {e}"

@add_tool
def take_quick_note(note_text: str):
    """Saves a text note instantly to a temporary local file named 'quick_note.txt'."""
    global_app_speak(f"Using take_quick_note tool to save a transient note.")
    file_path = "quick_note.txt"
    try:
        with open(file_path, "a") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] - {note_text}\n")
        return f"Note successfully saved to {file_path}."
    except Exception as e:
        return f"Could not save the quick note due to an error: {e}"


# --- 3. GUI Application Class (V2.0) ---

class AssistantApp:
    def __init__(self, master):
        self.master = master
        master.title("Nexus Personal AI Assistant")
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        master.geometry("600x650")
        master.grid_columnconfigure(0, weight=1)
        master.grid_rowconfigure(0, weight=1)

        # 1. Initialize TTS and set global speak reference
        self.init_tts()
        global global_app_speak
        global_app_speak = self.speak
        
        # 2. Set up GUI components (CRITICAL: Creates self.log_area)
        self.setup_ui() 
        
        # 3. Initialize Gemini (CRITICAL: NOW self.log_area exists)
        self.init_gemini()
        
        self.speak("Nexus is starting up. Click the microphone to talk or type your command below.")
        
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # --- Initialization Methods ---
    def init_tts(self):
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty('voices')
        self.engine.setProperty('voice', voices[0].id) 

    def speak(self, text):
        """FIXED: Converts text to speech on a separate thread to prevent blocking the GUI and other methods."""
        self.log_message(f"{text}", tag="assistant_speech")
        
        def run_speech():
            self.engine.say(text)
            self.engine.runAndWait()

        threading.Thread(target=run_speech).start()

    def init_gemini(self):
        self.chat_ready = False
        self.chat = None

        if "GEMINI_API_KEY" not in os.environ:
            self.log_message("SYSTEM ERROR: GEMINI_API_KEY environment variable not set. Core AI is disabled.", "system")
            self.status_label.configure(text="Status: API KEY MISSING (AI Disabled)", text_color="red")
            return

        # --- HISTORY LOADING (Fixes 4 & 5) ---
        raw_history = load_chat_history()
        history_for_chat = []
        for entry in raw_history:
            # FIX APPLIED HERE: Use the explicit Part constructor to avoid TypeError
            parts = [types.Part(text=p['text']) for p in entry['parts'] if p.get('text')] 
            if parts:
                history_for_chat.append(types.Content(role=entry['role'], parts=parts))

        tool_list = list(AVAILABLE_TOOLS.values())

        tool_config = types.GenerateContentConfig(
            tools=tool_list,
            system_instruction="You are a dedicated, efficient, and slightly witty personal AI assistant named 'Nexus'. You use clear, concise language and always mention which tool you are using before providing the final answer, especially when performing a task for the user.",
        )
        try:
            self.client = genai.Client()
            self.chat = self.client.chats.create(
                model='gemini-2.5-flash', 
                config=tool_config,
                history=history_for_chat
            )
            self.chat_ready = True
            self.log_message("System: Gemini AI Client Initialized successfully.", "system")
            self.status_label.configure(text="Status: Ready (AI Active)", text_color="green")
        except Exception as e:
            self.log_message(f"CRITICAL ERROR: Could not initialize Gemini Client. Details: {e}", "system")
            self.status_label.configure(text="Status: AI Initialization Failed!", text_color="red")
            messagebox.showerror("Gemini Error", f"Could not initialize Gemini Client. Details: {e}")
            self.master.quit()

    # --- New Closing Protocol ---
    def on_closing(self):
        """Saves chat history before closing the application."""
        if self.chat_ready:
            try:
                history = self.chat.get_history()
                save_chat_history(history)
                self.log_message("System: Chat history saved successfully.", "system")
            except Exception as e:
                self.log_message(f"Warning: Failed to save chat history: {e}", "system")
        
        self.master.destroy()

    # --- UI Setup ---
    def setup_ui(self):
        """Creates the modern UI widgets with improved scaling and branding."""
        
        self.master.grid_columnconfigure(0, weight=1)
        self.master.grid_rowconfigure(0, weight=0)
        self.master.grid_rowconfigure(1, weight=1) 
        self.master.grid_rowconfigure(2, weight=0) 
        self.master.grid_rowconfigure(3, weight=0) 

        # --- A. Header Frame ---
        header_frame = ctk.CTkFrame(self.master, height=50, fg_color="#3A3A3A", corner_radius=0)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="new")
        header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(header_frame, text="🧠 Nexus AI Assistant", font=('Arial', 18, 'bold'), text_color="#A9CCE3").grid(row=0, column=0, padx=20, pady=10, sticky="w")


        # --- B. Conversation Frame ---
        self.conv_container = ctk.CTkFrame(self.master, fg_color="transparent")
        self.conv_container.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.conv_container.grid_columnconfigure(0, weight=1) 
        self.conv_container.grid_rowconfigure(0, weight=1)

        # Log Area (Using standard Tkinter ScrolledText for text manipulation)
        self.log_area = scrolledtext.ScrolledText(self.conv_container, wrap=tk.WORD, bg="#1E1E1E", fg="white", bd=0, relief=tk.FLAT, font=('Arial', 12)) 
        self.log_area.grid(row=0, column=0, sticky="nsew")
        self.log_area.config(state=tk.DISABLED)


        # --- C. Input and Status Areas ---

        # Input Frame 
        input_frame = ctk.CTkFrame(self.master)
        input_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        # Input Entry
        self.input_entry = ctk.CTkEntry(input_frame, width=400, placeholder_text="Type your command here...", font=('Arial', 14))
        self.input_entry.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew")
        self.input_entry.bind('<Return>', lambda event: self.process_text_command())
        self.input_entry.bind('<Key>', lambda event: self.input_entry.configure(placeholder_text_color="#A9CCE3"))
        self.input_entry.bind('<FocusOut>', lambda event: self.input_entry.configure(placeholder_text_color="gray"))
        
        # Buttons
        ctk.CTkButton(input_frame, text="🖼️ Image", command=self.open_image_dialog, width=80).grid(row=0, column=1, padx=5, pady=10)
        ctk.CTkButton(input_frame, text="Send", command=self.process_text_command, width=80).grid(row=0, column=2, padx=5, pady=10)
        
        self.talk_button = ctk.CTkButton(input_frame, text="🎤 Talk", command=self.start_voice_thread, fg_color="green", hover_color="#004d00", width=80)
        self.talk_button.grid(row=0, column=3, padx=(5, 10), pady=10)
        
        # Status Area
        status_area = ctk.CTkFrame(self.master, height=30)
        status_area.grid(row=3, column=0, columnspan=2, sticky='we', padx=10, pady=(0, 10))
        status_area.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(status_area, text="Status: Starting...", anchor="w", font=('Arial', 10))
        self.status_label.grid(row=0, column=0, sticky='w', padx=5)

        self.progress_bar = ctk.CTkProgressBar(status_area, width=100)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=1, sticky='e', padx=5)

    def log_message(self, message, tag=None):
        """Inserts formatted text into the log area, handling labels (Fix 2)."""
        self.log_area.configure(state="normal") 
        
        if tag == "system":
            label = "[SYSTEM] "
        elif tag == "user":
            label = "[VIVEK] "
        elif tag == "assistant_speech":
            label = "[NEXUS.AI] "
        else:
            label = ""
        
        self.log_area.insert(tk.END, f"\n{label}{message}", tag)
        
        self.log_area.tag_config('system', foreground='#FFD700', justify=tk.LEFT)
        self.log_area.tag_config('user', foreground='white', justify=tk.LEFT)
        self.log_area.tag_config('assistant_speech', foreground='#ADD8E6', justify=tk.LEFT)
        
        self.log_area.see(tk.END) 
        self.log_area.configure(state="disabled")
    
    # --- Visual Feedback / Animation Methods ---

    def start_loading_animation(self, status_text):
        self.status_label.configure(text=f"Status: {status_text}")
        self.talk_button.configure(state="disabled", fg_color="gray")
        self.progress_bar.start() 

    def stop_loading_animation(self):
        self.progress_bar.stop()
        self.progress_bar.set(0) 
        self.status_label.configure(text="Status: Ready")
        self.talk_button.configure(state="normal", fg_color="green")

    # --- New Multimodality Handler ---
    def open_image_dialog(self):
        """Opens a file dialog to select an image and prompts the user for a question."""
        if self.talk_button.cget("state") == "disabled":
            self.speak("Please wait until Nexus finishes its current task before giving a new command.")
            return

        if not self.chat_ready:
            self.speak("I must be connected to the AI to analyze an image.")
            return

        image_path = filedialog.askopenfilename(
            title="Select Image for Analysis",
            filetypes=[("Image files", "*.jpg *.jpeg *.png")]
        )
        
        if image_path:
            self.input_entry.delete(0, ctk.END)
            self.input_entry.insert(0, f"What do you see in this image? [IMAGE_PATH:{image_path}]")
            self.speak("Image selected. Please modify the text box with your question and press Send.")

    # --- Command Processing ---

    def process_text_command(self):
        command = self.input_entry.get().strip() 
        if not command: return
        self.input_entry.delete(0, ctk.END)
        self.log_message(f"{command}", "user")
        self.start_command_thread(command)

    def start_voice_thread(self):
        if self.talk_button.cget("state") == "disabled":
            self.speak("I'm already busy!")
            return
        
        self.start_loading_animation("Listening...") 
        threading.Thread(target=self.listen_and_process).start()

    def listen_and_process(self):
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                self.stop_loading_animation()
                return

        try:
            command = r.recognize_google(audio, language='en-in').lower()
            self.log_message(f"{command}", "user")
            self.start_command_thread(command)
        except sr.UnknownValueError:
            self.speak("Sorry, I did not understand that.")
        except sr.RequestError:
            self.speak("Could not connect to the voice recognition service.")
        finally:
            pass 

    def start_command_thread(self, command):
        self.start_loading_animation("Thinking...")
        threading.Thread(target=self.handle_command, args=(command,)).start()

    def handle_command(self, command):
        
        if not self.chat_ready:
            self.speak("I am sorry, my core AI brain is not active. Please check the API key.")
            self.master.after(0, self.stop_loading_animation)
            return

        # --- PREPARE CONTENTS FOR CHAT ---
        contents_to_send = []
        image_tag_match = re.search(r"\[IMAGE_PATH:(.*?)\]", command)
        
        if image_tag_match:
            image_path = image_tag_match.group(1).strip()
            text_prompt = command.replace(image_tag_match.group(0), "").strip()
            
            if not text_prompt:
                text_prompt = "What do you see in this image?"
            
            try:
                # Load image object and append it to contents
                img = Image.open(image_path)
                contents_to_send.append(img)
                contents_to_send.append(text_prompt)
                self.log_message(f"System: Sending image for analysis: {image_path}", "system")

            except FileNotFoundError:
                self.speak(f"Error: The image file was not found at {image_path}. Please verify the path.")
                self.master.after(0, self.stop_loading_animation)
                return
            except Exception as e:
                self.speak(f"Error loading image for analysis: {e}")
                self.master.after(0, self.stop_loading_animation)
                return
        else:
            # If no image tag, send the command as plain text
            contents_to_send.append(command)
        # --- END PREPARE CONTENTS ---

        if "hello" in command.lower() or "hi" in command.lower():
            self.speak("Hello! I am Nexus. How may I be of assistance?")
            self.master.after(0, self.stop_loading_animation)
            return
        elif "stop" in command.lower() or "exit" in command.lower() or "goodbye" in command.lower():
            self.speak("Goodbye! Shutting down Nexus now.")
            self.master.quit()
            return
        
        self.speak("Thinking...")
        try:
            # FIX APPLIED HERE: Sending contents_to_send as a positional argument
            response = self.chat.send_message(contents_to_send)
            
            while response.function_calls:
                
                tool_responses = []
                
                # 1. Provide Instant Spoken Feedback
                for function_call in response.function_calls:
                    tool_name = function_call.name
                    friendly_name = tool_name.replace("_", " ") 
                    self.speak(f"Processing command using the '{friendly_name}' tool.")
                    
                # 2. Execute all tool calls
                for function_call in response.function_calls:
                    tool_name = function_call.name
                    tool_args = dict(function_call.args)
                    
                    if tool_name in AVAILABLE_TOOLS:
                        function_to_call = AVAILABLE_TOOLS[tool_name]
                        
                        try:
                            tool_result = function_to_call(**tool_args)
                            self.log_message(f"Tool executed. Result: {tool_result}", "system")
                            
                            tool_responses.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response={'result': tool_result}
                                )
                            )
                        except Exception as e:
                            error_message = f"An error occurred while running the tool {tool_name}: {e}"
                            self.speak(error_message)
                            tool_responses.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response={'result': error_message}
                                )
                            )
                    else:
                        self.speak(f"The model suggested calling an unknown tool: {tool_name}")

                # FIX APPLIED HERE: Sending tool_responses as a positional argument
                response = self.chat.send_message(tool_responses)
            
            self.speak(response.text)

        except Exception as e:
            self.speak(f"An unexpected error occurred: {e}")
        finally:
            self.master.after(0, self.stop_loading_animation)


# --- 4. Main Program Execution ---

if __name__ == "__main__":
    
    root = ctk.CTk()
    app = AssistantApp(root)
    root.mainloop()