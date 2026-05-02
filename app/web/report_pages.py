from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.version import VERSION_LABEL
from app.core.runtime_paths import paths
from app.utils.tool_pages import (
    delete_pdf_reader_file,
    get_pdf_reader_file_path,
    list_notes_history,
    list_pdf_reader_files,
    notes_file_path,
    read_app_notes,
    read_notes_version,
    save_pdf_reader_upload,
    write_app_notes,
)
from app.web.deps import csrf_protect, flash, get_current_user, template_context, templates

router = APIRouter()


@router.get("/reports", name="reports")
async def reports():
    return RedirectResponse("/", status_code=303)


@router.get("/sw.js", name="service_worker")
async def service_worker():
    return FileResponse(paths.static_dir / "sw.js", media_type="application/javascript")


@router.get("/notes", name="notes_page")
async def notes_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=303)
    view_version = request.query_params.get("v", "")
    current_content = read_app_notes()
    viewing_content = read_notes_version(view_version) if view_version else current_content
    note_path = notes_file_path()
    updated_at = datetime.fromtimestamp(note_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if note_path.exists() else None
    return templates.TemplateResponse(
        "notes.html",
        template_context(
            request,
            content=viewing_content,
            current_content=current_content,
            updated_at=updated_at,
            history=list_notes_history(),
            view_version=view_version,
        ),
    )


@router.post("/notes", name="notes_page")
async def notes_submit(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=303)
    await csrf_protect(request)
    form = await request.form()
    action = str(form.get("action", "save") or "save").strip()
    if action == "restore":
        filename = str(form.get("version_file", "") or "").strip()
        old_content = read_notes_version(filename)
        if old_content:
            write_app_notes(old_content)
            flash(request, "Version restauree avec succes.", "success")
        else:
            flash(request, "Version introuvable.", "danger")
    else:
        write_app_notes(str(form.get("content", "") or ""))
        flash(request, "Bloc-note enregistre.", "success")
    return RedirectResponse("/notes", status_code=303)


@router.get("/pdf-reader", name="pdf_reader")
async def pdf_reader(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=303)
    files = list_pdf_reader_files()
    selected = str(request.query_params.get("file", "") or "").strip()
    if selected and selected not in files:
        selected = ""
    return templates.TemplateResponse("pdf_reader.html", template_context(request, files=files, selected=selected))


@router.post("/pdf-reader", name="pdf_reader")
async def pdf_reader_submit(request: Request):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=303)
    await csrf_protect(request)
    form = await request.form()
    action = str(form.get("action", "upload") or "upload").strip()
    if action == "delete":
        filename = str(form.get("filename", "") or "").strip()
        if filename and delete_pdf_reader_file(filename):
            flash(request, f"PDF supprime : {filename}", "success")
        else:
            flash(request, "Fichier introuvable.", "warning")
        return RedirectResponse("/pdf-reader", status_code=303)
    uploaded = form.get("pdf_file")
    if not uploaded or not getattr(uploaded, "filename", ""):
        flash(request, "Choisis un fichier PDF.", "warning")
        return RedirectResponse("/pdf-reader", status_code=303)
    try:
        filename = save_pdf_reader_upload(uploaded)
    except ValueError as exc:
        flash(request, str(exc), "danger" if "acceptes" in str(exc) else "warning")
        return RedirectResponse("/pdf-reader", status_code=303)
    flash(request, f"PDF ajoute : {filename}", "success")
    return RedirectResponse(f"/pdf-reader?file={filename}", status_code=303)


@router.get("/pdf-reader/file/{filename:path}", name="pdf_reader_file")
async def pdf_reader_file(request: Request, filename: str):
    if not get_current_user(request):
        return RedirectResponse("/login", status_code=303)
    path = get_pdf_reader_file_path(filename)
    if not path:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(path, media_type="application/pdf")


@router.get("/health", name="health")
async def health():
    return JSONResponse({"ok": True, "service": "FABOuanes", "version": VERSION_LABEL})
