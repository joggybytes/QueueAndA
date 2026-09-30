import customtkinter as ctk
from models import StudentUser

class DashboardView(ctk.CTkFrame):
    def __init__(self, parent, student: StudentUser):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        
        ctk.CTkLabel(self, text=f"Welcome back, {student.name}!", font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(self, text="Here is your schedule for today.", text_color="gray").pack(anchor="w", padx=20, pady=(0, 20))
        
        card = ctk.CTkFrame(self, corner_radius=10)
        card.pack(fill="x", padx=20, pady=10)
        
        header_frame = ctk.CTkFrame(card, fg_color="transparent")
        header_frame.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(header_frame, text="Next Consultation", font=ctk.CTkFont(weight="bold", size=16), text_color="#3498db").pack(side="left")
        ctk.CTkLabel(header_frame, text="Today, 2:30 PM", font=ctk.CTkFont(weight="bold")).pack(side="right")
        
        ctk.CTkLabel(card, text="Teacher: TeacherName", font=ctk.CTkFont(size=18)).pack(anchor="w", padx=15, pady=5)
        ctk.CTkLabel(card, text="Topic: CODE101 - Consultation Description", text_color="gray").pack(anchor="w", padx=15)
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkButton(btn_frame, text="Reschedule", fg_color="transparent", border_width=1, text_color=("gray10", "gray90")).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="Join Virtual Room").pack(side="right")