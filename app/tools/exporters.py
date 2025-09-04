# app/tools/exporters.py
from io import BytesIO
from docx import Document

def checklist_json_to_docx(plan: dict) -> bytes:
    """
    Build a clean .docx from the structured checklist JSON.
    Returns bytes so Streamlit can offer a download directly.
    """
    doc = Document()
    doc.add_heading('Hiring Plan', level=0)

    # Timeline
    weeks = plan.get("timeline_weeks")
    if weeks:
        doc.add_paragraph(f"Target timeline: {weeks} week(s)")

    # Tasks
    doc.add_heading('Checklist', level=1)
    for t in plan.get("tasks", []):
        line = f"{t['name']} — owner: {t['owner']}, due: {t['due']}"
        doc.add_paragraph(line, style='List Bullet')

    # Interview Loop
    doc.add_heading('Interview Loop', level=1)
    for s in plan.get("interview_loop", []):
        line = f"{s['stage']} ({s['duration_min']} min): {', '.join(s['signals'])}"
        doc.add_paragraph(line, style='List Bullet')

    # Roles & JDs
    doc.add_heading('Roles & JDs', level=1)
    jds = plan.get("jds", {})
    for title, jd in jds.items():
        doc.add_heading(title, level=2)
        if jd.get("mission"):
            doc.add_paragraph(f"Mission: {jd['mission']}")
        if jd.get("requirements"):
            doc.add_paragraph("Requirements:")
            for r in jd["requirements"]:
                doc.add_paragraph(r, style='List Bullet 2')
        if jd.get("nice_to_haves"):
            doc.add_paragraph("Nice-to-haves:")
            for n in jd["nice_to_haves"]:
                doc.add_paragraph(n, style='List Bullet 2')
        if jd.get("benefits"):
            doc.add_paragraph("Benefits:")
            for b in jd["benefits"]:
                doc.add_paragraph(b, style='List Bullet 2')

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()
