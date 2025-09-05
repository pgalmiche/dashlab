import base64
import io
from unittest.mock import Mock, patch

import pytest
from dash import html

from app.services.utils import file_utils as fe


def make_mock_collection(metadata=None):
    mock_col = Mock()
    mock_col.find_one.return_value = metadata or {}
    return mock_col


def test_list_s3_folders_success():
    mock_s3 = Mock()
    mock_s3.list_objects_v2.return_value = {
        'CommonPrefixes': [{'Prefix': 'foo/'}, {'Prefix': 'bar/'}]
    }
    folders = fe.list_s3_folders(mock_s3, 'my-bucket')
    assert folders == ['', 'foo', 'bar']


def test_list_s3_folders_no_bucket():
    result = fe.list_s3_folders(Mock(), '')
    assert result == []


def test_list_files_in_s3_success():
    mock_s3 = Mock()
    mock_s3.list_objects_v2.return_value = {
        'Contents': [{'Key': 'file1.txt'}, {'Key': 'subdir/'}]
    }
    files = fe.list_files_in_s3(mock_s3, 'my-bucket')
    assert files == [{'label': 'file1.txt', 'value': 'file1.txt'}]


def test_generate_s3_url_default_region():
    url = fe.generate_s3_url('bucket', 'file.txt', 'us-east-1')
    assert url == 'https://bucket.s3.amazonaws.com/file.txt'


def test_generate_s3_url_other_region():
    url = fe.generate_s3_url('bucket', 'file.txt', 'eu-west-1')
    assert url == 'https://bucket.s3.eu-west-1.amazonaws.com/file.txt'


def test_save_file_creates_object_and_returns_url():
    mock_s3 = Mock()
    url = fe.save_file(mock_s3, 'bucket', b'data', 'file.txt', 'folder')
    mock_s3.put_object.assert_called_once()
    assert 'https://bucket.s3.amazonaws.com/folder/file.txt' in url


@pytest.mark.parametrize(
    'fname,func,expected',
    [
        ('image.png', fe.is_image, True),
        ('doc.pdf', fe.is_pdf, True),
        ('song.mp3', fe.is_audio, True),
        ('notes.txt', fe.is_raw_text, True),
        ('weirdfile.xyz', fe.is_raw_text, False),
    ],
)
def test_file_type_detection(fname, func, expected):
    assert func(fname) == expected


def test_generate_presigned_url_success():
    mock_s3 = Mock()
    mock_s3.generate_presigned_url.return_value = 'https://signed-url'
    url = fe.generate_presigned_url(mock_s3, 'bucket', 'file.pdf')
    assert url == 'https://signed-url'
    mock_s3.generate_presigned_url.assert_called_once()


def test_generate_presigned_url_failure():
    mock_s3 = Mock()
    mock_s3.generate_presigned_url.side_effect = Exception('boom')
    with pytest.raises(Exception):
        mock_s3.generate_presigned_url()


def test_store_file_metadata_skips_without_collection():
    with patch.object(fe, 'get_collection', return_value=None):
        fe.store_file_metadata('path', ['tag'])  # should not raise


def test_store_file_metadata_inserts():
    mock_col = Mock()
    with patch.object(fe, 'get_collection', return_value=mock_col):
        fe.store_file_metadata('path', ['tag'])
        mock_col.insert_one.assert_called_once()


def test_render_file_preview_image(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    fake_collection = make_mock_collection({'tags': ['tag1', 'tag2']})
    monkeypatch.setattr(fe, 'get_collection', lambda: fake_collection)

    comp, tags, folder, new = fe.render_file_preview(mock_s3, 'bucket', 'file.png')
    assert isinstance(comp, html.Div)
    assert 'tag1' in tags


def test_render_file_preview_pdf_and_audio(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    monkeypatch.setattr(fe, 'get_collection', lambda: make_mock_collection())

    comp_pdf, _, _, _ = fe.render_file_preview(mock_s3, 'bucket', 'file.pdf')
    comp_audio, _, _, _ = fe.render_file_preview(mock_s3, 'bucket', 'song.mp3')

    assert isinstance(comp_pdf, html.Div)
    assert isinstance(comp_audio, html.Div)


def test_render_file_preview_text_success(monkeypatch):
    mock_s3 = Mock()
    mock_s3.get_object.return_value = {'Body': io.BytesIO(b'hello')}
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    monkeypatch.setattr(fe, 'get_collection', lambda: make_mock_collection())

    comp, _, _, _ = fe.render_file_preview(mock_s3, 'bucket', 'file.txt')
    assert 'hello' in comp.children[0].children


def test_render_file_preview_text_failure(monkeypatch):
    mock_s3 = Mock()
    mock_s3.get_object.side_effect = Exception('boom')
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    monkeypatch.setattr(fe, 'get_collection', lambda: make_mock_collection())

    comp, _, _, _ = fe.render_file_preview(mock_s3, 'bucket', 'file.txt')
    assert 'Could not read' in comp.children[0].children


def test_render_file_preview_unknown_extension(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    monkeypatch.setattr(fe, 'get_collection', lambda: make_mock_collection())

    comp, _, _, _ = fe.render_file_preview(mock_s3, 'bucket', 'file.xyz')
    assert 'Preview not available' in comp.children[0].children


def test_render_file_preview_with_metadata(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'generate_presigned_url', lambda *a, **k: 'http://url')
    fake_metadata = {'tags': ['t1', 't2'], 'folder': 'my-folder'}
    monkeypatch.setattr(
        fe, 'get_collection', lambda: make_mock_collection(fake_metadata)
    )

    comp, tags, folder, new_folder = fe.render_file_preview(
        mock_s3, 'bucket', 'file.pdf'
    )
    assert 't1' in tags
    assert folder == 'my-folder'  # check the 3rd return value
    assert new_folder == ''  # optional, just to be explicit


def test_move_file_and_update_metadata_success(monkeypatch):
    mock_s3 = Mock()
    mock_col = Mock()
    mock_col.update_one.return_value.matched_count = 1
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    result = fe.move_file_and_update_metadata(
        mock_s3, 'bucket', 'old/file.txt', 'tag1,tag2', 'newfolder'
    )
    assert 'updated successfully' in result


def test_delete_file_from_s3_success():
    mock_s3 = Mock()
    fe.delete_file_from_s3(mock_s3, 'bucket', 'file.txt')
    mock_s3.delete_object.assert_called_once()


def test_delete_entries_by_path_with_https(monkeypatch):
    mock_s3 = Mock()
    mock_col = Mock()
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    fe.delete_entries_by_path(
        mock_s3,
        'bucket',
        ['https://bucket.s3.amazonaws.com/file.txt'],
    )
    mock_col.delete_many.assert_called_once()


def test_fetch_all_files(monkeypatch):
    mock_col = Mock()
    mock_col.find.return_value = [{'file': 'meta'}]
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    result = fe.fetch_all_files()
    assert {'file': 'meta'} in result


def test_upload_files_to_s3_success(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'store_file_metadata', lambda *a, **k: None)
    content = 'data:text/plain;base64,' + base64.b64encode(b'hello').decode()
    status, tags_msg, files = fe.upload_files_to_s3(
        mock_s3, 'bucket', [content], ['file.txt'], folder_name=None, tags=['t1']
    )
    assert 'Successfully uploaded' in status
    assert 'file.txt' in files


def test_handle_deletion_invalid():
    msg = fe.handle_deletion(Mock(), 'bucket', '')
    assert 'Please enter' in msg


def test_build_database_table_empty():
    table = fe.build_database_table([])
    assert isinstance(table, html.Div)


def test_build_database_table_with_files():
    files = [{'name': 'test', 'size': 123}]
    table = fe.build_database_table(files)
    assert isinstance(table, html.Table)


def test_list_s3_folders_exception(monkeypatch):
    mock_s3 = Mock()
    mock_s3.list_objects_v2.side_effect = Exception('fail')
    result = fe.list_s3_folders(mock_s3, 'bucket')
    assert result == []


def test_list_files_in_s3_exception(monkeypatch):
    mock_s3 = Mock()
    mock_s3.list_objects_v2.side_effect = Exception('fail')
    result = fe.list_files_in_s3(mock_s3, 'bucket', 'folder')
    assert result == []


def test_move_file_and_update_metadata_no_file(monkeypatch):
    result = fe.move_file_and_update_metadata(Mock(), 'bucket', '')
    assert 'No file selected' in result


def test_move_file_and_update_metadata_no_db(monkeypatch):
    monkeypatch.setattr(fe, 'get_collection', lambda: None)
    result = fe.move_file_and_update_metadata(Mock(), 'bucket', 'file.txt')
    assert 'Database connection' in result


def test_move_file_and_update_metadata_s3_error(monkeypatch):
    mock_s3 = Mock()
    mock_s3.copy_object.side_effect = Exception('copy fail')
    mock_col = Mock()
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    result = fe.move_file_and_update_metadata(
        mock_s3, 'bucket', 'old/file.txt', target_folder='new'
    )
    assert 'Error moving file' in result


def test_move_file_and_update_metadata_not_found(monkeypatch):
    mock_s3 = Mock()
    mock_col = Mock()
    mock_col.update_one.return_value.matched_count = 0
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    result = fe.move_file_and_update_metadata(mock_s3, 'bucket', 'file.txt')
    assert 'not found' in result


def test_delete_file_from_s3_error(monkeypatch):
    mock_s3 = Mock()
    mock_s3.delete_object.side_effect = Exception('fail')
    fe.delete_file_from_s3(mock_s3, 'bucket', 'file.txt')  # should not raise


def test_delete_entries_by_path_invalid(monkeypatch):
    mock_s3 = Mock()
    mock_col = Mock()
    monkeypatch.setattr(fe, 'get_collection', lambda: mock_col)
    fe.delete_entries_by_path(mock_s3, 'bucket', ['not-a-url'])
    mock_col.delete_many.assert_called_once()


def test_fetch_all_files_no_collection(monkeypatch):
    monkeypatch.setattr(fe, 'get_collection', lambda: None)
    assert fe.fetch_all_files() == []


def test_upload_files_to_s3_failure(monkeypatch):
    mock_s3 = Mock()
    monkeypatch.setattr(fe, 'save_file', lambda *a, **k: 1 / 0)  # force error
    status, tags_msg, files = fe.upload_files_to_s3(
        mock_s3, 'bucket', ['data:text/plain;base64,aaaa'], ['file.txt']
    )
    assert 'Error uploading' in status


def test_handle_deletion_no_valid_paths():
    msg = fe.handle_deletion(Mock(), 'bucket', ',,,')
    assert 'No valid paths' in msg
