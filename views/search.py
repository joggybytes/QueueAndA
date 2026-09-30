# views/search.py
import customtkinter as ctk
from models import MOCK_TEACHERS

class BookingModal(ctk.CTkToplevel):
    def __init__(self, parent, teacher_name):
        super().__init__(parent)
        self.title(f"Book Consultation with {teacher_name}")
        self.geometry("400x350")
        
        self.attributes("-topmost", True)
        
        ctk.CTkLabel(self, text=f"Booking: {teacher_name}", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        ctk.CTkLabel(self, text="Select Course:").pack(anchor="w", padx=20)
        ctk.CTkOptionMenu(self, values=["Course 1", "Course 2"]).pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(self, text="Reason for meeting:").pack(anchor="w", padx=20)
        self.reason_text = ctk.CTkTextbox(self, height=80)
        self.reason_text.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkButton(self, text="Submit Request", command=self.destroy).pack(pady=10)


class SearchView(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        
        ctk.CTkLabel(self, text="Find a Teacher", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=20, pady=(20, 10))
        
        search_container = ctk.CTkFrame(self, fg_color="transparent")
        search_container.pack(fill="x", padx=20, pady=10)
        
        self.search_entry = ctk.CTkEntry(search_container, placeholder_text="Search by name...", width=300)
        self.search_entry.pack(side="left", padx=(0, 10))
        
        self.search_entry.bind("<KeyRelease>", self.update_results)
        
        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.populate_list(MOCK_TEACHERS)

    def populate_list(self, teachers):
        for widget in self.results_frame.winfo_children():
            widget.destroy()
            
        for teacher in teachers:
            card = ctk.CTkFrame(self.results_frame)
            card.pack(fill="x", pady=5)
            
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", padx=15, pady=10)
            
            ctk.CTkLabel(info_frame, text=teacher.name, font=ctk.CTkFont(weight="bold", size=16)).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=f"{teacher.department} | {', '.join(teacher.courses)}", text_color="gray").pack(anchor="w")
            
            btn = ctk.CTkButton(card, text="Book", width=80, command=lambda t=teacher.name: self.open_booking_modal(t))
            btn.pack(side="right", padx=15)

    def update_results(self, event=None):
        query = self.search_entry.get().lower()
        filtered = [t for t in MOCK_TEACHERS if query in t.name.lower() or query in t.department.lower()]
        self.populate_list(filtered)

    def open_booking_modal(self, teacher_name):
        BookingModal(self, teacher_name)