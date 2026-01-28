from flask import Flask, render_template, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# File to store attendance data
DATA_FILE = 'attendance_data.json'

def load_data():
    """Load attendance data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'classes': {}, 'students': {}, 'records': []}

def save_data(data):
    """Save attendance data to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

# ========== CLASS MANAGEMENT ==========
@app.route('/api/classes', methods=['GET'])
def get_classes():
    """Get list of all classes"""
    data = load_data()
    return jsonify(list(data.get('classes', {}).keys()))

@app.route('/api/classes', methods=['POST'])
def add_class():
    """Add a new class"""
    data = load_data()
    class_name = request.json.get('className', '').strip()
    section = request.json.get('section', '').strip()
    
    if not class_name or not section:
        return jsonify({'error': 'Class name and section required'}), 400
    
    key = f"{class_name}-{section}"
    if key in data.get('classes', {}):
        return jsonify({'error': 'Class-Section combination already exists'}), 400
    
    if 'classes' not in data:
        data['classes'] = {}
    
    data['classes'][key] = {
        'className': class_name,
        'section': section,
        'created': datetime.now().isoformat(),
        'studentCount': 0
    }
    save_data(data)
    return jsonify({'success': True, 'id': key})

@app.route('/api/classes/<class_id>', methods=['DELETE'])
def delete_class(class_id):
    """Delete a class and its students"""
    data = load_data()
    if class_id in data.get('classes', {}):
        del data['classes'][class_id]
        # Remove students from this class
        data['students'] = {k: v for k, v in data['students'].items() if v.get('classId') != class_id}
        # Remove attendance records for students in this class
        student_ids = [k for k, v in data['students'].items() if v.get('classId') == class_id]
        data['records'] = [r for r in data['records'] if r['student'] not in student_ids]
        save_data(data)
        return jsonify({'success': True})
    return jsonify({'error': 'Class not found'}), 404

# ========== STUDENT MANAGEMENT ==========
@app.route('/api/students', methods=['GET'])
def get_students():
    """Get list of all students"""
    data = load_data()
    class_id = request.args.get('classId')
    
    if class_id:
        students = {k: v for k, v in data.get('students', {}).items() if v.get('classId') == class_id}
    else:
        students = data.get('students', {})
    
    return jsonify([{'id': k, **v} for k, v in students.items()])

@app.route('/api/students', methods=['POST'])
def add_student():
    """Add a new student"""
    data = load_data()
    student_name = request.json.get('name', '').strip()
    roll_no = request.json.get('rollNo', '').strip()
    class_id = request.json.get('classId', '').strip()
    
    if not student_name or not class_id:
        return jsonify({'error': 'Name and class required'}), 400
    
    if class_id not in data.get('classes', {}):
        return jsonify({'error': 'Class not found'}), 404
    
    student_id = f"{class_id}_{len([s for s in data.get('students', {}).values() if s.get('classId') == class_id]) + 1}"
    
    if 'students' not in data:
        data['students'] = {}
    
    data['students'][student_id] = {
        'name': student_name,
        'rollNo': roll_no,
        'classId': class_id,
        'added': datetime.now().isoformat()
    }
    
    # Update class student count
    if class_id in data['classes']:
        data['classes'][class_id]['studentCount'] = len([s for s in data['students'].values() if s.get('classId') == class_id])
    
    save_data(data)
    return jsonify({'success': True, 'id': student_id})

@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Delete a student"""
    data = load_data()
    if student_id in data.get('students', {}):
        class_id = data['students'][student_id].get('classId')
        del data['students'][student_id]
        # Remove attendance records
        data['records'] = [r for r in data['records'] if r['student'] != student_id]
        
        # Update class count
        if class_id and class_id in data['classes']:
            data['classes'][class_id]['studentCount'] = len([s for s in data['students'].values() if s.get('classId') == class_id])
        
        save_data(data)
        return jsonify({'success': True})
    return jsonify({'error': 'Student not found'}), 404

# ========== ATTENDANCE MANAGEMENT ==========
@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    """Mark attendance for a student"""
    data = load_data()
    student_id = request.json.get('student', '').strip()
    status = request.json.get('status', 'present')
    
    if not student_id or student_id not in data.get('students', {}):
        return jsonify({'error': 'Student not found'}), 404
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Check if student already has a record for today
    existing_record_index = None
    for i, r in enumerate(data.get('records', [])):
        if r['student'] == student_id and r['date'] == today:
            existing_record_index = i
            break
    
    record = {
        'student': student_id,
        'date': today,
        'time': datetime.now().strftime('%H:%M:%S'),
        'status': status
    }
    
    if existing_record_index is not None:
        data['records'][existing_record_index] = record
    else:
        if 'records' not in data:
            data['records'] = []
        data['records'].append(record)
    
    save_data(data)
    return jsonify({'success': True, 'record': record})

@app.route('/api/attendance/<date>', methods=['GET'])
def get_attendance_by_date(date):
    """Get unique attendance records for a specific date"""
    data = load_data()
    students_seen = {}
    for r in data.get('records', []):
        if r['date'] == date:
            students_seen[r['student']] = r
    
    return jsonify(list(students_seen.values()))

# ========== REPORT GENERATION ==========
@app.route('/api/report', methods=['GET'])
def get_report():
    """Get attendance summary report"""
    data = load_data()
    class_id = request.args.get('classId')
    report = {}
    
    students = {k: v for k, v in data.get('students', {}).items() if not class_id or v.get('classId') == class_id}
    
    for student_id, student in students.items():
        records = [r for r in data.get('records', []) if r['student'] == student_id]
        present = len([r for r in records if r['status'] == 'present'])
        absent = len([r for r in records if r['status'] == 'absent'])
        late = len([r for r in records if r['status'] == 'late'])
        
        report[student_id] = {
            'name': student.get('name', student_id),  # Fallback to student_id if name not present
            'rollNo': student.get('rollNo', ''),
            'classId': student.get('classId', ''),
            'present': present,
            'absent': absent,
            'late': late,
            'total': len(records)
        }
    
    return jsonify(report)

@app.route('/api/report/export', methods=['GET'])
def export_report():
    """Export attendance report as JSON"""
    data = load_data()
    export_data = {
        'exported_date': datetime.now().isoformat(),
        'classes': data.get('classes', {}),
        'students': data.get('students', {}),
        'attendance_records': data.get('records', [])
    }
    return jsonify(export_data)

if __name__ == '__main__':
    app.run(debug=True)