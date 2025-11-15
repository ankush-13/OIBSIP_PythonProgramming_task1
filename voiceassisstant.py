# advanced_assistant.py
import os
import speech_recognition as sr
import pyttsx3
import datetime
import wikipedia
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()  # loads .env if present

class VoiceAssistant:
    def __init__(self, name="Jarvis"):
        self.name = name
        self.recognizer = sr.Recognizer()
        self.tts = pyttsx3.init()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        # Configuration
        self.owm_key = os.getenv("OWM_API_KEY")  # OpenWeatherMap API key for weather feature
        self.email_config = {
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("SMTP_PORT", 587)),
            "email": os.getenv("EMAIL_ADDRESS"),
            "password": os.getenv("EMAIL_PASSWORD"),  # use app password for Gmail
        }

    # Basic I/O
    def speak(self, text):
        print("Assistant:", text)
        self.tts.say(text)
        self.tts.runAndWait()

    def listen(self, timeout=5, phrase_time_limit=8):
        with sr.Microphone() as mic:
            self.recognizer.adjust_for_ambient_noise(mic, duration=0.5)
            try:
                audio = self.recognizer.listen(mic, timeout=timeout, phrase_time_limit=phrase_time_limit)
                text = self.recognizer.recognize_google(audio)
                print("Heard:", text)
                return text.lower()
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                return ""
            except sr.RequestError:
                self.speak("Network problem when trying to recognize speech.")
                return ""

    # Intent routing
    def handle(self, text):
        if not text:
            return

        # Greeting
        if any(k in text for k in ("hello", "hi", f"hey {self.name.lower()}", "hey")):
            self.speak(f"Hello, I'm {self.name}. How can I help you?")
            return

        # Time / Date
        if "time" in text:
            now = datetime.datetime.now()
            self.speak(now.strftime("The time is %I:%M %p."))
            return
        if "date" in text:
            now = datetime.datetime.now()
            self.speak(now.strftime("Today is %A, %B %d, %Y."))
            return

        # Weather: "what's the weather in mumbai"
        if "weather" in text:
            city = text.replace("weather in", "").replace("weather", "").strip()
            if not city:
                self.speak("Which city?")
                city = self.listen()
            if city:
                self.speak(self.get_weather(city))
            return

        # Reminders: "remind me to call mom at 6 pm"
        if "remind me" in text:
            # naive parser for "remind me to <task> at <time>"
            try:
                if " at " in text:
                    part_task = text.split("remind me to",1)[1].strip()
                    task, at_part = part_task.rsplit(" at ", 1)
                    run_time = self.parse_time_string(at_part)
                    if run_time:
                        self.schedule_reminder(task.strip(), run_time)
                        self.speak(f"Okay, I will remind you to {task.strip()} at {run_time.strftime('%I:%M %p')}.")
                    else:
                        self.speak("Sorry, I couldn't parse the time. Say like 'remind me to call mom at 18:30' or 'at 6 pm'.")
                else:
                    self.speak("Tell me when to remind you, for example 'remind me to X at 6 pm'.")
            except Exception as e:
                self.speak("Failed to set reminder.")
            return

        # Send email: "send email to alice@example.com subject hello body hi"
        if text.startswith("send email") or "send an email" in text:
            # Very simple parsing; for robust usage build proper parser or GUI prompts
            self.speak("Who should I send the email to? Provide email address.")
            to_addr = self.listen()
            self.speak("What is the subject?")
            subj = self.listen()
            self.speak("What is the message?")
            body = self.listen()
            success = self.send_email(to_addr, subj, body)
            if success:
                self.speak("Email sent.")
            else:
                self.speak("Failed to send email. Check configuration.")
            return

        # Smart home control placeholder
        if "turn on" in text or "turn off" in text:
            # Example: "turn on bedroom light"
            self.speak("Smart home: request received. (This is a placeholder; integrate your device API here.)")
            # Example hook: self.call_smart_home_api(device, on_off)
            return

        # Web search / general knowledge
        if "search for" in text or "who is" in text or "what is" in text or text.startswith("search"):
            q = text.replace("search for", "").strip()
            if not q:
                self.speak("What would you like me to search for?")
                q = self.listen()
            if q:
                self.speak("Searching.")
                ans = self.web_search(q)
                self.speak(ans)
            return

        self.speak("Sorry, I didn't understand. Try 'time', 'weather in <city>', 'remind me to ... at ...', or 'search for ...'.")

    # Utilities
    def parse_time_string(self, timestr):
        # supports 'HH:MM' 24h or '6 pm'/'6:30 am'
        try:
            timestr = timestr.strip().lower()
            now = datetime.datetime.now()
            if ":" in timestr:
                t = datetime.datetime.strptime(timestr, "%H:%M")
                run = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                if run < now:
                    run += datetime.timedelta(days=1)
                return run
            # handle am/pm
            import re
            m = re.match(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', timestr)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2)) if m.group(2) else 0
                ampm = m.group(3)
                if ampm == 'pm' and hour != 12:
                    hour += 12
                if ampm == 'am' and hour == 12:
                    hour = 0
                run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if run < now:
                    run += datetime.timedelta(days=1)
                return run
        except Exception:
            return None

    def schedule_reminder(self, task_text, run_time_dt):
        # uses APScheduler to schedule a job
        def job():
            self.speak(f"Reminder: {task_text}")

        self.scheduler.add_job(job, 'date', run_date=run_time_dt)

    def get_weather(self, city):
        if not self.owm_key:
            return "Weather API key not configured. Put OWM_API_KEY in .env."
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": self.owm_key, "units": "metric"}
        try:
            r = requests.get(url, params=params, timeout=8)
            data = r.json()
            if data.get("cod") != 200:
                return f"Weather service error: {data.get('message', 'unknown')}"
            main = data["main"]
            weather = data["weather"][0]["description"]
            temp = main["temp"]
            return f"{city.capitalize()}: {weather}. Temperature {temp}°C."
        except Exception as e:
            return "Failed to fetch weather."

    def web_search(self, query):
        # try DuckDuckGo instant answer first
        try:
            resp = requests.get("https://api.duckduckgo.com/",
                                params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1}, timeout=6)
            data = resp.json()
            if data.get("Abstract"):
                return data["Abstract"]
            # fallback to wikipedia
            try:
                return wikipedia.summary(query, sentences=2)
            except Exception:
                return "No concise answer found."
        except Exception:
            return "Search error."

    def send_email(self, to_addr, subject, body):
        cfg = self.email_config
        if not cfg["email"] or not cfg["password"]:
            self.speak("Email config not set in environment.")
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = cfg["email"]
            msg["To"] = to_addr
            msg.set_content(body)
            with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(cfg["email"], cfg["password"])
                smtp.send_message(msg)
            return True
        except Exception as e:
            print("email error:", e)
            return False

    # run loop
    def run(self):
        self.speak(f"Hello — {self.name} starting. Say 'stop' to exit.")
        try:
            while True:
                text = self.listen()
                if not text:
                    continue
                if "stop" in text or "exit" in text or "quit" in text:
                    self.speak("Shutting down. Bye.")
                    break
                # process on a separate thread so the assistant remains responsive
                threading.Thread(target=self.handle, args=(text,)).start()
        except KeyboardInterrupt:
            self.speak("Interrupted. Exiting.")
        finally:
            self.scheduler.shutdown(wait=False)

if __name__ == "__main__":
    assistant = VoiceAssistant(name="Ava")
    assistant.run()
