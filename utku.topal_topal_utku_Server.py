import tkinter as tk
from tkinter import messagebox
import socket
import threading
import time

class QuizServer:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Quiz Game Server")
        
        # Grid Configuration
        master.grid_columnconfigure(index=list(range(2)), weight=1)
        master.grid_rowconfigure(index=4, weight=1) 

        # Network & Game Variables
        self.server_socket = None
        self.is_listening = False
        self.game_started = False
        
        # Clients: {socket: {'name': str, 'score': int, 'address': addr}}
        self.clients = {} 
        
        # Store disconnected players to keep their scores
        self.disconnected_clients = [] 
        
        # Game State
        self.questions = []         
        self.current_q_index = 0    
        self.questions_asked_count = 0 
        self.total_questions_limit = 0 
        
        # Round State
        self.current_round_answers = {} 
        self.correct_answer_current = ""
        self.bonus_awarded = False
        self.fixed_game_bonus = 0
        
        # MUTEX
        self.lock = threading.Lock() 

        self.create_widgets()

    def create_widgets(self):
        # Row 0: Port
        tk.Label(self.master, text="Port:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.port_entry = tk.Entry(self.master)
        self.port_entry.insert(0, "12345")
        self.port_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # Row 1: Question File
        tk.Label(self.master, text="Question File (txt):").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.file_entry = tk.Entry(self.master)
        self.file_entry.insert(0, "quiz_qa.txt")
        self.file_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Row 2: Number of Questions
        tk.Label(self.master, text="Number of Questions:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.num_q_entry = tk.Entry(self.master)
        self.num_q_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Row 3: Buttons
        btn_frame = tk.Frame(self.master)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        self.listen_button = tk.Button(btn_frame, text="Start Listening", command=self.toggle_listening, width=15)
        self.listen_button.pack(side=tk.LEFT, padx=10)

        self.start_game_button = tk.Button(btn_frame, text="Start Game", command=self.start_game, state=tk.DISABLED, width=15)
        self.start_game_button.pack(side=tk.LEFT, padx=10)

        # Row 4: Log Display
        self.text_widget = tk.Text(self.master, state=tk.DISABLED)
        self.text_widget.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

    def add_message_to_text(self, message):
        # Thread-safe logging to the GUI.
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, message + "\n")
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.yview(tk.END)

    def toggle_listening(self):
        if self.is_listening:
            self.stop_server()
        else:
            self.start_listening()

    def start_listening(self):
        # Point 2: Port not hardcoded
        port_str = self.port_entry.get()
        if not port_str.isdigit():
            self.add_message_to_text("Error: Port must be a number.")
            return

        try:
            port = int(port_str)
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(('0.0.0.0', port))
            self.server_socket.listen(5)
            
            self.is_listening = True
            self.listen_button.config(text="Stop Server")
            self.start_game_button.config(state=tk.NORMAL)
            self.add_message_to_text(f"--- Server listening on port {port} ---")
            
            # Start Accept Thread
            self.thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.thread.start()
            
            # Point 13: Handle window closing cleanly
            self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
            
        except Exception as e:
            self.add_message_to_text(f"Server Error: Could not start server: {e}")

    def stop_server(self):
        self.is_listening = False
        self.game_started = False
        
        # LOCK: Protecting client list while closing sockets
        self.lock.acquire()
        try:
            for sock in list(self.clients.keys()):
                sock.close()
            self.clients.clear()
        finally:
            self.lock.release()
        
        if self.server_socket:
            self.server_socket.close()
        
        self.listen_button.config(text="Start Listening")
        self.start_game_button.config(state=tk.DISABLED)
        self.add_message_to_text("--- Server stopped ---")

    def accept_connections(self):
        # Point 3: Handle multiple clients
        while self.is_listening:
            try:
                client_sock, addr = self.server_socket.accept()
                
                # Handshake (Receive Name)
                try:
                    name = client_sock.recv(1024).decode().strip()
                except:
                    client_sock.close()
                    continue

                # Point 8: No new connections if game started
                if self.game_started:
                    self.add_message_to_text(f"User '{name}' ({addr[0]}) tried to connect to an active game.")
                    msg = "ERR: Game is not finished, still going you can't join."
                    client_sock.send(msg.encode())
                    client_sock.close()
                    continue

                # Point 7: Unique names check
                self.lock.acquire()
                try:
                    existing_names = [data['name'] for data in self.clients.values()]
                    if name in existing_names:
                        client_sock.send("ERR: Name already taken.\n".encode())
                        client_sock.close()
                        self.add_message_to_text(f"Rejected connection from {addr}: Name '{name}' exists.")
                        self.lock.release()
                        continue
                    
                    self.clients[client_sock] = {'name': name, 'score': 0, 'address': addr}
                    self.add_message_to_text(f"Client connected: {name} ({addr[0]})")
                    client_sock.send("WELCOME: You are connected.\n".encode())
                except:
                    if self.lock.locked():
                        self.lock.release()
                    continue
                
                if self.lock.locked():
                    self.lock.release()

                # Start Client Handler
                client_thread = threading.Thread(target=self.handle_client, args=(client_sock, name), daemon=True)
                client_thread.start()

            except OSError:
                break

    def handle_client(self, client_socket, name):
        while True:
            try:
                msg = client_socket.recv(1024).decode().strip()
                if not msg:
                    break 
                
                if self.game_started:
                    self.process_client_answer(client_socket, msg)
                else:
                    pass 

            except (socket.error, ConnectionResetError):
                break
        
        self.remove_client(client_socket, name)

    def load_questions(self, filename):
        self.add_message_to_text(f"Attempting to load file: {filename}...")
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                lines = [line.strip() for line in f if line.strip()]

            if len(lines) == 0:
                self.add_message_to_text("ERROR: File is empty.")
                return False, "File is empty."

            # Point 5 (File Check): structure spans 5 lines
            if len(lines) % 5 != 0:
                self.add_message_to_text(f"ERROR: File has {len(lines)} lines, which is not divisible by 5.")
                return False, "File format incorrect (lines not divisible by 5)."

            self.questions = []
            for i in range(0, len(lines), 5):
                q_text = lines[i]
                op_a = lines[i+1].split('-', 1)[-1].strip() 
                op_b = lines[i+2].split('-', 1)[-1].strip()
                op_c = lines[i+3].split('-', 1)[-1].strip()
                ans_line = lines[i+4]
                if ':' in ans_line:
                    ans = ans_line.split(':', 1)[-1].strip().upper()
                else:
                    ans = ans_line.strip().upper()

                q_dict = {
                    'text': q_text,
                    'A': op_a,
                    'B': op_b,
                    'C': op_c,
                    'answer': ans
                }
                self.questions.append(q_dict)

            self.add_message_to_text(f"SUCCESS: Loaded {len(self.questions)} questions successfully.")
            return True, f"Loaded {len(self.questions)} questions."

        except FileNotFoundError:
             self.add_message_to_text(f"ERROR: File '{filename}' not found.")
             return False, "File not found."

        except Exception as e:
            self.add_message_to_text(f"ERROR: Failed to load file. {e}")
            return False, str(e)

    def start_game(self):
        # Point 5: Start manually if >= 2 players
        if len(self.clients) < 2:
            self.add_message_to_text("Error: Need at least 2 players to start.")
            return

        filename = self.file_entry.get()
        success, msg = self.load_questions(filename)
        
        if not success:
            self.add_message_to_text(f"File Error: {msg}")
            return
            
        if not self.questions:
            self.add_message_to_text("Error: No questions loaded. Check file format.")
            return
        
        num_q_str = self.num_q_entry.get().strip()
        if not num_q_str:
            self.add_message_to_text("Error: Number of questions can't be blank.")
            return

        try:
            requested_limit = int(num_q_str)
            if requested_limit <= 0:
                self.add_message_to_text("Error: Number of questions must be greater than 0.")
                return
            if requested_limit > len(self.questions):
                # Point 6: Verbose error
                self.add_message_to_text(f"Error: You asked for {requested_limit} questions, but file only has {len(self.questions)}.")
                return

            self.total_questions_limit = requested_limit
            
        except ValueError:
            self.add_message_to_text("Error: Invalid number of questions (must be a number).")
            return

        # LOCK: Initializing game state
        self.lock.acquire()
        try:
            self.game_started = True
            self.start_game_button.config(state=tk.DISABLED)
            self.current_q_index = 0
            self.questions_asked_count = 0
            self.disconnected_clients = []
            
            # Bonus logic: N - 1 ->> N is the number of Clients active in the start game
            # Because any client can leave at the first question without answering.
            self.fixed_game_bonus = max(0, len(self.clients) - 1)
            
            for sock in self.clients:
                self.clients[sock]['score'] = 0
        finally:
            self.lock.release()

        self.add_message_to_text(f"--- Game Started with {len(self.clients)} players. Bonus fixed at +{self.fixed_game_bonus}. ---")
        self.broadcast_scoreboard(initial=True)
        self.master.after(1000, self.ask_next_question)

    def ask_next_question(self):
        try:
            self.lock.acquire()
            
            # Point 12: End if limit of questions are reached
            if self.questions_asked_count >= self.total_questions_limit:
                self.add_message_to_text("Game Limit Reached. Ending Game.")
                self.lock.release()
                self.end_game() 
                return

            # Point 12: End if < 2 players
            if len(self.clients) < 2:
                self.add_message_to_text("Not enough players to continue. Ending Game.")
                self.lock.release()
                self.end_game()
                return

            if not self.questions:
                self.add_message_to_text("ERROR: Question list is empty! Cannot ask question.")
                self.lock.release()
                self.end_game()
                return

            # Reuse questions logic
            q_idx = self.current_q_index % len(self.questions)
            q_data = self.questions[q_idx]
            self.correct_answer_current = q_data['answer']
            
            msg = (f"QUESTION\n{q_data['text']}\n"
                   f"A: {q_data['A']}\n"
                   f"B: {q_data['B']}\n"
                   f"C: {q_data['C']}")
            
            self.current_round_answers = {}
            self.bonus_awarded = False
            
            self.add_message_to_text(f"Asking Q{self.questions_asked_count + 1}: {q_data['text']}")
            
            self._broadcast_helper(msg) 
            
            self.current_q_index += 1
            self.questions_asked_count += 1
            
            self.lock.release()
            
        except Exception as e:
            if self.lock.locked():
                self.lock.release()
            self.add_message_to_text(f"CRITICAL ERROR in ask_next_question: {e}")
            import traceback
            traceback.print_exc()

    def process_client_answer(self, client_socket, answer):
        self.lock.acquire()
        try:
            if client_socket not in self.current_round_answers:
                user_answer = answer.upper()
                name = self.clients[client_socket]['name']
                
                is_correct = (user_answer == self.correct_answer_current)
                points_earned = 0
                status_msg = "WRONG"
                
                if is_correct:
                    points_earned = 1 
                    status_msg = "CORRECT"
                    
                    if not self.bonus_awarded:
                        points_earned += self.fixed_game_bonus
                        self.bonus_awarded = True 
                        status_msg += f" (First! +{self.fixed_game_bonus} bonus)"
                
                log_status = "CORRECT" if is_correct else "WRONG"
                self.add_message_to_text(f"Received answer from {name} is {user_answer} - {log_status} (+{points_earned})")

                self.clients[client_socket]['score'] += points_earned
                
                self.current_round_answers[client_socket] = {
                    'answer': user_answer,
                    'time': time.time()
                }
                
                # Personalized message --> for the clients each of them is unique for the single client
                feedback_msg = (f"You submitted: {user_answer}\n"
                                f"That is {status_msg}.\n"
                                f"You got {points_earned} points from this question.")
                
                try:
                    client_socket.send(feedback_msg.encode())
                except:
                    pass

                # Check if all currently connected players have answered
                remaining_sockets = set(self.clients.keys())
                answered_sockets = set(self.current_round_answers.keys())
                
                if remaining_sockets.issubset(answered_sockets):
                    self.lock.release()
                    self.calculate_scores_and_proceed()
                    return

            self.lock.release()
        except:
            if self.lock.locked():
                self.lock.release()

    def calculate_scores_and_proceed(self):
        self.lock.acquire()
        try:
            # Point 10: Send scoreboard after every question
            sb_text = self.generate_scoreboard_text()
            self.add_message_to_text(sb_text)
            
            self._broadcast_helper(f"RESULT\nRound Over. Here are the standings:\n{sb_text}")
            self.add_message_to_text("Round complete. Scoreboard broadcasted.")
        finally:
            self.lock.release()
            
        threading.Timer(2.0, self.ask_next_question).start()

    def generate_scoreboard_text(self):
        active_list = []
        for sock, data in self.clients.items():
            entry = data.copy()
            entry['is_active'] = True
            active_list.append(entry)

        disco_list = []
        for data in self.disconnected_clients:
            entry = data.copy()
            entry['is_active'] = False
            disco_list.append(entry)

        all_players = active_list + disco_list
        sorted_clients = sorted(all_players, key=lambda x: x['score'], reverse=True)
        
        sb = "--- SCOREBOARD ---\n"
        rank = 1
        
        # Point 11: Tie breaking logic ->> If the clients are at the same points, they should be at the same place in the leaderboard
        # For example, 
        # 1- User 1 - 1 points
        # 1- User 3 - 1 points
        # 2- User 2 - 0 points
        for i in range(len(sorted_clients)):
            client = sorted_clients[i]
            
            if i > 0 and client['score'] == sorted_clients[i-1]['score']:
                display_rank = rank 
            else:
                rank = i + 1
                display_rank = rank
            
            suffix = ""
            if not client['is_active']:
                suffix = " -> disconnected"
            
            sb += f"{display_rank}. {client['name']}{suffix}: {client['score']}\n"
        return sb

    def broadcast_scoreboard(self, initial=False):
        self.lock.acquire()
        try:
            sb = self.generate_scoreboard_text()
            prefix = "GAME START\n" if initial else ""
            self._broadcast_helper(f"{prefix}{sb}")
        finally:
            self.lock.release()

    def broadcast(self, message):
        self.lock.acquire()
        try:
            self._broadcast_helper(message)
        finally:
            self.lock.release()

    def _broadcast_helper(self, message):
        for sock in list(self.clients.keys()):
            try:
                sock.send(message.encode())
            except:
                pass

    def end_game(self):
        # Point 12: Terminate active connections, but server remains open
        self.lock.acquire()
        try:
            self.game_started = False
            self.add_message_to_text("--- Game Over ---")
            
            # Point 11: Final Scoreboard
            final_sb = self.generate_scoreboard_text()
            msg = f"GAME OVER\nFinal Standings:\n{final_sb}"
            
            self._broadcast_helper(msg)
            
            for sock in list(self.clients.keys()):
                try:
                    sock.close()
                except:
                    pass
            self.clients.clear()
            
            self.start_game_button.config(state=tk.NORMAL)
            self.add_message_to_text("All clients disconnected. Ready for new game.")
        finally:
            self.lock.release()

    def remove_client(self, client_socket, name):
        self.lock.acquire()
        try:
            if client_socket in self.clients:
                current_score = self.clients[client_socket]['score']
                self.disconnected_clients.append({'name': name, 'score': current_score})

                del self.clients[client_socket]
                self.add_message_to_text(f"Client '{name}' disconnected.")
                
                if self.game_started:
                    msg = f"ALERT: Player '{name}' has disconnected."
                    self._broadcast_helper(msg)
                    
                    # Point 12: If < 2 players remain, game ends
                    if len(self.clients) < 2:
                         should_end = False
                         should_proceed = False
                         
                         if self.current_round_answers:
                             # If the disconnected player was the only one we were waiting for,
                             # finish the round immediately so the game doesn't get stuck.
                             if len(self.current_round_answers) >= len(self.clients):
                                 should_proceed = True
                         else:
                             should_end = True
                        
                         self.lock.release()
                         
                         if should_proceed:
                             self.calculate_scores_and_proceed()
                         elif should_end:
                             self.end_game()
                         return
                    else:
                        # Check if round can proceed with remaining players
                        remaining_sockets = set(self.clients.keys())
                        answered_sockets = set(self.current_round_answers.keys())
                        if remaining_sockets.issubset(answered_sockets):
                            self.lock.release()
                            self.calculate_scores_and_proceed()
                            return

            if self.lock.locked():
                self.lock.release()
        except:
            if self.lock.locked():
                self.lock.release()

    # Point 13: Clean Termination
    def on_closing(self):
        if self.is_listening:
            self.stop_server()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = QuizServer(root)
    root.mainloop()