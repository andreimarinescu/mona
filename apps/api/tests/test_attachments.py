"""C4 §5 item 3: the `ingest_attachment` path guard (§4.2, A13)."""

import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mona import attachments
from mona.attachments import Refused, open_attachment, read_all

NAME = "doc_0123456789ab_relevé.pdf"


@pytest.fixture
def root(tmp_path) -> Path:
    r = tmp_path / "cache"
    for sub in ("documents", "images", "audio", "documents-evil"):
        (r / sub).mkdir(parents=True)
    (r / "documents" / NAME).write_bytes(b"%PDF-doc")
    (r / "images" / "img_0123456789ab.jpg").write_bytes(b"\xff\xd8\xffimg")
    (r / "audio" / "aud_0123456789ab.ogg").write_bytes(b"OggS")
    (r / "documents-evil" / "x.pdf").write_bytes(b"%PDF-evil")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.pdf").write_bytes(b"%PDF-secret")
    return r


def opened(root: Path, path: str) -> bytes:
    att = open_attachment(str(root), path)
    return read_all(att.fd, 1024)


def refused(root: Path, path: str) -> str:
    with pytest.raises(Refused) as err:
        att = open_attachment(str(root), path)
        os.close(att.fd)
    return err.value.code


def test_files_under_documents_and_images_open_by_relative_and_absolute_path(root):
    assert opened(root, f"documents/{NAME}") == b"%PDF-doc"
    assert opened(root, str(root / "documents" / NAME)) == b"%PDF-doc"
    assert opened(root, "images/img_0123456789ab.jpg") == b"\xff\xd8\xffimg"
    assert opened(root, str(root / "images" / "img_0123456789ab.jpg")) == b"\xff\xd8\xffimg"


def test_a_retyped_name_is_found_by_its_hermes_prefix(root):
    nfd = unicodedata.normalize("NFD", NAME)
    os.rename(root / "documents" / NAME, root / "documents" / nfd)
    nfc = str(root / "documents" / unicodedata.normalize("NFC", NAME))
    assert nfc != str(root / "documents" / nfd)
    att = open_attachment(str(root), nfc)
    assert att.rel == f"documents/{nfd}" and read_all(att.fd, 1024) == b"%PDF-doc"


def test_a_prefix_lookup_needs_exactly_one_match(root):
    (root / "documents" / "doc_0123456789ab_other.pdf").write_bytes(b"%PDF-2")
    assert refused(root, "documents/doc_0123456789ab_typo.pdf") == "invalid_argument"
    assert refused(root, "documents/no-prefix.pdf") == "invalid_argument"


def test_a_prefix_match_that_is_a_link_outside_is_refused(root, tmp_path):
    (root / "documents" / NAME).unlink()
    os.symlink(tmp_path / "outside" / "secret.pdf", root / "documents" / NAME)
    assert refused(root, "documents/doc_0123456789ab_retyped.pdf") == "forbidden_path"


@pytest.mark.parametrize(
    "path",
    [
        "../outside/secret.pdf",
        "documents/../../outside/secret.pdf",
        "/etc/passwd",
        "audio/aud_0123456789ab.ogg",
        "documents-evil/x.pdf",
        "documents",
        "documents\\x.pdf",
        "documents/x\x00.pdf",
    ],
)
def test_paths_outside_the_two_subtrees_are_forbidden(root, path):
    assert refused(root, path) == "forbidden_path"


def test_absolute_paths_elsewhere_are_forbidden(root, tmp_path):
    assert refused(root, str(tmp_path / "outside" / "secret.pdf")) == "forbidden_path"
    assert refused(root, str(root / "documents-evil" / "x.pdf")) == "forbidden_path"


def test_a_symlink_in_the_volume_pointing_outside_is_forbidden(root, tmp_path):
    os.symlink(tmp_path / "outside" / "secret.pdf", root / "documents" / "doc_aaaaaaaaaaaa_l.pdf")
    assert refused(root, "documents/doc_aaaaaaaaaaaa_l.pdf") == "forbidden_path"


def test_a_directory_symlink_in_the_chain_is_forbidden(root, tmp_path):
    os.symlink(tmp_path / "outside", root / "documents" / "sub")
    assert refused(root, "documents/sub/secret.pdf") == "forbidden_path"


def test_missing_files_and_folders_are_invalid_arguments(root):
    (root / "documents" / "folder").mkdir()
    assert refused(root, "documents/doc_ffffffffffff_gone.pdf") == "invalid_argument"
    assert refused(root, "documents/folder") == "invalid_argument"


def swap_after_resolve(monkeypatch, swap) -> None:
    real = attachments.resolve

    def resolve_then_swap(root: str, path: str) -> str:
        rel = real(root, path)
        swap()
        return rel

    monkeypatch.setattr(attachments, "resolve", resolve_then_swap)


def test_a_file_swapped_for_a_symlink_after_the_check_is_forbidden(root, tmp_path, monkeypatch):
    target = root / "documents" / NAME

    def swap():
        target.unlink()
        os.symlink(tmp_path / "outside" / "secret.pdf", target)

    swap_after_resolve(monkeypatch, swap)
    assert refused(root, f"documents/{NAME}") == "forbidden_path"


def test_a_folder_swapped_for_a_symlink_after_the_check_is_forbidden(root, tmp_path, monkeypatch):
    sub = root / "documents" / "sub"
    sub.mkdir()
    (sub / "secret.pdf").write_bytes(b"%PDF-inside")

    def swap():
        os.rename(sub, root / "documents" / "sub.old")
        os.symlink(tmp_path / "outside", sub)

    swap_after_resolve(monkeypatch, swap)
    assert refused(root, "documents/sub/secret.pdf") == "forbidden_path"


def test_a_fifo_is_forbidden_without_blocking(root):
    fifo = root / "documents" / "doc_bbbbbbbbbbbb_pipe.pdf"
    os.mkfifo(fifo)
    pool = ThreadPoolExecutor(1)
    try:
        code = pool.submit(refused, root, "documents/doc_bbbbbbbbbbbb_pipe.pdf").result(timeout=5)
    finally:
        try:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        except OSError:
            pass
        pool.shutdown(wait=False)
    assert code == "forbidden_path"


def test_read_all_stops_past_the_limit(root):
    att = open_attachment(str(root), f"documents/{NAME}")
    assert read_all(att.fd, 3) is None
