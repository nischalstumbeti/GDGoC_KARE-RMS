from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import json
import os
import csv
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
import io
import threading
import time
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib import colors

# Import Supabase database functions
from db import (
    get_all_users, get_user, create_user, update_user, delete_user,
    get_all_candidates, get_candidate, create_candidate,
    get_all_checklists, get_checklist, save_checklist,
    init_default_user as db_init_default_user
)

app = Flask(__name__)
# Use environment variable for secret key in production, fallback for development
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'gdg_kare_2026_secret_key_change_in_production')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure directories exist
os.makedirs('data', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Using Supabase database for all data storage

def format_positions(value):
    """Convert JSON string positions to comma-separated string"""
    if not value:
        return value
    try:
        # Try to parse as JSON if it's a JSON string
        if isinstance(value, str) and value.strip().startswith('['):
            positions = json.loads(value)
            if isinstance(positions, list):
                return ', '.join(positions)
        # If it's already a list, join it
        elif isinstance(value, list):
            return ', '.join(value)
        # Otherwise return as is
        return value
    except (json.JSONDecodeError, TypeError):
        # If parsing fails, return original value
        return value

# Register Jinja2 filter
app.jinja_env.filters['format_positions'] = format_positions

def keep_alive_ping():
    """Background thread that pings a URL every 11 minutes to keep the service alive"""
    ping_url = os.getenv('KEEP_ALIVE_URL', None)
    ping_interval = int(os.getenv('KEEP_ALIVE_INTERVAL', 11 * 60))  # Default: 11 minutes in seconds
    
    # If no URL is set, try to construct from environment or use a default
    if not ping_url:
        # Try to get from Render environment variables or construct from app URL
        render_url = os.getenv('RENDER_EXTERNAL_URL')
        if render_url:
            ping_url = render_url
        else:
            # Default to localhost for development
            ping_url = 'http://localhost:8080'
    
    print(f"Keep-alive thread started. Will ping {ping_url} every {ping_interval // 60} minutes")
    
    while True:
        try:
            time.sleep(ping_interval)
            response = requests.get(ping_url, timeout=10)
            print(f"[Keep-Alive] Pinged {ping_url} - Status: {response.status_code} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except requests.exceptions.RequestException as e:
            print(f"[Keep-Alive] Error pinging {ping_url}: {e}")
        except Exception as e:
            print(f"[Keep-Alive] Unexpected error: {e}")

def start_keep_alive_thread():
    """Start the keep-alive background thread"""
    keep_alive_enabled = os.getenv('KEEP_ALIVE_ENABLED', 'true').lower() == 'true'
    if keep_alive_enabled:
        thread = threading.Thread(target=keep_alive_ping, daemon=True)
        thread.start()
        print("Keep-alive thread initialized")

def init_default_user():
    """Initialize default admin user if it doesn't exist"""
    db_init_default_user()

@app.route('/')
def index():
    """Redirect to login if not authenticated, else dashboard"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        passcode = request.form.get('passcode', '').strip()
        
        user = get_user(user_id)
        
        if user and user['passcode'] == passcode:
            # Get IP address
            ip_address = request.remote_addr
            if request.headers.get('X-Forwarded-For'):
                ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
            
            # Fetch IP geolocation info
            location_info = {'ip': ip_address, 'location': 'Unknown', 'isp': 'Unknown'}
            try:
                # Using ip-api.com (free, no API key required)
                response = requests.get(f'http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city,isp,query', timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success':
                        city = data.get('city', '')
                        region = data.get('regionName', '')
                        country = data.get('country', '')
                        location_parts = [p for p in [city, region, country] if p]
                        location_info['location'] = ', '.join(location_parts) if location_parts else 'Unknown'
                        location_info['isp'] = data.get('isp', 'Unknown')
                        location_info['ip'] = data.get('query', ip_address)
            except:
                pass  # If API fails, use defaults
            
            # Update last login and location info
            update_user(user_id, {
                'last_login': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'ip_address': location_info['ip'],
                'location': location_info['location'],
                'isp': location_info['isp']
            })
            
            # Set session with role and name
            session['user_id'] = user_id
            session['role'] = user.get('role', 'admin')
            session['name'] = user.get('name', user_id)
            session['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            session['ip_address'] = location_info['ip']
            session['location'] = location_info['location']
            session['isp'] = location_info['isp']
            
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid User ID or Passcode')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Display dashboard after login"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    users = get_all_users()
    candidates = get_all_candidates()
    checklists = get_all_checklists()
    
    user_id = session['user_id']
    user_role = session.get('role', 'admin')
    user_name = session.get('name', user_id)
    user_data = users.get(user_id, {})
    last_login = session.get('last_login') or user_data.get('last_login', 'First login')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Get IP, location, ISP from session or user data
    ip_address = session.get('ip_address') or user_data.get('ip_address', 'Unknown')
    location = session.get('location') or user_data.get('location', 'Unknown')
    isp = session.get('isp') or user_data.get('isp', 'Unknown')
    
    # Calculate statistics
    total_candidates = len(candidates)
    total_checklists = len(checklists)
    pending_checklists = total_candidates - total_checklists
    
    return render_template('dashboard.html', 
                         user_id=user_id,
                         user_role=user_role,
                         user_name=user_name,
                         last_login=last_login,
                         current_time=current_time,
                         ip_address=ip_address,
                         location=location,
                         isp=isp,
                         total_candidates=total_candidates,
                         total_checklists=total_checklists,
                         pending_checklists=pending_checklists)

@app.route('/manage_users', methods=['GET', 'POST'])
def manage_users():
    """Admin panel for user management"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    
    users = get_all_users()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            new_user_id = request.form.get('user_id', '').strip()
            new_passcode = request.form.get('passcode', '').strip()
            new_role = request.form.get('role', '').strip()
            new_name = request.form.get('name', '').strip()
            
            if not new_user_id or not new_passcode or not new_role:
                return render_template('manage_users.html', users=users, 
                                     error='All fields are required')
            
            if new_user_id in users:
                return render_template('manage_users.html', users=users, 
                                     error='User ID already exists')
            
            if create_user(new_user_id, new_passcode, new_role, new_name):
                users = get_all_users()  # Refresh users list
                return render_template('manage_users.html', users=users, 
                                     success=f'User {new_user_id} created successfully')
            else:
                return render_template('manage_users.html', users=users, 
                                     error='Failed to create user')
        
        elif action == 'edit':
            edit_user_id = request.form.get('edit_user_id', '').strip()
            new_passcode = request.form.get('edit_passcode', '').strip()
            new_role = request.form.get('edit_role', '').strip()
            new_name = request.form.get('edit_name', '').strip()
            
            if edit_user_id not in users:
                return render_template('manage_users.html', users=users, 
                                     error='User not found')
            
            updates = {}
            if new_passcode:
                updates['passcode'] = new_passcode
            if new_role:
                updates['role'] = new_role
            if new_name:
                updates['name'] = new_name
            
            if updates and update_user(edit_user_id, updates):
                users = get_all_users()  # Refresh users list
                return render_template('manage_users.html', users=users, 
                                     success=f'User {edit_user_id} updated successfully')
            else:
                return render_template('manage_users.html', users=users, 
                                     error='Failed to update user')
        
        elif action == 'delete':
            delete_user_id = request.form.get('delete_user_id', '').strip()
            
            if delete_user_id == 'admin':
                return render_template('manage_users.html', users=users, 
                                     error='Cannot delete admin user')
            
            if delete_user_id not in users:
                return render_template('manage_users.html', users=users, 
                                     error='User not found')
            
            if delete_user(delete_user_id):
                users = get_all_users()  # Refresh users list
                return render_template('manage_users.html', users=users, 
                                     success=f'User {delete_user_id} deleted successfully')
            else:
                return render_template('manage_users.html', users=users, 
                                     error='Failed to delete user')
    
    return render_template('manage_users.html', users=users)

@app.route('/import_candidates', methods=['GET', 'POST'])
def import_candidates():
    """Handle CSV import of candidates"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            return render_template('import_candidates.html', error='No file selected')
        
        file = request.files['csv_file']
        if file.filename == '':
            return render_template('import_candidates.html', error='No file selected')
        
        if not file.filename.endswith('.csv'):
            return render_template('import_candidates.html', error='Invalid file format. Please upload a CSV file.')
        
        try:
            # Read CSV
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)
            
            required_columns = ['Register ID', 'Candidate Name', 'Department', 'Position Applied', 
                              'Day Scholar / Hosteler', 'Phone Number', 'LinkedIn Profile', 'GitHub Profile']
            
            # Validate columns
            if not all(col in csv_reader.fieldnames for col in required_columns):
                return render_template('import_candidates.html', 
                                     error=f'Missing required columns. Required: {", ".join(required_columns)}')
            
            candidates = get_all_candidates()
            imported = 0
            skipped = 0
            errors = []
            
            for row in csv_reader:
                register_id = row['Register ID'].strip()
                
                if not register_id:
                    skipped += 1
                    continue
                
                if register_id in candidates:
                    skipped += 1
                    errors.append(f"Register ID {register_id} already exists")
                    continue
                
                # Handle empty day_scholar_hosteler - set to NULL if empty
                day_scholar_hosteler = row['Day Scholar / Hosteler'].strip()
                if not day_scholar_hosteler:
                    day_scholar_hosteler = None
                
                candidate_data = {
                    'register_id': register_id,
                    'candidate_name': row['Candidate Name'].strip(),
                    'department': row['Department'].strip(),
                    'position_applied': row['Position Applied'].strip(),
                    'day_scholar_hosteler': day_scholar_hosteler,
                    'phone_number': row['Phone Number'].strip(),
                    'linkedin_profile': row['LinkedIn Profile'].strip() or None,
                    'github_profile': row['GitHub Profile'].strip() or None,
                    'imported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                if create_candidate(candidate_data):
                    imported += 1
                else:
                    errors.append(f"Failed to import Register ID {register_id}")
            
            message = f'Successfully imported {imported} candidate(s).'
            if skipped > 0:
                message += f' Skipped {skipped} duplicate(s).'
            
            return render_template('import_candidates.html', success=message, errors=errors if errors else None)
        
        except Exception as e:
            return render_template('import_candidates.html', error=f'Error processing CSV: {str(e)}')
    
    return render_template('import_candidates.html')

@app.route('/add_checklist', methods=['GET', 'POST'])
def add_checklist():
    """Handle interview checklist form"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_role = session.get('role', 'admin')
    user_name = session.get('name', session.get('user_id', ''))
    
    candidates = get_all_candidates()
    
    if request.method == 'POST':
        register_id = request.form.get('register_id')
        
        if register_id not in candidates:
            return render_template('add_checklist.html', candidates=candidates, 
                                 error='Invalid candidate selected')
        
        # Parse form data
        skills = []
        skill_count = int(request.form.get('skill_count', 0))
        for i in range(skill_count):
            tech = request.form.get(f'skill_{i}_tech', '').strip()
            level = request.form.get(f'skill_{i}_level', '').strip()
            if tech:
                skills.append({'technology': tech, 'skill_level': level})
        
        practical_experience = request.form.get('practical_experience', '').strip()
        
        communication = request.form.get('communication_skills', '').strip()
        time_management = request.form.get('time_management', '').strip()
        leadership = request.form.get('leadership_ability', '').strip()
        
        interviewer_comments = request.form.get('interviewer_comments', '').strip()
        faculty_comments = request.form.get('faculty_comments', '').strip()
        
        interview_taken_by = request.form.get('interview_taken_by', '').strip()
        reviewed_by = request.form.get('reviewed_by', '').strip()
        remarks = request.form.get('remarks', '').strip()
        
        # Get existing checklist if it exists
        existing_checklist = get_checklist(register_id) or {}
        
        # Auto-fill names based on role
        if user_role == 'interviewer' and not interview_taken_by:
            interview_taken_by = user_name
        elif user_role == 'faculty_reviewer' and not reviewed_by:
            reviewed_by = user_name
        
        # Prepare checklist data based on role
        if user_role == 'faculty_reviewer':
            # Faculty reviewer can only update soft skills and faculty comments
            checklist_data = {
                'register_id': register_id,
                'technical_skills': existing_checklist.get('technical_skills', []),
                'practical_experience': existing_checklist.get('practical_experience', ''),
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': existing_checklist.get('interviewer_comments', ''),
                'faculty_comments': faculty_comments,
                'interview_taken_by': existing_checklist.get('interview_taken_by', ''),
                'reviewed_by': user_name,
                'remarks': remarks
            }
        elif user_role == 'interviewer':
            # Interviewer can update all fields except faculty_comments and reviewed_by
            checklist_data = {
                'register_id': register_id,
                'technical_skills': skills,
                'practical_experience': practical_experience,
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': interviewer_comments,
                'faculty_comments': existing_checklist.get('faculty_comments', ''),
                'interview_taken_by': user_name,
                'reviewed_by': existing_checklist.get('reviewed_by', ''),
                'remarks': remarks
            }
        else:
            # Admin can update all fields
            checklist_data = {
                'register_id': register_id,
                'technical_skills': skills,
                'practical_experience': practical_experience,
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': interviewer_comments,
                'faculty_comments': faculty_comments,
                'interview_taken_by': interview_taken_by if interview_taken_by else (user_name if user_role == 'interviewer' else ''),
                'reviewed_by': reviewed_by,
                'remarks': remarks
            }
        
        # Save checklist to Supabase
        save_checklist(register_id, checklist_data)
        
        return render_template('add_checklist.html', candidates=candidates, 
                             user_role=user_role, user_name=user_name,
                             success='Checklist saved successfully!')
    
    return render_template('add_checklist.html', candidates=candidates, 
                         user_role=user_role, user_name=user_name)

@app.route('/view_candidates')
def view_candidates():
    """Display all candidates in table view"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_role = session.get('role', 'admin')
    candidates = get_all_candidates()
    checklists = get_all_checklists()
    
    # Add checklist status to each candidate
    for register_id in candidates:
        candidates[register_id]['has_checklist'] = register_id in checklists
    
    return render_template('view_candidates.html', candidates=candidates, user_role=user_role)

@app.route('/view_checklist/<register_id>')
def view_checklist(register_id):
    """View checklist for a specific candidate"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    candidate = get_candidate(register_id)
    if not candidate:
        return redirect(url_for('view_candidates'))
    
    checklist = get_checklist(register_id)
    
    return render_template('view_checklist.html', candidate=candidate, checklist=checklist)

@app.route('/edit_checklist/<register_id>', methods=['GET', 'POST'])
def edit_checklist(register_id):
    """Edit checklist for a specific candidate"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_role = session.get('role', 'admin')
    user_name = session.get('name', session.get('user_id', ''))
    
    candidate = get_candidate(register_id)
    if not candidate:
        return redirect(url_for('view_candidates'))
    
    checklist = get_checklist(register_id) or {}
    
    if request.method == 'POST':
        # Parse form data (same as add_checklist)
        skills = []
        skill_count = int(request.form.get('skill_count', 0))
        for i in range(skill_count):
            tech = request.form.get(f'skill_{i}_tech', '').strip()
            level = request.form.get(f'skill_{i}_level', '').strip()
            if tech:
                skills.append({'technology': tech, 'skill_level': level})
        
        practical_experience = request.form.get('practical_experience', '').strip()
        communication = request.form.get('communication_skills', '').strip()
        time_management = request.form.get('time_management', '').strip()
        leadership = request.form.get('leadership_ability', '').strip()
        interviewer_comments = request.form.get('interviewer_comments', '').strip()
        faculty_comments = request.form.get('faculty_comments', '').strip()
        interview_taken_by = request.form.get('interview_taken_by', '').strip()
        reviewed_by = request.form.get('reviewed_by', '').strip()
        remarks = request.form.get('remarks', '').strip()
        
        # Auto-fill names based on role
        if user_role == 'interviewer' and not interview_taken_by:
            interview_taken_by = user_name
        elif user_role == 'faculty_reviewer' and not reviewed_by:
            reviewed_by = user_name
        
        # Get existing checklist
        existing_checklist = get_checklist(register_id) or {}
        
        # Prepare checklist data based on role
        if user_role == 'faculty_reviewer':
            # Faculty reviewer can only update soft skills and faculty comments
            checklist_data = {
                'register_id': register_id,
                'technical_skills': existing_checklist.get('technical_skills', []),
                'practical_experience': existing_checklist.get('practical_experience', ''),
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': existing_checklist.get('interviewer_comments', ''),
                'faculty_comments': faculty_comments,
                'interview_taken_by': existing_checklist.get('interview_taken_by', ''),
                'reviewed_by': user_name,
                'remarks': remarks
            }
        elif user_role == 'interviewer':
            # Interviewer can update all fields except faculty_comments and reviewed_by
            checklist_data = {
                'register_id': register_id,
                'technical_skills': skills,
                'practical_experience': practical_experience,
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': interviewer_comments,
                'faculty_comments': existing_checklist.get('faculty_comments', ''),
                'interview_taken_by': user_name,
                'reviewed_by': existing_checklist.get('reviewed_by', ''),
                'remarks': remarks
            }
        else:
            # Admin can update all fields
            checklist_data = {
                'register_id': register_id,
                'technical_skills': skills,
                'practical_experience': practical_experience,
                'communication_skills': communication,
                'time_management': time_management,
                'leadership_ability': leadership,
                'interviewer_comments': interviewer_comments,
                'faculty_comments': faculty_comments,
                'interview_taken_by': interview_taken_by if interview_taken_by else (user_name if user_role == 'interviewer' else ''),
                'reviewed_by': reviewed_by,
                'remarks': remarks
            }
        
        # Save checklist to Supabase
        save_checklist(register_id, checklist_data)
        
        return redirect(url_for('view_checklist', register_id=register_id))
    
    return render_template('edit_checklist.html', candidate=candidate, checklist=checklist,
                         user_role=user_role, user_name=user_name)

@app.route('/report/<register_id>')
def report(register_id):
    """Generate checklist report for a candidate"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    candidate = get_candidate(register_id)
    if not candidate:
        return redirect(url_for('view_candidates'))
    
    checklist = get_checklist(register_id)
    
    # Use the new professional checklist report template
    return render_template('checklist_report.html', candidate=candidate, checklist=checklist)

@app.route('/download_pdf/<register_id>')
def download_pdf(register_id):
    """Download PDF report for a specific candidate"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    candidate = get_candidate(register_id)
    if not candidate:
        return redirect(url_for('view_candidates'))
    
    checklist = get_checklist(register_id)
    
    # Create PDF with watermark
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                            rightMargin=0.5*inch, leftMargin=0.5*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1a73e8'),
        spaceAfter=12,
        alignment=1,  # Center
        fontName='Helvetica-Bold'
    )
    
    # Header with logo
    logo_path = os.path.join('static', 'KARE-ACM-SiGBED.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.2*inch, height=1.2*inch)
        story.append(logo)
        story.append(Spacer(1, 0.1*inch))
    
    story.append(Paragraph("GDG On Campus", title_style))
    story.append(Paragraph("Kalasalingam Academy of Research & Education", styles['Heading2']))
    story.append(Paragraph("Core Recruitment 2026 - Interview Checklist Report", styles['Heading3']))
    story.append(Spacer(1, 0.3*inch))
    
    # Candidate Details
    story.append(Paragraph("<b>Candidate Details</b>", styles['Heading2']))
    candidate_data = [
        ['Register ID:', candidate['register_id']],
        ['Name:', candidate['candidate_name']],
        ['Department:', candidate['department']],
        ['Position Applied:', format_positions(candidate['position_applied'])],
        ['Day Scholar / Hosteler:', candidate['day_scholar_hosteler']],
        ['Phone Number:', candidate['phone_number']],
        ['LinkedIn:', candidate['linkedin_profile']],
        ['GitHub:', candidate['github_profile']]
    ]
    
    candidate_table = Table(candidate_data, colWidths=[2*inch, 4*inch])
    candidate_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (1, 0), (1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(candidate_table)
    story.append(Spacer(1, 0.2*inch))
    
    if checklist:
        # Technical Skills
        if checklist.get('technical_skills'):
            story.append(Paragraph("<b>Technical Skills</b>", styles['Heading2']))
            skills_data = [['Technology', 'Skill Level']]
            for skill in checklist['technical_skills']:
                skills_data.append([skill['technology'], skill['skill_level']])
            
            skills_table = Table(skills_data, colWidths=[3*inch, 3*inch])
            skills_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(skills_table)
            story.append(Spacer(1, 0.2*inch))
        
        # Evaluation
        story.append(Paragraph("<b>Evaluation</b>", styles['Heading2']))
        eval_data = [
            ['Practical Experience:', checklist.get('practical_experience', 'N/A')],
            ['Communication Skills:', checklist.get('communication_skills', 'N/A')],
            ['Time Management:', checklist.get('time_management', 'N/A')],
            ['Leadership Ability:', checklist.get('leadership_ability', 'N/A')]
        ]
        
        eval_table = Table(eval_data, colWidths=[2*inch, 4*inch])
        eval_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(eval_table)
        story.append(Spacer(1, 0.2*inch))
        
        # Comments
        if checklist.get('interviewer_comments'):
            story.append(Paragraph("<b>Interviewer Comments:</b>", styles['Heading3']))
            story.append(Paragraph(checklist['interviewer_comments'], styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        if checklist.get('faculty_comments'):
            story.append(Paragraph("<b>Faculty Mentor Comments:</b>", styles['Heading3']))
            story.append(Paragraph(checklist['faculty_comments'], styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
        
        # Internal
        story.append(Paragraph("<b>Internal Official Use</b>", styles['Heading2']))
        internal_data = [
            ['Interview Taken By:', checklist.get('interview_taken_by', 'N/A')],
            ['Reviewed By:', checklist.get('reviewed_by', 'N/A')],
            ['Remarks:', checklist.get('remarks', 'N/A')]
        ]
        
        internal_table = Table(internal_data, colWidths=[2*inch, 4*inch])
        internal_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(internal_table)
    
    # Define page drawing function
    def on_first_page(canv, doc):
        canv.saveState()
        
        # Draw watermark image (repeating pattern)
        watermark_path = os.path.join('static', 'Watermark.jpg')
        if os.path.exists(watermark_path):
            try:
                # Set transparency for watermark effect
                canv.setFillAlpha(0.15)
                canv.setStrokeAlpha(0.15)
                
                # Draw watermark in repeating pattern across the page
                watermark_size = 4*inch
                for x in range(0, int(doc.width + doc.leftMargin + doc.rightMargin), int(watermark_size)):
                    for y in range(0, int(doc.height + doc.topMargin + doc.bottomMargin), int(watermark_size)):
                        canv.drawImage(watermark_path, 
                                     x + doc.leftMargin, 
                                     y + doc.bottomMargin,
                                     width=watermark_size, 
                                     height=watermark_size, 
                                     preserveAspectRatio=True, 
                                     mask='auto')
            except Exception as e:
                pass  # If image fails to load, continue without it
        
        canv.restoreState()
    
    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_first_page)
    buffer.seek(0)
    
    return send_file(buffer, mimetype='application/pdf', 
                    as_attachment=True, 
                    download_name=f'checklist_{register_id}.pdf')

@app.route('/download_all_pdf')
def download_all_pdf():
    """Download PDF report for all candidates"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    candidates = get_all_candidates()
    checklists = get_all_checklists()
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1a73e8'),
        spaceAfter=12,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    # Header with logo
    logo_path = os.path.join('static', 'KARE-ACM-SiGBED.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.2*inch, height=1.2*inch)
        story.append(logo)
        story.append(Spacer(1, 0.1*inch))
    
    story.append(Paragraph("GDG On Campus", title_style))
    story.append(Paragraph("Kalasalingam Academy of Research & Education", styles['Heading2']))
    story.append(Paragraph("Core Recruitment 2026 - All Interview Checklist Reports", styles['Heading3']))
    story.append(Spacer(1, 0.3*inch))
    
    # Generate report for each candidate with checklist
    for register_id, candidate in candidates.items():
        checklist = checklists.get(register_id)
        if not checklist:
            continue
        
        # Page break before each candidate (except first)
        if story:
            story.append(Spacer(1, 0.2*inch))
        
        # Candidate Details
        story.append(Paragraph(f"<b>Candidate: {candidate['candidate_name']} ({register_id})</b>", styles['Heading2']))
        candidate_data = [
            ['Register ID:', candidate['register_id']],
            ['Name:', candidate['candidate_name']],
            ['Department:', candidate['department']],
            ['Position Applied:', format_positions(candidate['position_applied'])]
        ]
        
        candidate_table = Table(candidate_data, colWidths=[2*inch, 4*inch])
        candidate_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(candidate_table)
        story.append(Spacer(1, 0.1*inch))
        
        # Technical Skills Summary
        if checklist.get('technical_skills'):
            skills_text = ", ".join([f"{s['technology']} ({s['skill_level']})" 
                                    for s in checklist['technical_skills']])
            story.append(Paragraph(f"<b>Technical Skills:</b> {skills_text}", styles['Normal']))
        
        # Evaluation Summary
        eval_text = f"Communication: {checklist.get('communication_skills', 'N/A')}, "
        eval_text += f"Time Management: {checklist.get('time_management', 'N/A')}, "
        eval_text += f"Leadership: {checklist.get('leadership_ability', 'N/A')}"
        story.append(Paragraph(f"<b>Evaluation:</b> {eval_text}", styles['Normal']))
        
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph("─" * 80, styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    
    return send_file(buffer, mimetype='application/pdf', 
                    as_attachment=True, 
                    download_name=f'all_checklists_{datetime.now().strftime("%Y%m%d")}.pdf')

# Initialize default user and start keep-alive thread
# This runs when the module is imported (works with both Flask dev server and Gunicorn)
init_default_user()
start_keep_alive_thread()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)


