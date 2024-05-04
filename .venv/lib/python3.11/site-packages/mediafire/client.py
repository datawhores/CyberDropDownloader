"""MediaFire Client"""

from __future__ import unicode_literals

import os
import hashlib
import logging
import requests
import posixpath

from six.moves.urllib.parse import urlparse

from mediafire.api import (MediaFireApi, MediaFireApiError)
from mediafire.uploader import (MediaFireUploader, UploadSession)

# These are educated guesses
QUICK_KEY_LENGTH = 15
FOLDER_KEY_LENGTH = 13

# All URIs must use this scheme
URI_SCHEME = 'mf'

logger = logging.getLogger(__name__)


class MediaFireError(Exception):
    """Base class for MediaFire errors"""
    pass


class ResourceNotFoundError(MediaFireError):
    """Raised when resource referenced cannot be found"""
    pass


class NotAFolderError(MediaFireError):
    """Raised when operation expects a folder but got something else"""
    pass


class DownloadError(MediaFireError):
    """Raised when download fails"""


class Resource(dict):
    """Base class for MediFire resources"""
    pass


class File(Resource):
    """MediaFire File resource"""
    pass


class Folder(Resource):
    """MediaFire Folder resource"""
    pass


class MediaFireClient(object):
    """A simple MediaFire Client."""

    def __init__(self, session_token=None, _api=None):
        """Initialize MediaFireClient.

        Keyword arguments:
        session_token -- previously acquired session_token dict
        """

        # support testing
        if _api is None:
            # pass-through to HTTP client
            self.api = MediaFireApi()
        else:
            self.api = _api()

        if session_token:
            self.api.session = session_token

    def login(self, email=None, password=None, app_id=None, api_key=None):
        """Login to MediaFire account.

        Keyword arguments:
        email -- account email
        password -- account password
        app_id -- application ID
        api_key -- API Key (optional)
        """
        session_token = self.api.user_get_session_token(
            app_id=app_id, email=email, password=password, api_key=api_key)

        # install session token back into api client
        self.api.session = session_token

    def get_resource_by_uri(self, uri):
        """Return resource described by MediaFire URI.

        uri -- MediaFire URI

        Examples:
            Folder (using folderkey):
            mf:r5g3p2z0sqs3j
            mf:r5g3p2z0sqs3j/folder/file.ext

            File (using quickkey):
            mf:xkr43dadqa3o2p2

            Path:
            mf:///Documents/file.ext
        """

        location = self._parse_uri(uri)

        if location.startswith("/"):
            # Use path lookup only, root=myfiles
            result = self.get_resource_by_path(location)
        elif "/" in location:
            # mf:abcdefjhijklm/name
            resource_key, path = location.split('/', 2)
            parent_folder = self.get_resource_by_key(resource_key)
            if not isinstance(parent_folder, Folder):
                raise NotAFolderError(resource_key)
            # perform additional lookup by path
            result = self.get_resource_by_path(
                path, folder_key=parent_folder['folderkey'])
        else:
            # mf:abcdefjhijklm
            result = self.get_resource_by_key(location)

        return result

    def get_resource_by_key(self, resource_key):
        """Return resource by quick_key/folder_key.

        key -- quick_key or folder_key
        """

        # search for quick_key by default
        lookup_order = ["quick_key", "folder_key"]

        if len(resource_key) == FOLDER_KEY_LENGTH:
            lookup_order = ["folder_key", "quick_key"]

        resource = None

        for lookup_key in lookup_order:
            try:
                if lookup_key == "folder_key":
                    info = self.api.folder_get_info(folder_key=resource_key)
                    resource = Folder(info['folder_info'])
                elif lookup_key == "quick_key":
                    info = self.api.file_get_info(quick_key=resource_key)
                    resource = File(info['file_info'])
            except MediaFireApiError:
                # TODO: Check response code
                pass

            if resource:
                break

        if not resource:
            raise ResourceNotFoundError(resource_key)

        return resource

    def get_resource_by_path(self, path, folder_key=None):
        """Return resource by remote path.

        path -- remote path

        Keyword arguments:
        folder_key -- what to use as the root folder (None for root)
        """
        logger.debug("resolving %s", path)

        # remove empty path components
        path = posixpath.normpath(path)
        components = [t for t in path.split(posixpath.sep) if t != '']

        if not components:
            # request for root
            return Folder(
                self.api.folder_get_info(folder_key)['folder_info']
            )

        resource = None

        for component in components:
            exists = False
            for item in self._folder_get_content_iter(folder_key):
                name = item['name'] if 'name' in item else item['filename']

                if name == component:
                    exists = True
                    if components[-1] != component:
                        # still have components to go through
                        if 'filename' in item:
                            # found a file, expected a directory
                            raise NotAFolderError(item['filename'])
                        folder_key = item['folderkey']
                    else:
                        # found the leaf
                        resource = item
                    break

                if resource is not None:
                    break

            if not exists:
                # intermediate component does not exist - bailing out
                break

        if resource is None:
            raise ResourceNotFoundError(path)

        if "quickkey" in resource:
            file_info = self.api.file_get_info(
                resource['quickkey'])['file_info']
            result = File(file_info)
        elif "folderkey" in resource:
            folder_info = self.api.folder_get_info(
                resource['folderkey'])['folder_info']
            result = Folder(folder_info)

        return result

    def _folder_get_content_iter(self, folder_key=None):
        """Iterator for api.folder_get_content"""

        lookup_params = [
            {'content_type': 'folders', 'node': 'folders'},
            {'content_type': 'files', 'node': 'files'}
        ]

        for param in lookup_params:
            more_chunks = True
            chunk = 0
            while more_chunks:
                chunk += 1
                content = self.api.folder_get_content(
                    content_type=param['content_type'], chunk=chunk,
                    folder_key=folder_key)['folder_content']

                # empty folder/file list
                if not content[param['node']]:
                    break

                # no next page
                if content['more_chunks'] == 'no':
                    more_chunks = False

                for resource_info in content[param['node']]:
                    yield resource_info

    def get_folder_contents_iter(self, uri):
        """Return iterator for directory contents.

        uri -- mediafire URI

        Example:

            for item in get_folder_contents_iter('mf:///Documents'):
                print(item)
        """
        resource = self.get_resource_by_uri(uri)

        if not isinstance(resource, Folder):
            raise NotAFolderError(uri)

        folder_key = resource['folderkey']

        for item in self._folder_get_content_iter(folder_key):
            if 'filename' in item:
                # Work around https://mediafire.mantishub.com/view.php?id=5
                # TODO: remove in 1.0
                if ".patch." in item['filename']:
                    continue
                yield File(item)
            elif 'name' in item:
                yield Folder(item)

    def create_folder(self, uri, recursive=False):
        """Create folder.

        uri -- MediaFire URI

        Keyword arguments:
        recursive -- set to True to create intermediate folders.
        """
        logger.info("Creating %s", uri)

        # check that folder exists already
        try:
            resource = self.get_resource_by_uri(uri)

            if isinstance(resource, Folder):
                return resource
            else:
                raise NotAFolderError(uri)
        except ResourceNotFoundError:
            pass

        location = self._parse_uri(uri)

        folder_name = posixpath.basename(location)
        parent_uri = 'mf://' + posixpath.dirname(location)

        try:
            parent_node = self.get_resource_by_uri(parent_uri)
            if not isinstance(parent_node, Folder):
                raise NotAFolderError(parent_uri)
            parent_key = parent_node['folderkey']
        except ResourceNotFoundError:
            if recursive:
                result = self.create_folder(parent_uri, recursive=True)
                parent_key = result['folderkey']
            else:
                raise

        # We specify exact location, so don't allow duplicates
        result = self.api.folder_create(
            folder_name, parent_key=parent_key, action_on_duplicate='skip')

        logger.info("Created folder '%s' [mf:%s]",
                    result['name'], result['folder_key'])

        return self.get_resource_by_key(result['folder_key'])

    def delete_folder(self, uri, purge=False):
        """Delete folder.

        uri -- MediaFire folder URI

        Keyword arguments:
        purge -- delete the folder without sending it to Trash
        """

        try:
            resource = self.get_resource_by_uri(uri)
        except ResourceNotFoundError:
            # Nothing to remove
            return None

        if not isinstance(resource, Folder):
            raise ValueError("Folder expected, got {}".format(type(resource)))

        if purge:
            func = self.api.folder_purge
        else:
            func = self.api.folder_delete

        try:
            result = func(resource['folderkey'])
        except MediaFireApiError as err:
            if err.code == 100:
                logger.debug(
                    "Delete folder returns error 900 but folder is deleted: "
                    "http://forum.mediafiredev.com/showthread.php?129")

                result = {}
            else:
                raise

        return result

    def delete_file(self, uri, purge=False):
        """Delete file.

        uri -- MediaFire file URI

        Keyword arguments:
        purge -- delete the file without sending it to Trash.
        """
        try:
            resource = self.get_resource_by_uri(uri)
        except ResourceNotFoundError:
            # Nothing to remove
            return None

        if not isinstance(resource, File):
            raise ValueError("File expected, got {}".format(type(resource)))

        if purge:
            func = self.api.file_purge
        else:
            func = self.api.file_delete

        return func(resource['quickkey'])

    def delete_resource(self, uri, purge=False):
        """Delete file or folder

        uri -- mediafire URI

        Keyword arguments:
        purge -- delete the resource without sending it to Trash.
        """
        try:
            resource = self.get_resource_by_uri(uri)
        except ResourceNotFoundError:
            # Nothing to remove
            return None

        if isinstance(resource, File):
            result = self.delete_file(uri, purge)
        elif isinstance(resource, Folder):
            result = self.delete_folder(uri, purge)
        else:
            raise ValueError('Unsupported resource: {}'.format(type(resource)))

        return result

    def upload_session(self):
        """Returns upload session context manager.

        Use this if you are uploading more than one file at a time.
        See http://mfi.re/developers/core_api/1.5/user/#get_action_token

        Example:

            with client.upload_session():
                for path in queue:
                    client.upload(path, 'mf:///Some/Folder')

        """
        return UploadSession(self.api)

    def _prepare_upload_info(self, source, dest_uri):
        """Prepare Upload object, resolve paths"""

        try:
            dest_resource = self.get_resource_by_uri(dest_uri)
        except ResourceNotFoundError:
            dest_resource = None

        is_fh = hasattr(source, 'read')

        folder_key = None
        name = None

        if dest_resource:
            if isinstance(dest_resource, File):
                folder_key = dest_resource['parent_folderkey']
                name = dest_resource['filename']
            elif isinstance(dest_resource, Folder):
                if is_fh:
                    raise ValueError("Cannot determine target file name")
                basename = posixpath.basename(source)
                dest_uri = posixpath.join(dest_uri, basename)
                try:
                    result = self.get_resource_by_uri(dest_uri)
                    if isinstance(result, Folder):
                        raise ValueError("Target is a folder (file expected)")
                    folder_key = result.get('parent_folderkey', None)
                    name = result['filename']
                except ResourceNotFoundError:
                    # ok, neither a file nor folder, proceed
                    folder_key = dest_resource['folderkey']
                    name = basename
            else:
                raise Exception("Unknown resource type")
        else:
            # get parent resource
            parent_uri = '/'.join(dest_uri.split('/')[0:-1])
            result = self.get_resource_by_uri(parent_uri)
            if not isinstance(result, Folder):
                raise NotAFolderError("Parent component is not a folder")

            folder_key = result['folderkey']
            name = posixpath.basename(dest_uri)

        return folder_key, name

    def upload_file(self, source, dest_uri):
        """Upload file to MediaFire.

        source -- path to the file or a file-like object (e.g. io.BytesIO)
        dest_uri -- MediaFire Resource URI
        """

        folder_key, name = self._prepare_upload_info(source, dest_uri)

        is_fh = hasattr(source, 'read')
        fd = None

        try:
            if is_fh:
                # Re-using filehandle
                fd = source
            else:
                # Handling fs open/close
                fd = open(source, 'rb')

            return MediaFireUploader(self.api).upload(
                fd, name, folder_key=folder_key,
                action_on_duplicate='replace')
        finally:
            # Close filehandle if we opened it
            if fd and not is_fh:
                fd.close()

    def download_file(self, src_uri, target):
        """Download file from MediaFire.

        src_uri -- MediaFire file URI to download
        target -- download path or file-like object in write mode
        """
        resource = self.get_resource_by_uri(src_uri)
        if not isinstance(resource, File):
            raise MediaFireError("Only files can be downloaded")

        quick_key = resource['quickkey']
        result = self.api.file_get_links(quick_key=quick_key,
                                         link_type='direct_download')
        direct_download = result['links'][0]['direct_download']

        # Force download over HTTPS
        direct_download = direct_download.replace('http:', 'https:')

        name = resource['filename']

        target_is_filehandle = True if hasattr(target, 'write') else False

        if not target_is_filehandle:
            if (os.path.exists(target) and os.path.isdir(target)) or \
                    target.endswith("/"):
                target = os.path.join(target, name)

            if not os.path.isdir(os.path.dirname(target)):
                os.makedirs(os.path.dirname(target))

            logger.info("Downloading %s to %s", src_uri, target)

        response = requests.get(direct_download, stream=True)
        try:
            if target_is_filehandle:
                out_fd = target
            else:
                out_fd = open(target, 'wb')

            checksum = hashlib.sha256()
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    out_fd.write(chunk)
                    checksum.update(chunk)

            checksum_hex = checksum.hexdigest().lower()
            if checksum_hex != resource['hash']:
                raise DownloadError("Hash mismatch ({} != {})".format(
                    resource['hash'], checksum_hex))

            logger.info("Download completed successfully")
        finally:
            if not target_is_filehandle:
                out_fd.close()

    # pylint: disable=too-many-arguments
    def update_file_metadata(self, uri, filename=None, description=None,
                             mtime=None, privacy=None):
        """Update file metadata.

        uri -- MediaFire file URI

        Supplying the following keyword arguments would change the
        metadata on the server side:

        filename -- rename file
        description -- set file description string
        mtime -- set file modification time
        privacy -- set file privacy - 'private' or 'public'
        """

        resource = self.get_resource_by_uri(uri)

        if not isinstance(resource, File):
            raise ValueError('Expected File, got {}'.format(type(resource)))

        result = self.api.file_update(resource['quickkey'], filename=filename,
                                      description=description,
                                      mtime=mtime, privacy=privacy)

        return result
    # pylint: enable=too-many-arguments

    # pylint: disable=too-many-arguments
    def update_folder_metadata(self, uri, foldername=None, description=None,
                               mtime=None, privacy=None,
                               privacy_recursive=None):
        """Update folder metadata.

        uri -- MediaFire file URI

        Supplying the following keyword arguments would change the
        metadata on the server side:

        filename -- rename file
        description -- set file description string
        mtime -- set file modification time
        privacy -- set file privacy - 'private' or 'public'
        recursive -- update folder privacy recursively
        """

        resource = self.get_resource_by_uri(uri)

        if not isinstance(resource, Folder):
            raise ValueError('Expected Folder, got {}'.format(type(resource)))

        result = self.api.folder_update(resource['folderkey'],
                                        foldername=foldername,
                                        description=description,
                                        mtime=mtime,
                                        privacy=privacy,
                                        privacy_recursive=privacy_recursive)

        return result
    # pylint: enable=too-many-arguments

    @staticmethod
    def _parse_uri(uri):
        """Parse and validate MediaFire URI."""

        tokens = urlparse(uri)

        if tokens.netloc != '':
            logger.error("Invalid URI: %s", uri)
            raise ValueError("MediaFire URI format error: "
                             "host should be empty - mf:///path")

        if tokens.scheme != '' and tokens.scheme != URI_SCHEME:
            raise ValueError("MediaFire URI format error: "
                             "must start with 'mf:' or '/'")

        return posixpath.normpath(tokens.path)
