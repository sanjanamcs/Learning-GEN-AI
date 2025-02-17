from fastapi import HTTPException
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn
import pandas as pd
import json
import io
import re
import fitz  # PyMuPDF
from fpdf import FPDF
import requests

app = FastAPI()

# ---------------- Global Variables ----------------
# List of candidate dictionaries extracted from the skill matrix file
candidate_list = []
selected_candidate = {}     # Candidate chosen by the user
resume_files = {}           # Mapping from candidate ID to generated PDF filename
progress_log = {}           # Mapping from candidate ID to progress messages

# ---------------- Utility Functions ----------------


def extract_skill_matrix_from_upload(file: UploadFile):
    """
    Reads an uploaded Excel file (skill matrix) and extracts structured candidate data.
    Raises an HTTPException if the file is empty or not a valid Excel file.
    Returns a list of candidate dictionaries.
    """
    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=400, detail="No file uploaded. Please select a valid Excel (.xlsx) file.")
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a valid Excel (.xlsx) file. Please upload a valid Excel file.")

    structured_data = []
    role_counter = 1
    unique_individuals = set()
    percentage_pattern = re.compile(r"^\d+(\.\d+)?%?$")

    for sheet in xls.sheet_names:
        try:
            df = xls.parse(sheet)
            df = df.dropna(how="all").fillna("")
            columns = list(df.columns)
            if len(columns) < 2:
                continue
            first_name_col = columns[0]
            last_name_col = "Unnamed: 1" if "Unnamed: 1" in columns else columns[1]
            experience_col = columns[2] if len(columns) > 2 else None
            expertise_col = columns[3] if len(columns) > 3 else None

            # Define two merged categories
            categories = {
                "Salesforce Technical Competencies and External Systems Integration": [],
                "Behavioral & Leadership Competencies and Certifications": []
            }
            category_flag = None
            for col in columns[4:]:
                if "%" in col or "Current Capability Score" in col or "Expertise(Years)" in col:
                    continue
                if "Salesforce Technical Competencies" in col or "External Systems Integration" in col:
                    category_flag = "Salesforce Technical Competencies and External Systems Integration"
                elif "Behavioral & Leadership Competencies" in col or "SF Certification" in col:
                    category_flag = "Behavioral & Leadership Competencies and Certifications"
                elif category_flag:
                    categories[category_flag].append(col)

            for _, row in df.iterrows():
                first_name = str(row[first_name_col]).strip()
                last_name = str(row[last_name_col]).strip()
                experience = row[experience_col] if experience_col and isinstance(
                    row[experience_col], (int, float, str)) else ""
                expertise = row[expertise_col] if expertise_col and isinstance(
                    row[expertise_col], (int, float, str)) else ""
                if percentage_pattern.match(first_name) or percentage_pattern.match(last_name):
                    continue
                has_skills = any(
                    isinstance(row[col], (int, float)) and row[col] > 0
                    for col in (categories["Salesforce Technical Competencies and External Systems Integration"] +
                                categories["Behavioral & Leadership Competencies and Certifications"])
                )
                if first_name and last_name and has_skills:
                    full_name = f"{first_name} {last_name}"
                    if full_name not in unique_individuals:
                        unique_individuals.add(full_name)
                        entry = {
                            "ID": f"Role_{role_counter}",
                            "Sheet Name": sheet,
                            "First Name": first_name,
                            "Last Name": last_name,
                            "Experience": experience,
                            "Expertise": expertise,
                            "Salesforce Technical Competencies and External Systems Integration": {
                                skill: row[skill] for skill in categories["Salesforce Technical Competencies and External Systems Integration"]
                                if skill in row and isinstance(row[skill], (int, float)) and row[skill] > 0
                            },
                            "Behavioral & Leadership Competencies and Certifications": {
                                skill: row[skill] for skill in categories["Behavioral & Leadership Competencies and Certifications"]
                                if skill in row and isinstance(row[skill], (int, float)) and row[skill] > 0
                            }
                        }
                        for cert in categories["Behavioral & Leadership Competencies and Certifications"]:
                            if cert in row and row[cert] == 1:
                                entry["Behavioral & Leadership Competencies and Certifications"][cert] = "Certified"
                        structured_data.append(entry)
                        role_counter += 1
                    if len(structured_data) >= 62:
                        break
        except Exception as e:
            print(f"Error processing sheet {sheet}: {e}")
    return structured_data


def extract_pdf_text_from_upload(file: UploadFile):
    """
    Extracts text from an uploaded PDF file using PyMuPDF.
    """
    file_bytes = file.file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text("text")
    return text

# ---------------- LLM & PDF Generation Functions ----------------


def generate_new_resume(comp_matrix, resume, new_resume_format):
    """
    Calls an LLM API (via OpenRouter using ASUS TUF API) to reformat the old resume plus candidate skill data
    into a new structured JSON following the provided new resume format.
    """
    system_prompt = """
    You are an AI assistant that reformats resumes into a structured JSON format.
    Take the competency matrix and old resume as input, extract relevant details, and map them to the new resume format.
    Only respond with the new resume format as a JSON object that adheres strictly to the provided JSON Schema. Do not include any extra messages.
    """
    user_prompt = f"""
    Competency Matrix:
    {comp_matrix}
    
    Resume:
    {resume}
    
    Convert this into the following structured format:
    {new_resume_format}
    """
    json_schema = {
        "name": "new_resume",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "description": "Candidate's first name"},
                "last_name": {"type": "string", "description": "Candidate's last name"},
                "role": {"type": "string", "description": "Candidate's role or position"},
                "professional_summary": {"type": "string", "description": "Professional summary of the candidate"},
                "education": {"type": "string", "description": "Education details of the candidate"},
                "skills": {"type": "string", "description": "Comma separated skills"},
                "projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name of the project"},
                            "description": {"type": "string", "description": "Description of the project"},
                            "role": {"type": "string", "description": "Role in the project"},
                            "technology": {"type": "string", "description": "Technologies used in the project"},
                            "role_played": {"type": "string", "description": "Detailed role played in the project"}
                        },
                        "required": ["name", "description", "role", "technology", "role_played"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["first_name", "last_name", "role", "professional_summary", "education", "skills", "projects"],
            "additionalProperties": False
        }
    }
    payload = {
        "model": "mistralai/mistral-small-24b-instruct-2501",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_schema", "json_schema": json_schema}
    }
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": "Bearer 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",
            "Content-Type": "application/json"
        },
        data=json.dumps(payload)
    )
    response = response.json()
    return response["choices"][0]["message"]["content"]


def generate_cover_letter(resume_data):
    """
    Generates a cover letter by calling an LLM API based on the provided resume data.
    """
    prompt = (
        f"Generate a professional cover letter for a job application using the following resume details:\n\n"
        f"Name: {resume_data.get('first_name', '')} {resume_data.get('last_name', '')}\n"
        f"Role: {resume_data.get('role', '')}\n"
        f"Professional Summary: {resume_data.get('professional_summary', '')}\n"
        f"Education: {resume_data.get('education', '')}\n"
        f"Skills: {resume_data.get('skills', '')}\n\n"
        f"Cover Letter:"
    )
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }
    data_payload = {
        "model": "mistralai/mistral-small-24b-instruct-2501",
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "You are an AI assistant that generates a professional cover letter."},
            {"role": "user", "content": prompt}
        ]
    }
    response = requests.post(url, headers=headers,
                             data=json.dumps(data_payload))
    response_json = response.json()
    cover_letter_text = response_json["choices"][0]["message"]["content"]
    return cover_letter_text


def generate_resume(data_json, logo_path=None):
    """
    Generates a resume PDF (using FPDF) from the new resume JSON data.
    It also calls the cover letter generation function and appends it on a new page.
    Returns the filename of the generated PDF.
    """
    data = json.loads(data_json)
    pdf = FPDF()
    pdf.add_page()
    # Register Unicode fonts (ensure the .ttf files are accessible)
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.add_font("DejaVu", "B", "DejaVuSans-Bold.ttf", uni=True)
    if logo_path:
        x = 210 - 30 - 10
        y = 10
        try:
            pdf.image(logo_path, x=x, y=y, w=30)
            pdf.set_y(y + 35)
        except RuntimeError:
            pass
    pdf.set_font("DejaVu", "B", 16)
    full_name = f"{data['first_name']} {data['last_name']}"
    pdf.cell(0, 10, full_name, ln=True, align='C')
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, data['role'], ln=True, align='C')
    sections = [
        ('PROFESSIONAL SUMMARY', [data['professional_summary']]),
        ('EDUCATION', [data['education']]),
        ('SKILLS', [data['skills']])
    ]
    for title, content in sections:
        pdf.ln(10)
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 10, title, ln=True)
        pdf.set_font("DejaVu", "", 12)
        pdf.multi_cell(0, 5, "\n".join(content))
    pdf.ln(10)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 10, "PROJECT DETAILS", ln=True)
    pdf.set_font("DejaVu", "", 12)
    for project in data['projects']:
        pdf.ln(5)
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 10, project['name'], ln=True)
        pdf.set_font("DejaVu", "", 12)
        pdf.multi_cell(0, 5, project['description'])
        pdf.cell(0, 5, f"Role: {project['role']}", ln=True)
        pdf.cell(0, 5, f"Technology: {project['technology']}", ln=True)
        pdf.cell(0, 5, f"Role Played: {project['role_played']}", ln=True)
        pdf.ln(5)
    print("Generating Cover Letter...")
    cover_letter_text = generate_cover_letter(data)
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, "COVER LETTER", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("DejaVu", "", 12)
    pdf.multi_cell(0, 5, cover_letter_text)
    filename = f"{data['first_name']}_{data['last_name']}_Resume.pdf"
    pdf.output(filename)
    return filename

# ---------------- Background Task ----------------


def generate_resume_background(comp_matrix, old_resume_text, new_resume_format, candidate_id):
    """
    Background task that:
      1. Updates the progress log at each step.
      2. Calls the LLM to generate the new resume JSON.
      3. Generates the PDF.
      4. Stores the filename in resume_files.
    """
    progress_log[candidate_id] = []
    progress_log[candidate_id].append("Starting resume generation...")

    progress_log[candidate_id].append("Calling LLM to reformat resume...")
    formatted_resume = generate_new_resume(
        comp_matrix, old_resume_text, new_resume_format)
    progress_log[candidate_id].append("LLM reformatting complete.")

    progress_log[candidate_id].append(
        "Generating PDF resume with cover letter...")
    pdf_filename = generate_resume(formatted_resume, logo_path="Logo.png")
    progress_log[candidate_id].append("PDF generation complete.")

    resume_files[candidate_id] = pdf_filename

# ---------------- FastAPI Endpoints ----------------


@app.get("/", response_class=HTMLResponse)
async def index():
    html = """
    <html>
      <head><title>Resume Maker</title></head>
      <body>
        <h2>Step 1: Upload Skill Matrix File (Excel)</h2>
        <form action="/upload-skill-matrix" enctype="multipart/form-data" method="post">
          <input name="file" type="file">
          <br><br>
          <input type="submit" value="Upload Skill Matrix">
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/upload-skill-matrix", response_class=HTMLResponse)
async def upload_skill_matrix(file: UploadFile = File(...)):
    # Check if a file was selected
    if not file.filename:
        raise HTTPException(
            status_code=400, detail="No file selected. Please upload a valid Excel (.xlsx) file.")
    # Read file contents asynchronously
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=400, detail="Uploaded file is empty. Please upload a valid Excel (.xlsx) file.")
    # Create a BytesIO stream from the file contents
    file_like = io.BytesIO(contents)
    # Create a new UploadFile-like object so that our extraction function can use it
    new_file = UploadFile(filename=file.filename, file=file_like)

    global candidate_list
    candidate_list = extract_skill_matrix_from_upload(new_file)
    options_html = ""
    for candidate in candidate_list:
        cid = candidate.get("ID", "")
        fname = candidate.get("First Name", "")
        lname = candidate.get("Last Name", "")
        display = f"{cid} - {fname} {lname}"
        options_html += f'<option value="{cid}">{display}</option>'
    html = f"""
    <html>
      <head><title>Select Candidate</title></head>
      <body>
        <h2>Step 2: Select a Candidate</h2>
        <form action="/select-candidate" method="post">
          <select name="candidate_id">
            {options_html}
          </select>
          <br><br>
          <input type="submit" value="Next">
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/select-candidate", response_class=HTMLResponse)
async def select_candidate(candidate_id: str = Form(...)):
    global candidate_list, selected_candidate
    for candidate in candidate_list:
        if str(candidate.get("ID", "")) == candidate_id:
            selected_candidate = candidate
            break
    html = """
    <html>
      <head><title>Upload Old Resume</title></head>
      <body>
        <h2>Step 3: Upload Old Resume (PDF)</h2>
        <form action="/upload-old-resume" enctype="multipart/form-data" method="post">
          <input name="file" type="file">
          <br><br>
          <input type="submit" value="Generate New Resume">
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.post("/upload-old-resume", response_class=HTMLResponse)
async def upload_old_resume(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Extracts text from the uploaded old resume PDF,
    launches a background task to generate the new resume,
    and returns a progress page that shows intermediate progress messages.
    """
    old_resume_text = extract_pdf_text_from_upload(file)
    comp_matrix = json.dumps(selected_candidate)
    new_resume_format = """{
        "first_name": "Firstname here",
        "last_name": "Last Name Here",
        "role": "Role Here",
        "professional_summary": "Professional summary here...",
        "education": "Education Degree with course Details here...",
        "skills": "Skills here...(Separate it with comma)",
        "projects": [
            {
                "name": "Project1",
                "description": "Developed a web application for...",
                "role": "Lead Developer",
                "technology": "Python, Django, PostgreSQL",
                "role_played": "Designed architecture and led the team."
            },
            {
                "name": "Project2",
                "description": "Mobile app for task management.",
                "role": "Full Stack Developer",
                "technology": "React Native, Node.js",
                "role_played": "Implemented frontend and backend features."
            }
        ]
    }"""
    candidate_id = selected_candidate.get("ID", "unknown")
    background_tasks.add_task(generate_resume_background, comp_matrix,
                              old_resume_text, new_resume_format, candidate_id)

    progress_html = f"""
    <html>
      <head>
        <title>Generating Resume...</title>
        <style>
          #progressContainer {{
            width: 100%;
            background-color: #ddd;
          }}
          #progressBar {{
            width: 1%;
            height: 30px;
            background-color: #4CAF50;
          }}
          #progressMessages {{
            margin-top: 20px;
            font-family: Arial, sans-serif;
          }}
        </style>
      </head>
      <body>
        <h2>Generating your new resume. Please wait...</h2>
        <div id="progressContainer">
          <div id="progressBar"></div>
        </div>
        <div id="progressMessages"></div>
        <script>
          var progressBar = document.getElementById("progressBar");
          var progressMessages = document.getElementById("progressMessages");
          var width = 1;
          var interval = setInterval(frame, 100);
          var redirected = false;  // Ensure one-time redirect
          function frame() {{
            if (width >= 100) {{
              width = 1;
            }} else {{
              width++;
              progressBar.style.width = width + '%';
            }}
          }}
          async function pollProgress() {{
            let response = await fetch("/progress?candidate_id={candidate_id}");
            let data = await response.json();
            progressMessages.innerHTML = "";
            data.messages.forEach(function(msg) {{
              let p = document.createElement("p");
              p.textContent = msg;
              progressMessages.appendChild(p);
            }});
            if (data.status === "ready" && !redirected) {{
              redirected = true;
              clearInterval(interval);
              window.location.href = "/download/" + data.filename;
            }} else {{
              setTimeout(pollProgress, 2000);
            }}
          }}
          pollProgress();
        </script>
      </body>
    </html>
    """
    return HTMLResponse(content=progress_html)


@app.get("/progress")
async def progress(candidate_id: str):
    """
    Polling endpoint: returns JSON with status ("pending" or "ready"),
    the generated PDF filename if ready, and a list of progress messages.
    """
    if candidate_id in resume_files:
        return {"status": "ready", "filename": resume_files[candidate_id], "messages": progress_log.get(candidate_id, [])}
    else:
        return {"status": "pending", "messages": progress_log.get(candidate_id, ["Processing..."])}


@app.get("/download/{pdf_filename}", response_class=FileResponse)
async def download_pdf(pdf_filename: str):
    """
    Serves the generated PDF file for download.
    """
    return FileResponse(pdf_filename, media_type="application/pdf", filename=pdf_filename)

# ---------------- Main ----------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
