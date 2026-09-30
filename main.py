import customtkinter as ctk
from models import StudentUser
from views import Sidebar, DashboardView, SearchView, ConsultationsView

ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("green")  

# main controller
class AppController(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Queue&A")
        self.geometry("900x600")
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # student initialize
        self.current_user = StudentUser(name="Name", student_id="2025130950")

        self.sidebar = Sidebar(self, navigate_callback=self.switch_view)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.content_area = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_area.grid(row=0, column=1, sticky="nsew")
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        self.views = {
            "dashboard": DashboardView(self.content_area, self.current_user),
            "search": SearchView(self.content_area),
            "consultations": ConsultationsView(self.content_area)
        }

        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self.switch_view("dashboard")

    def switch_view(self, view_name: str):
        """Handles the logic of switching screens and updating UI state."""
        self.sidebar.highlight_active(view_name)
        active_view = self.views[view_name]
        active_view.tkraise()

if __name__ == "__main__":
    app = AppController()
    app.mainloop()