import tkinter as tk
from tkinter import scrolledtext
import socket
import threading

class QuizClient:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Quiz Game Client")
        
        # Grid Configuration
        master.grid_columnconfigure(index=list(range(4)), weight=1)
        master.grid_rowconfigure(index=5, weight=1) # Log area expands

        self.client_socket = None
        self.is_connected = False
        self.thread = None
        
        # Game State Variables
        self.selected_answer = tk.StringVar(value="")

        self.create_widgets()

    def create_widgets(self):
        # Row 0: Connection Details
        conn_frame = tk.Frame(self.master)
        conn_frame.grid(row=0, column=0, columnspan=4, pady=10, padx=10, sticky="ew")
        
        conn_frame.grid_columnconfigure(index=[1, 3, 5], weight=1)

        tk.Label(conn_frame, text="IP:").pack(side=tk.LEFT, padx=2)
        self.ip_entry = tk.Entry(conn_frame, width=15)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(conn_frame, text="Port:").pack(side=tk.LEFT, padx=2)
        self.port_entry = tk.Entry(conn_frame, width=8)
        self.port_entry.insert(0, "12345")
        self.port_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(conn_frame, text="Name:").pack(side=tk.LEFT, padx=2)
        self.name_entry = tk.Entry(conn_frame, width=15)
        self.name_entry.pack(side=tk.LEFT, padx=2)

        self.connect_button = tk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=10)
        self.connect_button.pack(side=tk.LEFT, padx=10)

        # Row 1: Horizontal Rule
        tk.Frame(self.master, height=2, bd=1, relief=tk.SUNKEN).grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=5)

        # Row 2: Question Display / Instructions
        tk.Label(self.master, text="Game Zone", font=("Arial", 12, "bold")).grid(row=2, column=0, columnspan=4, pady=5)

        # Row 3: Radio Buttons for Answers
        self.radio_frame = tk.Frame(self.master)
        self.radio_frame.grid(row=3, column=0, columnspan=4, pady=5)
        
        self.rb_a = tk.Radiobutton(self.radio_frame, text="Option A", variable=self.selected_answer, value="A", state=tk.DISABLED, font=("Arial", 10))
        self.rb_b = tk.Radiobutton(self.radio_frame, text="Option B", variable=self.selected_answer, value="B", state=tk.DISABLED, font=("Arial", 10))
        self.rb_c = tk.Radiobutton(self.radio_frame, text="Option C", variable=self.selected_answer, value="C", state=tk.DISABLED, font=("Arial", 10))
        
        self.rb_a.pack(side=tk.LEFT, padx=20)
        self.rb_b.pack(side=tk.LEFT, padx=20)
        self.rb_c.pack(side=tk.LEFT, padx=20)

        # Row 4: Submit Button
        self.submit_btn = tk.Button(self.master, text="Submit Answer", command=self.submit_answer, state=tk.DISABLED, font=("Arial", 10, "bold"))
        self.submit_btn.grid(row=4, column=0, columnspan=4, pady=10)

        # Row 5: Log / Status Display
        self.text_widget = scrolledtext.ScrolledText(self.master, state=tk.DISABLED, height=15)
        self.text_widget.grid(row=5, column=0, columnspan=4, pady=10, padx=10, sticky="nsew")

    def add_log(self, message):
        # Logs to Text Widget.
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, message + "\n")
        self.text_widget.see(tk.END) # Auto-scroll
        self.text_widget.config(state=tk.DISABLED)

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        ip = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()
        name = self.name_entry.get().strip()

        if not ip or not port_str or not name:
            self.add_log("Error: IP, Port, and Name are required.")
            return

        try:
            port = int(port_str)
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(5.0) 
            self.client_socket.connect((ip, port))
            self.client_socket.settimeout(None) 

            # Send Name immediately
            self.client_socket.sendall(name.encode())
            
            self.is_connected = True
            
            # Update GUI
            self.connect_button.config(text="Disconnect")
            self.ip_entry.config(state=tk.DISABLED)
            self.port_entry.config(state=tk.DISABLED)
            self.name_entry.config(state=tk.DISABLED)
            
            self.add_log(f"--- Connected to {ip}:{port} as '{name}' ---")
            
            # Start Listener Thread
            self.thread = threading.Thread(target=self.receive_messages, daemon=True)
            self.thread.start()
            
            # Handle Window Close
            self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        except (socket.error, ValueError) as e:
            self.add_log(f"Connection Error: Could not connect: {e}")
            self.is_connected = False
            if self.client_socket:
                self.client_socket.close()

    def disconnect(self):
        if self.is_connected:
            self.is_connected = False
            try:
                self.client_socket.close()
            except:
                pass
            
            # Reset GUI
            self.connect_button.config(text="Connect")
            self.ip_entry.config(state=tk.NORMAL)
            self.port_entry.config(state=tk.NORMAL)
            self.name_entry.config(state=tk.NORMAL)
            
            self.disable_game_controls()
            self.add_log("--- Disconnected from Server ---")

    def receive_messages(self):
        while self.is_connected:
            try:
                msg = self.client_socket.recv(4096).decode()
                
                if not msg:
                    self.master.after(0, self.handle_server_disconnect)
                    break
                
                self.master.after(0, lambda m=msg: self.process_message(m))

            except (socket.error, OSError):
                if self.is_connected: 
                    self.master.after(0, self.handle_server_disconnect)
                break

    def handle_server_disconnect(self):
        self.add_log("--- Connection lost or Server closed ---")
        self.disconnect()

    def process_message(self, message):
        #Parse server messages and update GUI accordingly.
        
        # 1. Check for Error
        if "ERR:" in message:
            clean_msg = message.replace("ERR:", "").strip()
            self.add_log(clean_msg)
            self.disconnect()
            return

        # 2. Check for Question
        if "QUESTION" in message and "A:" in message:
            self.add_log("\n" + "="*30)
            self.add_log(message) 
            self.enable_game_controls()
            return

        # 3. Check for Result/Scoreboard
        if "RESULT" in message or "SCOREBOARD" in message:
            self.add_log("\n" + "-"*30)
            self.add_log(message)
            self.disable_game_controls()
            return
            
        # 4. Check for Game Over
        if "GAME OVER" in message:
            self.add_log("\n" + "*"*30)
            self.add_log(message)
            self.disable_game_controls()
            return

        # Fallback for chat/broadcasts
        self.add_log(message)

    def submit_answer(self):
        if not self.is_connected:
            return

        ans = self.selected_answer.get()
        if not ans:
            self.add_log("Info: Please select an option (A, B, or C).")
            return

        try:
            self.client_socket.sendall(ans.encode())
            self.disable_game_controls()
        except socket.error:
            self.handle_server_disconnect()

    def enable_game_controls(self):
        self.selected_answer.set("") 
        self.rb_a.config(state=tk.NORMAL)
        self.rb_b.config(state=tk.NORMAL)
        self.rb_c.config(state=tk.NORMAL)
        self.submit_btn.config(state=tk.NORMAL)

    def disable_game_controls(self):
        self.rb_a.config(state=tk.DISABLED)
        self.rb_b.config(state=tk.DISABLED)
        self.rb_c.config(state=tk.DISABLED)
        self.submit_btn.config(state=tk.DISABLED)

    def on_closing(self):
        # Handle window 'X' button.
        self.disconnect()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = QuizClient(root)
    root.mainloop()