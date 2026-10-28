import io
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse


def protected_file_response(upload, display_name):
    if not upload:
        raise Http404("File not found.")
    try:
        media_root = Path(settings.MEDIA_ROOT).resolve(strict=True)
        resolved_path = Path(upload.path).resolve(strict=True)
        resolved_path.relative_to(media_root)
        if not resolved_path.is_file():
            raise Http404("File not found.")
    except (OSError, ValueError, SuspiciousFileOperation) as exc:
        raise Http404("File not found.") from exc

    filename = display_name or resolved_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if getattr(settings, "USE_X_ACCEL_REDIRECT", False):
        relative_path = resolved_path.relative_to(media_root).as_posix()
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = f"/protected_media/{relative_path}"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    file_size = resolved_path.stat().st_size
    if file_size <= 8 * 1024 * 1024:
        return FileResponse(io.BytesIO(resolved_path.read_bytes()), as_attachment=True, filename=filename, content_type=content_type)
    return FileResponse(resolved_path.open("rb"), as_attachment=True, filename=filename, content_type=content_type)
