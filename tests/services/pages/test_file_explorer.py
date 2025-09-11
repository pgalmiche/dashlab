from unittest.mock import Mock

import pytest
from dash import html
from flask import session

import app.services.pages.file_explorer as fe


@pytest.fixture(autouse=True)
def app_ctx(monkeypatch):
    """Give us a Flask request context so session works."""
    from flask import Flask

    app = Flask(__name__)
    app.secret_key = 'testing'

    with app.test_request_context('/'):
        yield


def test_get_user_allowed_buckets_with_session():
    session['ALLOWED_BUCKETS'] = {'b1': 'us-east-1'}
    result = fe.get_user_allowed_buckets()
    assert result == {'b1': 'us-east-1'}


def test_get_user_allowed_buckets_default():
    session.clear()
    result = fe.get_user_allowed_buckets()
    assert 'dashlab-bucket' in result


def test_bucket_dropdown_builds_component():
    comp = fe.bucket_dropdown('my-id')
    assert isinstance(comp, html.Div)
    dd = comp.children[0]
    assert dd.id == 'my-id'


def test_upload_files_callback_success(monkeypatch):
    monkeypatch.setattr(
        fe, 'upload_files_to_s3', lambda *a, **k: ('ok', 'tags', ['f1'])
    )
    status, tags, ul = fe.upload_files_callback(
        ['content'], ['f1'], None, None, None, 'bucket', 'new_file_name'
    )
    assert 'ok' in status
    assert 'tags' in tags
    assert isinstance(ul, html.Ul)


def test_upload_files_callback_no_files_raises():
    with pytest.raises(fe.PreventUpdate):
        fe.upload_files_callback(
            None, None, None, None, None, 'bucket', 'new_file_name'
        )


def test_update_database_entries_refresh(monkeypatch):
    monkeypatch.setattr(fe, 'fetch_all_files', lambda: [{'file': 'meta'}])
    monkeypatch.setattr(fe, 'build_database_table', lambda files: html.Div('table'))

    fake_ctx = Mock()
    fake_ctx.triggered = [{'prop_id': 'refresh-btn.n_clicks'}]
    monkeypatch.setattr(fe, 'callback_context', fake_ctx)

    out = fe.update_database_entries_callback(1, 0, None, 'bucket')
    assert isinstance(out, html.Div)


def test_update_database_entries_delete(monkeypatch):
    monkeypatch.setattr(fe, 'handle_deletion', lambda *a, **k: 'error')
    monkeypatch.setattr(fe, 'fetch_all_files', lambda: [])
    monkeypatch.setattr(fe, 'build_database_table', lambda files: html.Div('table'))

    fake_ctx = Mock()
    fake_ctx.triggered = [{'prop_id': 'delete-btn.n_clicks'}]
    monkeypatch.setattr(fe, 'callback_context', fake_ctx)

    out = fe.update_database_entries_callback(0, 1, 'paths', 'bucket')
    assert 'error' in out.children


def test_update_file_selector_options(monkeypatch):
    monkeypatch.setattr(fe, 'list_files_in_s3', lambda *a, **k: ['f1', 'f2'])
    out = fe.update_file_selector_options('folder', 'bucket')
    assert 'f1' in out


def test_display_selected_file_none():
    comp, tags, folder, new = fe.display_selected_file(None, 'bucket')
    assert 'No file selected' in comp.children


def test_display_selected_file_with_file(monkeypatch):
    monkeypatch.setattr(
        fe,
        'render_file_preview',
        lambda *a, **k: (html.Div('file'), 'tags', 'folder', 'new'),
    )
    comp, tags, folder, new = fe.display_selected_file('f1', 'bucket')
    assert tags == 'tags'
    assert folder == 'folder'


def test_update_file_metadata_callback(monkeypatch):
    monkeypatch.setattr(fe, 'move_file_and_update_metadata', lambda *a, **k: 'done')
    msg = fe.update_file_metadata_callback(
        1, 'key', 'tags', 'folder', None, 'bucket', 'new_file_name'
    )
    assert msg == 'done'


def test_refresh_folder_options(monkeypatch):
    monkeypatch.setattr(fe, 'list_s3_folders', lambda *a, **k: ['', 'f1'])
    opts1, opts2, opts3 = fe.refresh_folder_options(None, 1, 'bucket', 'bucket')
    assert any(o['label'] == '(root)' for o in opts1)
    assert opts2 == opts3


def test_populate_upload_bucket_dropdown_with_user(monkeypatch):
    session['user'] = 'u1'
    session['ALLOWED_BUCKETS'] = {'b1': 'us-east-1'}
    session['DEFAULT_BUCKET'] = 'b1'
    opts, val = fe.populate_upload_bucket_dropdown('/file-explorer')
    assert opts[0]['value'] == 'b1'
    assert val == 'b1'


def test_populate_upload_bucket_dropdown_no_user():
    session.clear()
    with pytest.raises(fe.PreventUpdate):
        fe.populate_upload_bucket_dropdown('/file-explorer')


def test_populate_bucket_dropdown_with_user(monkeypatch):
    session['user'] = 'u1'
    session['ALLOWED_BUCKETS'] = {'b1': 'us-east-1'}
    session['DEFAULT_BUCKET'] = 'b1'
    opts, val = fe.populate_bucket_dropdown('/file-explorer')
    assert opts[0]['value'] == 'b1'
    assert val == 'b1'


def test_populate_bucket_dropdown_no_user():
    session.clear()
    with pytest.raises(fe.PreventUpdate):
        fe.populate_bucket_dropdown('/file-explorer')
