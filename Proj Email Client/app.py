import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import bcrypt

# Setup Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Google Sheets API Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Google Sheets
spreadsheet_id = '#########################'
students_sheet = client.open_by_key(spreadsheet_id).worksheet("Students")
documents_sheet = client.open_by_key(spreadsheet_id).worksheet("Documents")
staff_sheet = client.open_by_key(spreadsheet_id).worksheet("Staff")

# Helper: Send Email
def send_email(to_email, subject, body):
    from_email = "My.Gmail@gmail.com"  # Enter Your Respected Mail ID Here
    password = "Mail.Password"  # Use App-Specific Password if 2FA is enabled (or) without 2FA 

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # Start TLS encryption
            server.login(from_email, password)  # Login using the sender's credentials
            server.sendmail(from_email, to_email, msg.as_string())  # Send the email
            print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Error: {e}")
        return str(e)  # Return error message for debugging

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import mimetypes

# Google Drive Folder ID (replace with your folder ID)
DRIVE_FOLDER_ID = "FULL.ID" 

# Authenticate Google Drive API
def authenticate_drive_api():
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', 
        ['https://www.googleapis.com/auth/drive'])
    service = build('drive', 'v3', credentials=creds)
    return service

drive_service = authenticate_drive_api()

# Upload file to Google Drive
def upload_to_drive(file_path, file_name, folder_id=DRIVE_FOLDER_ID):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]  # Specify the folder to upload into
    }
    # Determine MIME type of the file
    mime_type = mimetypes.guess_type(file_path)[0]
    media = MediaFileUpload(file_path, mimetype=mime_type)

    # Upload the file
    try:
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        print(f"File uploaded successfully: {file['webViewLink']}")
        return file['webViewLink']
    except Exception as e:
        print(f"Error uploading file: {e}")
        return None


# Route for Home Page
@app.route('/')
def home():
    return render_template('home.html')

# Route for Login Page

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']

        if user_type == 'student':
            # Find student by email
            student_cell = students_sheet.find(email)
            if student_cell:
                student_row = students_sheet.row_values(student_cell.row)
                stored_password = student_row[6]  # The hashed password is in the 7th column (index 6) #

                # Verify password using bcrypt (for students)
                if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                    session['user'] = 'student'
                    session['email'] = email
                    # Redirect based on education level (UG or PG)
                    education = student_row[7]  # Education is in the 8th column
                    if education == 'UG':
                        return redirect('/student_dashboard_UG')
                    elif education == 'PG':
                        return redirect('/student_dashboard_PG')
                else:
                    return "Incorrect password!", 400

        elif user_type == 'staff':
            # Find staff by email
            staff_cell = staff_sheet.find(email)
            if staff_cell:
                staff_row = staff_sheet.row_values(staff_cell.row)
                stored_phone_number = staff_row[1]  # Staff phone number is in the 2nd column

                # For staff, the password is the phone number (no encryption)
                if password == stored_phone_number:
                    session['user'] = 'staff'
                    return redirect('/staff_dashboard_select')
                else:
                    return "Incorrect password!", 400

    return render_template('login.html')


# Uploads folder
from flask import send_from_directory

# Route for Student Dashboard
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'  # The folder where files will be stored
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':
        student_email = session['email']
        file_paths = {}
        education = request.form['education']  # Get education level from form

        # Choose the correct sheet based on the selected education
        if education == 'UG':
            documents_sheet = client.open_by_key(spreadsheet_id).worksheet("UG Documents")
        else:
            documents_sheet = client.open_by_key(spreadsheet_id).worksheet("PG Documents")

        # Process file uploads
        for file_key in ['marksheets', 'passport', 'pan_card', 'id_card', 'transfer_certificate']:
            file = request.files[file_key]
            if file and allowed_file(file.filename):
                filename = f"{secure_filename(student_email)}_{file_key}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                file_paths[file_key] = f"{request.host_url}uploads/{filename}"
            else:
                file_paths[file_key] = 'Not Uploaded'

        # Append the documents to the selected sheet based on education level
        documents_sheet.append_row([student_email, 
                                    file_paths['marksheets'], 
                                    file_paths['passport'], 
                                    file_paths['pan_card'], 
                                    file_paths['id_card'], 
                                    file_paths['transfer_certificate'], 
                                    'Not Verified'])

        return redirect('/application_status')

    return render_template('student_dashboard.html')

## ROUTE FOR STUDENT_DASHBOARD_UG

import os
from flask import send_from_directory, flash


UPLOAD_FOLDER = 'uploads' 
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/student_dashboard_UG', methods=['GET', 'POST'])
def student_dashboard_UG():
    if 'user' not in session:
        return redirect('/login')

    student_email = session['email']
    ug_sheet = client.open_by_key(spreadsheet_id).worksheet("UG Documents")
    
    student_cell = ug_sheet.find(student_email)
    if student_cell:
        student_row = ug_sheet.row_values(student_cell.row)
        existing_data = {
            "certificate": student_row[1] if len(student_row) > 1 else "Not Uploaded",
            "reference_letter": student_row[2] if len(student_row) > 2 else "Not Uploaded",
            "transcript": student_row[3] if len(student_row) > 3 else "Not Uploaded",
            "verification_status": student_row[4] if len(student_row) > 4 else "Not Verified"
        }
        resubmission_mode = True
    else:
        existing_data = {
            "certificate": "Not Uploaded",
            "reference_letter": "Not Uploaded",
            "transcript": "Not Uploaded",
            "verification_status": "Not Verified"
        }
        resubmission_mode = False

    if request.method == 'POST':
        file_paths = {}
        for file_key in ['certificate', 'reference_letter', 'transcript']:
            file = request.files[file_key]
            if file and allowed_file(file.filename):
                filename = f"{secure_filename(student_email)}_{file_key}_{secure_filename(file.filename)}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)  # Save temporarily

                # Upload to Drive
                drive_link = upload_to_drive(file_path, filename)
                if drive_link:
                    file_paths[file_key] = drive_link
                else:
                    file_paths[file_key] = "Error uploading to Drive"
                os.remove(file_path)  # Remove temporary local file
            else:
                file_paths[file_key] = existing_data[file_key]

        if resubmission_mode:
            ug_sheet.update(f'A{student_cell.row}:E{student_cell.row}', 
                            [[student_email, file_paths['certificate'], file_paths['reference_letter'], file_paths['transcript'], 'Not Verified']])
            flash("Documents resubmitted successfully!", "success")
        else:
            ug_sheet.append_row([student_email, file_paths['certificate'], file_paths['reference_letter'], file_paths['transcript'], 'Not Verified'])
            flash("Documents submitted successfully!", "success")

        return redirect('/student_dashboard_UG')

    return render_template('student_dashboard_UG.html', existing_data=existing_data, resubmission_mode=resubmission_mode)

from urllib.parse import urlparse

@app.route('/student_dashboard_PG', methods=['GET', 'POST'])
def student_dashboard_PG():
    if 'user' not in session:
        return redirect('/login')

    student_email = session['email']
    pg_sheet = client.open_by_key(spreadsheet_id).worksheet("PG Documents")
    
    student_cell = pg_sheet.find(student_email)
    if student_cell:
        student_row = pg_sheet.row_values(student_cell.row)
        existing_data = {
            "ug_degree_certificate": student_row[1] if len(student_row) > 1 else "Not Uploaded",
            "ug_degree_transcript": student_row[2] if len(student_row) > 2 else "Not Uploaded",
            "reference_letter_1": student_row[3] if len(student_row) > 3 else "Not Uploaded",
            "reference_letter_2": student_row[4] if len(student_row) > 4 else "Not Uploaded",
            "english_language_certificate": student_row[5] if len(student_row) > 5 else "Not Uploaded",
            "verification_status": student_row[6] if len(student_row) > 6 else "Not Verified"
        }
        resubmission_mode = True
    else:
        existing_data = {
            "ug_degree_certificate": "Not Uploaded",
            "ug_degree_transcript": "Not Uploaded",
            "reference_letter_1": "Not Uploaded",
            "reference_letter_2": "Not Uploaded",
            "english_language_certificate": "Not Uploaded",
            "verification_status": "Not Verified"
        }
        resubmission_mode = False

    if request.method == 'POST':
        file_paths = {}
        for file_key in ['ug_degree_certificate', 'ug_degree_transcript', 'reference_letter_1', 'reference_letter_2', 'english_language_certificate']:
            file = request.files.get(file_key)
            if file and allowed_file(file.filename):
                filename = f"{secure_filename(student_email)}_{file_key}_{secure_filename(file.filename)}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)  # Save temporarily

                # Upload to Drive
                drive_link = upload_to_drive(file_path, filename)
                if drive_link:
                    file_paths[file_key] = drive_link
                else:
                    file_paths[file_key] = "Error uploading to Drive"
                os.remove(file_path)  # Remove temporary local file
            else:
                file_paths[file_key] = existing_data.get(file_key, "Not Uploaded")

        if resubmission_mode:
            pg_sheet.update(f'A{student_cell.row}:G{student_cell.row}', 
                            [[student_email, file_paths['ug_degree_certificate'], file_paths['ug_degree_transcript'], file_paths['reference_letter_1'], file_paths['reference_letter_2'], file_paths['english_language_certificate'], 'Not Verified']])
            flash("Documents resubmitted successfully!", "success")
        else:
            pg_sheet.append_row([student_email, file_paths['ug_degree_certificate'], file_paths['ug_degree_transcript'], file_paths['reference_letter_1'], file_paths['reference_letter_2'], file_paths['english_language_certificate'], 'Not Verified'])
            flash("Documents submitted successfully!", "success")

        return redirect('/student_dashboard_PG')

    return render_template('student_dashboard_PG.html', existing_data=existing_data, resubmission_mode=resubmission_mode)

@app.route('/application_status', methods=['GET'])
def application_status():
    if 'user' not in session:
        return redirect('/login')

    student_email = session['email']
    from_page = request.args.get('page', 'UG')  # Default to UG if no page parameter is provided

    # Determine the correct worksheet and columns based on the page
    if from_page == 'PG':
        worksheet = client.open_by_key(spreadsheet_id).worksheet("PG Documents")
        document_columns = [
            ("UG Degree Certificate", 1),
            ("UG Degree Transcript", 2),
            ("Reference Letter 1", 3),
            ("Reference Letter 2", 4),
            ("English Language Certificate", 5),
        ]
    else:  # UG page
        worksheet = client.open_by_key(spreadsheet_id).worksheet("UG Documents")
        document_columns = [
            ("Certificate(s)", 1),
            ("Reference Letter", 2),
            ("Transcript", 3),
        ]

    # Find the student row
    student_cell = worksheet.find(student_email)
    if student_cell:
        student_row = worksheet.row_values(student_cell.row)
        verification_status = student_row[-1] if len(student_row) >= len(document_columns) + 2 else "Not Verified"

        document_links = {}
        for doc_name, col_index in document_columns:
            document_links[doc_name] = student_row[col_index] if len(student_row) > col_index else "Not Uploaded"
    else:
        document_links = {doc_name: "Not Uploaded" for doc_name, _ in document_columns}
        verification_status = "Not Verified"

    return render_template(
        'application_status.html',
        document_links=document_links,
        verification_status=verification_status,
        from_page=from_page
    )

## Route for Staff Dashboard: Documents Verification
@app.route('/staff_dashboard_select', methods=['GET', 'POST'])
def staff_dashboard_select():
    if 'user' not in session or session['user'] != 'staff':
        return redirect('/login')

    # Courses grouped by UG and PG
    courses = {
        'UG': [
            "Computer Networks BSc (Hons)",
            "Computer Science MEng/ BSc (Hons)",
            "Computer Science and Advanced Technologies BSc",
            "Computing and Information Systems (Distance learning) BSc (Hons)",
            "Computing BSc (Hons)",
            "Cyber Security and Forensic Computing BSc (Hons)",
            "Data Science and Analytics BSc (Hons)",
            "Software Engineering BSc (Hons)"
        ],
        'PG': [
            "Artificial Intelligence and Machine Learning MSc",
            "Computer Network Administration and Management MSc",
            "Cyber Security and Forensic Information Technology MSc",
            "Data Analytics MSc",
            "Information Systems MSc",
            "Computing MPhil and PhD"
        ]
    }

    if request.method == 'POST':
        selected_education = request.form['education']
        selected_course = request.form['course']

        # Determine the correct worksheet based on the education type
        document_worksheet_name = "UG Documents" if selected_education == 'UG' else "PG Documents"
        student_worksheet = students_sheet
        document_worksheet = client.open_by_key(spreadsheet_id).worksheet(document_worksheet_name)

        # Filter students
        students_data = student_worksheet.get_all_records()
        filtered_students = [
            student for student in students_data
            if student['Education'] == selected_education and student['Course'] == selected_course
        ]

        session['filtered_students'] = filtered_students
        session['document_worksheet'] = document_worksheet_name

        return render_template(
            'staff_dashboard_select.html',
            filtered_students=filtered_students,
            courses=courses[selected_education] if selected_education in courses else None
        )

    return render_template('staff_dashboard_select.html', filtered_students=None, courses=None)


@app.route('/staff_dashboard_student/<student_email>', methods=['GET', 'POST'])
def staff_dashboard_student(student_email):
    if 'user' not in session or session['user'] != 'staff':
        return redirect('/login')

    # Fetch student data from the 'Students' sheet
    students_data = students_sheet.get_all_records()
    email_name_map = {
        student['Email']: f"{student['First Name']} {student['Last Name']}"
        for student in students_data
    }
    student_name = email_name_map.get(student_email, student_email)  # Use email if name not found

    # Determine if the student is UG or PG based on the main student sheet
    student_cell = students_sheet.find(student_email)
    if not student_cell:
        return "Student not found.", 404

    student_row = students_sheet.row_values(student_cell.row)
    education = student_row[7]  # Assuming the 8th column contains UG/PG info

    # Determine the corresponding document worksheet
    if education == "UG":
        document_worksheet = client.open_by_key(spreadsheet_id).worksheet("UG Documents")
        document_columns = [
            ("Certificate(s)", 1),
            ("Reference Letter", 2),
            ("Transcript", 3)
        ]
    elif education == "PG":
        document_worksheet = client.open_by_key(spreadsheet_id).worksheet("PG Documents")
        document_columns = [
            ("UG Degree Certificate", 1),
            ("UG Degree Transcript", 2),
            ("Reference Letter 1", 3),
            ("Reference Letter 2", 4),
            ("English Language Certificate", 5)
        ]
    else:
        return "Invalid education type.", 400

    # Fetch document details
    student_document_cell = document_worksheet.find(student_email)
    if not student_document_cell:
        return "Student documents not found.", 404

    student_documents_row = document_worksheet.row_values(student_document_cell.row)
    document_links = {
        doc_name: student_documents_row[col_index] if len(student_documents_row) > col_index else "Not Uploaded"
        for doc_name, col_index in document_columns
    }

    verification_status = (
        student_documents_row[-1] if len(student_documents_row) > len(document_columns) else "Not Verified"
    )

    if request.method == 'POST':
        # Update verification status
        new_status = request.form['verification_status']
        document_worksheet.update_cell(student_document_cell.row, len(document_columns) + 2, new_status)
        return redirect('/staff_dashboard_select')

    return render_template(
        'staff_dashboard_student.html',
        student_name=student_name,
        student_email=student_email,
        education=education,
        document_links=document_links,
        verification_status=verification_status
    )


#ROUTE FOR EMAIL SENDING 

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Email helper function
def send_email(to_email, subject, body):
    from_email = "My.MailID"
    password = "My.Password"  # Use an app-specific password for better security
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
        print(f"Email sent successfully to {to_email}")
        return "Email sent successfully"
    except Exception as e:
        print(f"Error: {e}")
        return str(e)

@app.route('/staff_email_student/<student_email>', methods=['GET', 'POST'])
def staff_email_student(student_email):
    if 'user' not in session or session['user'] != 'staff':
        return redirect('/login')

    students_data = students_sheet.get_all_records()
    student_name = next((f"{s['First Name']} {s['Last Name']}" for s in students_data if s['Email'] == student_email), student_email)

    if request.method == 'POST':
        subject = request.form['subject']
        body = request.form['body']
        result = send_email(student_email, subject, body)
        flash(result)
        return redirect(url_for('staff_dashboard_student', student_email=student_email))

    return render_template('staff_email_student.html', student_email=student_email, student_name=student_name)

#ROUTE FOR REGISTRATION 

students_sheet = client.open_by_key('#####################').worksheet("Students")
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        address = request.form['address']
        phone_number = request.form['phone_number']
        nationality = request.form['nationality']
        education = request.form['education']
        course = request.form['course']
        password = phone_number  # Can be replaced with a separate password field if needed

        # Hash the password before storing it
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Check for existing email or phone number
        existing_email = students_sheet.find(email)
        existing_phone = students_sheet.find(phone_number)

        if existing_email:
            return "An account already exists with this email address.", 400
        elif existing_phone:
            return "An account already exists with this phone number.", 400

        # Add new student to Google Sheets
        students_sheet.append_row([first_name, last_name, email, address, phone_number, nationality, hashed_password.decode('utf-8'), education, course, "", ""])

        return redirect('/login')

    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True)




from flask import Flask, render_template, request, redirect, url_for
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

