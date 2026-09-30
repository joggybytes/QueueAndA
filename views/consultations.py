import customtkinter as ctk

class ConsultationsView(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        
        ctk.CTkLabel(self, text="My Consultations", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=20, pady=(20, 10))
        
        self.current_tab = ctk.StringVar(value="Pending")
        self.tabs = ctk.CTkSegmentedButton(
            self, values=["Pending", "Accepted", "History"], 
            variable=self.current_tab, command=self.switch_tab
        )
        self.tabs.pack(fill="x", padx=20, pady=10)
        
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.switch_tab("Pending")

    def switch_tab(self, tab_name):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        if tab_name == "Pending":
            self.create_mock_card("TeacherName1", "CODE101 - Consultation Description", "Waiting for approval...", "orange")
            self.create_mock_card("TeacherName2", "CODE200 - Consultation Description", "Waiting for approval...", "orange")
            
        elif tab_name == "Accepted":
            self.create_mock_card("TeacherName3", "CODE103 - Consultation Description", "Scheduled: Today, 2:30 PM", "green")
            
        elif tab_name == "History":
            self.create_mock_card("TeacherName4", "CODE105 - Consultation Description", "Completed: 4/12", "gray")

    def create_mock_card(self, teacher, topic, status, status_color):
        card = ctk.CTkFrame(self.list_frame)
        card.pack(fill="x", pady=5)
        
        ctk.CTkLabel(card, text=teacher, font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w", padx=15, pady=(10, 0))
        ctk.CTkLabel(card, text=topic).pack(anchor="w", padx=15)
        
        status_label = ctk.CTkLabel(card, text=status, text_color=status_color, font=ctk.CTkFont(weight="bold"))
        status_label.pack(anchor="w", padx=15, pady=(0, 10))