from unittest.mock import MagicMock, patch

import pytest

from app.services.pages.file_explorer import (
    AWS_REGION,
    S3_BUCKET_NAME,
    delete_entries_by_path,
    delete_file_from_s3,
    fetch_all_files,
    generate_presigned_url,
    generate_s3_url,
    get_collection,
    list_s3_folders,
    save_file,
    store_file_metadata,
)


@pytest.fixture
def mock_boto_client():
    with patch('app.services.pages.file_explorer.boto3.client') as mock_client:
        yield mock_client.return_value


@pytest.fixture
def mock_mongo_client():
    with patch('app.services.pages.file_explorer.MongoClient') as mock_client:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.get_database.return_value = {'file_metadata': mock_collection}
        mock_client.return_value = mock_db
        yield mock_client


# -------------------------------
# TESTS
# -------------------------------


def test_generate_s3_url_us_east_1():
    url = generate_s3_url('test-bucket', 'file.txt', 'us-east-1')
    assert url == 'https://test-bucket.s3.amazonaws.com/file.txt'


def test_generate_s3_url_other_region():
    url = generate_s3_url('test-bucket', 'file.txt', 'eu-west-1')
    assert url == 'https://test-bucket.s3.eu-west-1.amazonaws.com/file.txt'


@patch('app.services.pages.file_explorer.s3_client.generate_presigned_url')
def test_generate_presigned_url_success(mock_presign):
    mock_presign.return_value = 'https://signed-url'
    url = generate_presigned_url('bucket', 'key/file.pdf')
    assert url == 'https://signed-url'
    mock_presign.assert_called_once()


@patch(
    'app.services.pages.file_explorer.s3_client.generate_presigned_url',
    side_effect=Exception('Error'),
)
def test_generate_presigned_url_failure(mock_presign):
    with pytest.raises(Exception) as exc_info:
        generate_presigned_url('bucket', 'key/file.txt')
    assert str(exc_info.value) == 'Error'


@patch('app.services.pages.file_explorer.s3_client.put_object')
def test_save_file(mock_put):
    result = save_file(b'hello', 'test.txt', 'folder')
    expected_url = generate_s3_url(S3_BUCKET_NAME, 'folder/test.txt', AWS_REGION)
    assert result == expected_url
    mock_put.assert_called_once()


@patch('app.services.pages.file_explorer.get_collection')
def test_store_file_metadata(mock_get_collection):
    mock_collection = MagicMock()
    mock_get_collection.return_value = mock_collection
    store_file_metadata('s3://path/file.txt', ['tag1', 'tag2'])
    mock_collection.insert_one.assert_called_once()


@patch('app.services.pages.file_explorer.s3_client.delete_object')
def test_delete_file_from_s3(mock_delete):
    delete_file_from_s3('somefile.txt')
    mock_delete.assert_called_once_with(Bucket=S3_BUCKET_NAME, Key='somefile.txt')


@patch('app.services.pages.file_explorer.get_collection')
@patch('app.services.pages.file_explorer.s3_client.delete_object')
def test_delete_entries_by_path(mock_delete, mock_get_collection):
    mock_collection = MagicMock()
    mock_get_collection.return_value = mock_collection
    delete_entries_by_path(['https://bucket.s3.amazonaws.com/folder/file.txt'])
    mock_delete.assert_called_once()
    mock_collection.delete_many.assert_called_once()


@patch('app.services.pages.file_explorer.get_collection')
def test_fetch_all_files(mock_get_collection):
    mock_collection = MagicMock()
    mock_collection.find.return_value = [{'file_path': 'test'}]
    mock_get_collection.return_value = mock_collection
    result = fetch_all_files()
    assert result == [{'file_path': 'test'}]


@patch('app.services.pages.file_explorer.s3_client.list_objects_v2')
def test_list_s3_folders(mock_list):
    mock_list.return_value = {
        'CommonPrefixes': [{'Prefix': 'folder1/'}, {'Prefix': 'folder2/'}]
    }
    folders = list_s3_folders()
    assert folders == ['', 'folder1', 'folder2']


@patch('app.services.pages.file_explorer.MongoClient')
def test_get_collection_success(mock_client):
    mock_instance = mock_client.return_value
    mock_instance.admin.command.return_value = True
    collection = get_collection()
    assert collection is not None
