import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

AUDIOBOOK_OUTPUT_DIR = "audiobook_output"
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}


def list_audiobook_folders() -> List[str]:
    base = Path(AUDIOBOOK_OUTPUT_DIR)
    if not base.exists():
        return []
    return sorted(entry.name for entry in base.iterdir() if entry.is_dir())


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found in PATH. "
            "Install ffmpeg (e.g. 'brew install ffmpeg' on macOS, "
            "'apt install ffmpeg' on Linux) and ensure it is on your PATH."
        )


def _collect_audio_files(folder_path: str) -> List[Path]:
    folder = Path(folder_path)
    files = [f for f in folder.iterdir() if f.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS]

    def sort_key(p: Path) -> int:
        m = re.match(r"^(\d+)", p.name)
        return int(m.group(1)) if m else 999999

    return sorted(files, key=sort_key)


def _read_audio_duration(file_path: Path) -> float:
    try:
        if file_path.suffix.lower() == ".mp3":
            from mutagen.mp3 import MP3
            return MP3(str(file_path)).info.length
        else:
            import mutagen
            f = mutagen.File(str(file_path))
            if f is None:
                raise ValueError("mutagen returned None")
            return f.info.length
    except Exception as e:
        raise RuntimeError(f"Cannot read duration of {file_path.name}: {e}")


def _read_chapter_title_from_file(file_path: Path) -> str:
    try:
        from mutagen.id3 import ID3
        tags = ID3(str(file_path))
        title = str(tags.get("TIT2", [""])[0])
        if title:
            return title
    except Exception:
        pass
    name = re.sub(r"^\d+_", "", file_path.stem)
    return name.replace("_", " ").strip() or file_path.stem


def _read_metadata_from_folder(folder_path: str, audio_files: List[Path]) -> Tuple[str, str]:
    book_title, author = None, None
    if audio_files:
        try:
            from mutagen.id3 import ID3, ID3NoHeaderError
            tags = ID3(str(audio_files[0]))
            talb = tags.get("TALB")
            tpe1 = tags.get("TPE1")
            book_title = str(talb) if talb else None
            author = str(tpe1) if tpe1 else None
        except Exception:
            pass
    if not book_title or not author:
        folder_name = Path(folder_path).name
        if "_-_" in folder_name:
            parts = folder_name.split("_-_", 1)
            book_title = book_title or parts[0].replace("_", " ").strip()
            author = author or parts[1].replace("_", " ").strip()
        else:
            book_title = book_title or folder_name.replace("_", " ").strip()
            author = author or "Unknown Author"
    return book_title, author


def _build_ffmetadata(
    book_title: str,
    author: str,
    chapter_titles: List[str],
    durations_sec: List[float],
) -> str:
    lines = [
        ";FFMETADATA1",
        f"title={book_title}",
        f"artist={author}",
        f"album={book_title}",
        "",
    ]
    cursor_ms = 0
    for title, dur_sec in zip(chapter_titles, durations_sec):
        start_ms = cursor_ms
        end_ms = cursor_ms + int(dur_sec * 1000)
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={title}",
            "",
        ]
        cursor_ms = end_ms
    return "\n".join(lines)


def _build_concat_list(audio_files: List[Path]) -> str:
    lines = ["ffconcat version 1.0"]
    for f in audio_files:
        escaped = str(f.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines)


def export_to_m4b(folder_name: str) -> str:
    _check_ffmpeg()

    folder_path = os.path.join(AUDIOBOOK_OUTPUT_DIR, folder_name)
    if not os.path.isdir(folder_path):
        raise RuntimeError(f"Folder not found: {folder_path}")

    audio_files = _collect_audio_files(folder_path)
    if not audio_files:
        raise RuntimeError(f"No audio files found in {folder_path}")

    logger.info(f"Exporting {len(audio_files)} chapters from '{folder_name}' to M4B")

    book_title, author = _read_metadata_from_folder(folder_path, audio_files)
    chapter_titles = [_read_chapter_title_from_file(f) for f in audio_files]
    durations_sec = [_read_audio_duration(f) for f in audio_files]

    ffmetadata_str = _build_ffmetadata(book_title, author, chapter_titles, durations_sec)
    concat_str = _build_concat_list(audio_files)

    output_path = Path(AUDIOBOOK_OUTPUT_DIR) / f"{folder_name}.m4b"

    with tempfile.TemporaryDirectory() as tmp_dir:
        metadata_path = Path(tmp_dir) / "metadata.txt"
        concat_path = Path(tmp_dir) / "concat.txt"
        metadata_path.write_text(ffmetadata_str, encoding="utf-8")
        concat_path.write_text(concat_str, encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", str(metadata_path),
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-codec:a", "aac",
            "-b:a", "64k",
            "-vn",
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info("Running ffmpeg to encode M4B...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"ffmpeg error:\n{result.stderr[-1000:] if result.stderr else 'unknown'}")
                raise RuntimeError(f"ffmpeg exited with code {result.returncode}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"ffmpeg failed: {e}")

    logger.info(f"M4B export complete: {output_path}")
    return f"Export complete: {output_path.resolve()}"
