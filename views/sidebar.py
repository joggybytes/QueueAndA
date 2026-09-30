import customtkinter as ctk

class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, navigate_callback):
        super().__init__(parent, width=200, corner_radius=0)
        self.navigate_callback = navigate_callback
        self.buttons = {}
        
        self._build_ui()

    def _build_ui(self):
        self.grid_rowconfigure(4, weight=1) 
        
        ctk.CTkLabel(self, text="Queue&A", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, padx=20, pady=(20, 30))
        
        nav_items = {
            "dashboard": "Dashboard",
            "search": "Find Teacher",
            "consultations": "My Consultations"
        }
        
        row_idx = 1
        for key, text in nav_items.items():
            btn = ctk.CTkButton(
                self, text=text, fg_color="transparent", text_color=("gray10", "gray90"), anchor="w",
                command=lambda k=key: self.navigate_callback(k)
            )
            btn.grid(row=row_idx, column=0, padx=10, pady=5, sticky="ew")
            self.buttons[key] = btn
            row_idx += 1
            
        ctk.CTkButton(self, text="Log Out", fg_color="#c0392b", hover_color="#a93226").grid(row=5, column=0, padx=20, pady=20, sticky="ew")

    def highlight_active(self, active_key):
        active_color = ("gray75", "gray25")
        for key, btn in self.buttons.items():
            btn.configure(fg_color=active_color if key == active_key else "transparent")