import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import requests
from io import BytesIO
import random
import datetime
import time
import threading

# ================= CONFIG =================
EXECUTION_INTERVAL_SEC = 5
VOLTAGE_ESP32 = 3.3

WEATHER_API_KEY = ""
LOCATIONIQ_KEY = ""

# ======= ANTALYA COORDINATES =======
ANT_LAT = 36.8969
ANT_LON = 30.7133


# ================= MAP =================
def fetch_map_image():
    zoom = 11
    size = "900x600"

    url = (
        "https://maps.locationiq.com/v3/staticmap"
        f"?key={LOCATIONIQ_KEY}"
        f"&center={ANT_LAT},{ANT_LON}"
        f"&zoom={zoom}"
        f"&size={size}"
        f"&format=png"
    )

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return Image.open(BytesIO(r.content))


# ================= WEATHER =================
def get_weather():
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={ANT_LAT}&lon={ANT_LON}"
        f"&appid={WEATHER_API_KEY}&units=metric"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None


# ================= BATTERY =================
class Battery:
    def __init__(self, capacity):
        self.capacity = capacity
        self.energy = random.uniform(0.35 * capacity, 0.85 * capacity)

    def consume(self, w):
        self.energy = max(0, self.energy - w)

    def charge(self, w):
        self.energy = min(self.capacity, self.energy + w)

    def percent(self):
        return (self.energy / self.capacity) * 100


# ================= NODE =================
class Node:
    def __init__(self, x, y):
        self.id = random.randint(1000, 9999)
        self.x = x
        self.y = y
        self.battery = Battery(1000)
        self.cloud = random.randint(0, 100)
        self.state = "NORMAL"
        self.data = {}

    def update(self, weather):
        base_temp = weather["main"]["temp"]
        base_hum = weather["main"]["humidity"]
        cloud_api = weather["clouds"]["all"]

        temp = base_temp + random.uniform(-2, 2)
        hum = base_hum + random.uniform(-6, 6)

        # ===== POWER CONSUMPTION =====
        esp_power = VOLTAGE_ESP32 * random.uniform(0.15, 0.35)
        sensor_power = 5 * random.uniform(0.002, 0.005)

        self.battery.consume(
            (esp_power + sensor_power) * EXECUTION_INTERVAL_SEC / 3600
        )

        # ===== SOLAR (DAY/NIGHT + CLOUD) =====
        now_hour = datetime.datetime.now().hour
        sunrise = datetime.datetime.fromtimestamp(weather["sys"]["sunrise"]).hour
        sunset = datetime.datetime.fromtimestamp(weather["sys"]["sunset"]).hour

        if now_hour < sunrise or now_hour > sunset:
            solar = 0
        else:
            solar = random.uniform(250, 700)
            solar *= (1 - cloud_api / 100)
            solar *= random.uniform(0.05, 0.18)

        self.battery.charge(solar * EXECUTION_INTERVAL_SEC / 3600)

        percent = self.battery.percent()

        if percent < 20:
            self.state = "CRITICAL"
        elif percent < 50:
            self.state = "WARNING"
        else:
            self.state = "NORMAL"

        self.data = {
            "temperature": temp,
            "humidity": hum,
            "solar": solar,
            "battery": percent
        }

    def color(self):
        if self.state == "CRITICAL":
            return "red"
        elif self.state == "WARNING":
            return "yellow"
        return "green"


# ================= SIM ENGINE =================
class SimulationEngine:
    def step(self, nodes, weather):
        if not weather:
            return

        for node in nodes:
            node.update(weather)


# ================= CLOCK =================
def tick(lbl):
    lbl.config(text=time.strftime("%H:%M:%S"))
    lbl.after(1000, lambda: tick(lbl))


def update_date(lbl):
    lbl.config(text=datetime.datetime.now().strftime("%d-%m-%Y"))
    lbl.after(86400000, lambda: update_date(lbl))


# ================= APP =================
class DigitalTwinApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Digital Twin Control Panel – Antalya")
        self.geometry("900x600")

        self.base_map = fetch_map_image()
        self.map_img = self.base_map.copy()
        self.map_photo = ImageTk.PhotoImage(self.map_img)

        self.canvas = tk.Canvas(self, width=900, height=600)
        self.canvas.pack(fill="both", expand=True)
        self.canvas_img = self.canvas.create_image(0, 0, anchor="nw", image=self.map_photo)

        self.nodes = []
        self.engine = SimulationEngine()

        self.btn_node = tk.Button(self, text="Create Nodes", command=self.create_nodes)
        self.canvas.create_window(880, 40, anchor="ne", window=self.btn_node)

        self.btn_exec = tk.Button(self, text="Execute", command=self.run_thread)
        self.canvas.create_window(880, 80, anchor="ne", window=self.btn_exec)

        self.lbl_nodes = tk.Label(self, bg="white")
        self.canvas.create_window(880, 120, anchor="ne", window=self.lbl_nodes)

        self.lbl_log = tk.Label(self, bg="white", justify="left")
        self.canvas.create_window(880, 260, anchor="ne", window=self.lbl_log)

        self.lbl_clock = tk.Label(self, bg="white", font=("Arial", 16, "bold"))
        self.canvas.create_window(880, 10, anchor="ne", window=self.lbl_clock)
        tick(self.lbl_clock)

        self.lbl_date = tk.Label(self, bg="white")
        self.canvas.create_window(880, 380, anchor="ne", window=self.lbl_date)
        update_date(self.lbl_date)

        self.canvas.bind("<Motion>", self.on_hover)

    # ================= NODE OPS =================
    def create_nodes(self):
        self.nodes.clear()
        self.map_img = self.base_map.copy()
        draw = ImageDraw.Draw(self.map_img)

        for _ in range(random.randint(6, 10)):
            x = random.randint(50, 700)
            y = random.randint(50, 500)
            node = Node(x, y)
            self.nodes.append(node)
            draw.ellipse((x-5, y-5, x+5, y+5), fill="green")

        self.refresh_map()
        self.lbl_nodes.config(text=f"Nodes: {len(self.nodes)}")

    # ================= SIM =================
    def run_thread(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            weather = get_weather()
            self.engine.step(self.nodes, weather)

            self.map_img = self.base_map.copy()
            draw = ImageDraw.Draw(self.map_img)

            for n in self.nodes:
                draw.ellipse(
                    (n.x-5, n.y-5, n.x+5, n.y+5),
                    fill=n.color()
                )

            self.refresh_map()
            time.sleep(EXECUTION_INTERVAL_SEC)

    def refresh_map(self):
        self.map_photo = ImageTk.PhotoImage(self.map_img)
        self.canvas.itemconfig(self.canvas_img, image=self.map_photo)

    # ================= HOVER =================
    def on_hover(self, e):
        for n in self.nodes:
            if (e.x - n.x)**2 + (e.y - n.y)**2 < 25:
                d = n.data
                self.lbl_log.config(text=
                    f"Node ID: {n.id}\n"
                    f"Temp: {d.get('temperature', 0):.1f} °C\n"
                    f"Humidity: {d.get('humidity', 0):.1f} %\n"
                    f"Solar: {d.get('solar', 0):.1f} W\n"
                    f"Battery: {d.get('battery', 0):.1f} %\n"
                    f"State: {n.state}"
                )
                return
        self.lbl_log.config(text="")


# ================= RUN =================
if __name__ == "__main__":
    DigitalTwinApp().mainloop()
