# Queue&A

## Project Description
Queue&A is a Python OOP application that helps students
book consultations with their teachers. Teachers publish
their available schedules, and students request, track and
join those consultations in one place.

## High-Priority Features
1. Login and sign-up for students and teachers
2. Publishing available consultation schedules
3. Searching teachers by name or course and booking a consultation
4. Accepting requests with a meeting link, or declining them
5. Role-based dashboards with booking status
6. Consultation history

## Technologies Used
- Python
- Streamlit
- Supabase
- PostgreSQL

## OOP Implementation Examples
- Encapsulation: A booking's status and a user's password hash are private and change only through methods such as `accept()`, `cancel()` and `set_password()`.
- Inheritance: Teacher and Student extend User; TeacherView and StudentView extend BaseView.
- Polymorphism: `view_dashboard()` and `view_history()` show different bookings for teachers and students.
- Abstraction: User, DataStore and BaseView are abstract classes, and the controllers hide the booking rules behind simple methods.

## Project Structure
- models/: Application classes and database access
- views/: User interface
- controllers/: Application operations
- utils/: Date and time helpers
- assets/: Logos and icons
- supabase/: Database setup script
- app.py: Main Python file

## Installation
1. Download or clone the repository.
2. Create and activate a Python environment.
3. Install the required packages.
   ```
   pip install -r requirements.txt
   ```
4. Configure the application.
   - In your Supabase project, open the SQL Editor and run `supabase/schema.sql`.
   - Create `.streamlit/secrets.toml` with your Supabase details (this file is not uploaded to GitHub):
     ```
     [supabase]
     url = "enter your url"
     key = "enter your key"

     [app]
     timezone = "Asia/Manila"
     ```
5. Run the main Python file via terminal.
   ```
   streamlit run app.py
   ```

## Developers
- Cesar Leonardo M. Europa
