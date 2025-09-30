import io
from unittest.mock import Mock

from dash import html

from app.services.utils import ui_utils as fe


def test_render_file_preview_image(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    # tags/folder are no longer returned, so collection is irrelevant
    comp, tags, folder, new = fe.render_file_preview(mock_s3, 'bucket', 'file.png')
    assert isinstance(comp, html.Div)
    # tags/folder/new are empty strings
    assert tags == ''
    assert folder == ''
    assert new == ''


def test_render_file_preview_text_success(monkeypatch):
    mock_s3 = Mock()
    mock_s3.get_object.return_value = {'Body': io.BytesIO(b'hello')}
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    comp, tags, folder, new = fe.render_file_preview(mock_s3, 'bucket', 'file.txt')
    # Text preview no longer works, should fallback
    assert 'Preview not available' in comp.children[0].children
    assert tags == ''
    assert folder == ''
    assert new == ''


def test_render_file_preview_text_failure(monkeypatch):
    mock_s3 = Mock()
    mock_s3.get_object.side_effect = Exception('boom')
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    comp, tags, folder, new = fe.render_file_preview(mock_s3, 'bucket', 'file.txt')
    assert 'Preview not available' in comp.children[0].children
    assert tags == ''
    assert folder == ''
    assert new == ''


def test_render_file_preview_with_metadata(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    comp, tags, folder, new_folder = fe.render_file_preview(
        mock_s3, 'bucket', 'file.pdf'
    )
    # metadata is no longer returned
    assert tags == ''
    assert folder == ''
    assert new_folder == ''
    assert isinstance(comp, html.Div)
