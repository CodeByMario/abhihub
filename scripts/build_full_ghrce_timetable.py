#!/usr/bin/env python3
"""
Build complete GHRCE Winter-2026 Examination Timetable dataset (Theory + Practical),
associating every exam with GHRCE (college_id: 87928d20-edb3-4185-94e3-b0678470e850).
"""
import os
import json
import re

GHRCE_COLLEGE_ID = "87928d20-edb3-4185-94e3-b0678470e850"
GHRCE_NAME = "G H Raisoni College of Engineering"
GHRCE_ABBR = "GHRCE"

PRACTICAL_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'ghrce_winter_2026_practical_timetable.json')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'ghrce_winter_2026_full_timetable.json')

# First Term Theory Exams (from uploaded official schedule image)
FIRST_TERM_THEORY = [
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNBSL103", "course": "Matrices and Differential Calculus", "date_raw": "26-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UBSL151", "course": "Matrices and Differential Calculus", "date_raw": "26-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNBSL101", "course": "Engineering Physics", "date_raw": "28-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UBSL101", "course": "Engineering Physics", "date_raw": "28-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNBSL105", "course": "Linear Algebra and Statistics", "date_raw": "29-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNBSL109", "course": "Biomedical Engineering", "date_raw": "29-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UBSL153", "course": "Linear Algebra and Statistics", "date_raw": "29-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNCEL103", "course": "Water Resources Engineering", "date_raw": "30-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNCEL101", "course": "Engineering Mechanics", "date_raw": "30-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNEEL101", "course": "Basic Electrical Engineering", "date_raw": "30-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UCEL101", "course": "Engineering Mechanics", "date_raw": "30-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UEEL101", "course": "Basic Electrical Engineering", "date_raw": "30-12-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNHUL124", "course": "Vedic Mathematics", "date_raw": "02-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNITL102", "course": "Programming for Problem Solving", "date_raw": "02-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UCSL101", "course": "Computer Programming", "date_raw": "02-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNECL107", "course": "Basic Electronics", "date_raw": "04-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNECL101", "course": "Digital Logic Design", "date_raw": "04-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UECL201", "course": "Digital Logic Design", "date_raw": "04-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UECL104", "course": "Modeling of Digital Circuits", "date_raw": "04-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNMEL101", "course": "Engineering Graphics", "date_raw": "06-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UMEL112", "course": "Engineering Graphics", "date_raw": "06-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNBSL102", "course": "Environmental Chemistry", "date_raw": "07-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UBSL131", "course": "Environment Chemistry", "date_raw": "07-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UCSL102", "course": "Foundation of Data Analytics", "date_raw": "08-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First", "code": "UNHUL123", "course": "Sanskrit for Technical Knowledge", "date_raw": "09-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UHUL101", "course": "Communication Skills", "date_raw": "09-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "First Year", "sem_raw": "First (2020-23 Scheme)", "code": "UECL103", "course": "Introduction to Discrete Devices and Circuits", "date_raw": "11-01-2027", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
]

# Major Theory Exams for Sem III, V, VII across branches
THEORY_EXAMS_CORE = [
    # Civil Engineering
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "III", "code": "UNCEL201", "course": "Mechanics of Materials", "date_raw": "28-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "III", "code": "UNCEL202", "course": "Fluid Mechanics", "date_raw": "30-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "III", "code": "UNMBL221", "course": "Engineering Economics and Industrial Management", "date_raw": "02-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "III", "code": "UNHUL201", "course": "Advanced Communication Skills", "date_raw": "17-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "V", "code": "UNCEL303", "course": "Soil Mechanics", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "V", "code": "UNCEL302", "course": "Transportation Engineering", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "V", "code": "UNCEL301", "course": "Reinforced Concrete Design", "date_raw": "20-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "VII", "code": "UNCEL402", "course": "Estimating and Costing", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "VII", "code": "UNCEL403", "course": "Advanced Structural Analysis", "date_raw": "02-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Civil Engineering", "sem_raw": "VII", "code": "UNCEL401", "course": "Irrigation and Drainage Engineering", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Mechanical Engineering
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "III", "code": "UNMEL202", "course": "Machining Process", "date_raw": "28-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "III", "code": "UNMEL201", "course": "Fluid Mechanics and Machinery", "date_raw": "30-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "III", "code": "UNMBL222", "course": "Operation Research & Management", "date_raw": "02-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "V", "code": "UNMEL302", "course": "Metrology and Quality Control", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "V", "code": "UNMEL304", "course": "Design of Machine Elements", "date_raw": "02-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "V", "code": "UNMEL301", "course": "Heat Transfer", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "VII", "code": "UNMEL401", "course": "Thermal Engineering", "date_raw": "26-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "VII", "code": "UNMEL402", "course": "Automation in Production", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Mechanical Engineering", "sem_raw": "VII", "code": "UNMEL403", "course": "Design of Mechanical Drives", "date_raw": "30-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Electrical Engineering
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "III", "code": "UNEEL201", "course": "Sensors and Transducers", "date_raw": "28-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "III", "code": "UNEEL202", "course": "Network Theory", "date_raw": "30-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "V", "code": "UNEEL301", "course": "AC Machines", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "V", "code": "UNEEL302", "course": "Power Electronics", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "V", "code": "UNEEL303", "course": "Basic Power System Analysis", "date_raw": "18-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "VII", "code": "UNEEL401", "course": "Switchgear and Protection", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electrical Engineering", "sem_raw": "VII", "code": "UNEEL402", "course": "High Voltage Engineering", "date_raw": "30-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Electronics & Communication
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "III", "code": "UNECL201", "course": "Electronics Devices and Circuits", "date_raw": "28-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "III", "code": "UNECL202", "course": "Signals and Systems", "date_raw": "30-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "V", "code": "UNECL303", "course": "Analog Communication", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "V", "code": "UNECL302", "course": "Digital System Design", "date_raw": "18-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "V", "code": "UNECL301", "course": "Electromagnetics and Transmission Lines", "date_raw": "20-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Electronics Engineering", "sem_raw": "VII", "code": "UNECL402", "course": "Switching Theory and Automata", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Computer Science & Engineering
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "III", "code": "UNBSL201", "course": "Discrete Mathematics & Graph Theory", "date_raw": "30-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "V", "code": "UNCSL301", "course": "Formal Languages and Automata", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "V", "code": "UNCSL303", "course": "Design and Analysis of Algorithms", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "V", "code": "UNITL301", "course": "Computer Networks", "date_raw": "20-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "V", "code": "UNCSL304", "course": "Operating System", "date_raw": "23-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "VII", "code": "UNCSL402", "course": "Artificial Intelligence and Machine Learning", "date_raw": "28-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "VII", "code": "UNITL404", "course": "Computer System Security", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering", "sem_raw": "VII", "code": "UNCSL401", "course": "Compiler Design", "date_raw": "21-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Information Technology
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "III", "code": "UNCSLM204", "course": "Computer System Architecture", "date_raw": "26-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "V", "code": "UNITL302", "course": "Principles of DSP and Algorithm", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "V", "code": "UNITL301", "course": "Computer Networks", "date_raw": "20-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "V", "code": "UNCSL304", "course": "Operating System", "date_raw": "23-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "VII", "code": "UNITL403", "course": "Software Engineering and Project Management", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Information Technology", "sem_raw": "VII", "code": "UNITL404", "course": "Computer System Security", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Artificial Intelligence
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "III", "code": "UNAIL201", "course": "Machine Learning Algorithms", "date_raw": "29-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "V", "code": "UNCSL301", "course": "Formal Languages and Automata", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "V", "code": "UNCSL304", "course": "Operating System", "date_raw": "23-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "V", "code": "UNAIL301", "course": "Soft Computing", "date_raw": "25-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "VII", "code": "UNCSL303", "course": "Design and Analysis of Algorithms", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "VII", "code": "UNAIL401", "course": "Responsible AI", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Artificial Intelligence", "sem_raw": "VII", "code": "UNAIL306", "course": "Data Networks", "date_raw": "21-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # Data Science
    {"programme": "B.Tech", "branch": "Data Science", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Data Science", "sem_raw": "V", "code": "UNDIL302", "course": "Big Data Computing", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Data Science", "sem_raw": "V", "code": "UNDIL301", "course": "Probability and Statistics", "date_raw": "23-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},

    # CSE (AIML)
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "V", "code": "UNCSL301", "course": "Formal Languages and Automata", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "V", "code": "UNAIL306", "course": "Data Networks", "date_raw": "21-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "V", "code": "UNAIL301", "course": "Soft Computing", "date_raw": "25-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "VII", "code": "UNAIL302", "course": "Natural Language Processing", "date_raw": "26-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "VII", "code": "UNCSL303", "course": "Design and Analysis of Algorithms", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AIML)", "sem_raw": "VII", "code": "UNAIL401", "course": "Responsible AI", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # CSE (Cyber Security)
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "V", "code": "UNDIL308", "course": "Cyber Laws and Cyber Ethics", "date_raw": "29-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "V", "code": "UNDIL307", "course": "Fundamentals of Cryptography", "date_raw": "18-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "V", "code": "UNDIL309", "course": "Penetration Testing", "date_raw": "20-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "VII", "code": "UNDIL406", "course": "Web Technology", "date_raw": "28-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "VII", "code": "UNDIL405", "course": "Ethical Hacking", "date_raw": "04-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (Cyber Security)", "sem_raw": "VII", "code": "UNDIL404", "course": "Computer Security", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},

    # CSE (AI)
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "III", "code": "UNCSL201", "course": "Data Structures and Algorithms", "date_raw": "19-11-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "V", "code": "UNCSL301", "course": "Formal Languages and Automata", "date_raw": "27-10-2026", "time_raw": "11:00 AM To 01:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "V", "code": "UNAIL306", "course": "Data Networks", "date_raw": "21-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "V", "code": "UNAIL301", "course": "Soft Computing", "date_raw": "25-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "VII", "code": "UNAIL302", "course": "Natural Language Processing", "date_raw": "26-10-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"},
    {"programme": "B.Tech", "branch": "Computer Science & Engineering (AI)", "sem_raw": "VII", "code": "UNAIL401", "course": "Responsible AI", "date_raw": "19-11-2026", "time_raw": "02:00 PM To 04:30 PM", "exam_type": "THEORY"}
]

def build_full_dataset():
    with open(PRACTICAL_FILE, 'r', encoding='utf-8') as f:
        practical_exams = json.load(f)

    # Mark all practical exams with college metadata
    for row in practical_exams:
        row['college_id'] = GHRCE_COLLEGE_ID
        row['college_name'] = GHRCE_NAME
        row['college_abbr'] = GHRCE_ABBR
        row['exam_type'] = 'PRACTICAL'

    # Mark theory exams with college metadata
    for row in FIRST_TERM_THEORY:
        row['college_id'] = GHRCE_COLLEGE_ID
        row['college_name'] = GHRCE_NAME
        row['college_abbr'] = GHRCE_ABBR

    for row in THEORY_EXAMS_CORE:
        row['college_id'] = GHRCE_COLLEGE_ID
        row['college_name'] = GHRCE_NAME
        row['college_abbr'] = GHRCE_ABBR

    full_dataset = practical_exams + FIRST_TERM_THEORY + THEORY_EXAMS_CORE

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_dataset, f, indent=2)

    print(f"[Build] Successfully combined {len(practical_exams)} practical + {len(FIRST_TERM_THEORY) + len(THEORY_EXAMS_CORE)} theory exam records.")
    print(f"[Build] Saved to {OUTPUT_FILE} (all mapped to {GHRCE_ABBR} - {GHRCE_COLLEGE_ID}).")

if __name__ == '__main__':
    build_full_dataset()
