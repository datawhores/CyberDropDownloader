"""MediaFireUploader - API encapsulating Upload magic"""

from __future__ import unicode_literals

import hashlib
import logging
import math
import os
import time

from collections import namedtuple

from mediafire.subsetio import SubsetIO
from mediafire.api import MediaFireConnectionError

MEBIBYTE = 2 ** 20

# Use resumable upload if file is larger than 4MiB
UPLOAD_SIMPLE_LIMIT_BYTES = 4 * MEBIBYTE

# Retry resumable uploads 5 times
UPLOAD_RETRY_COUNT = 5

# Upload polling interval in seconds
UPLOAD_POLL_INTERVAL = 5

# Length of upload key
UPLOAD_KEY_LENGTH = 11

# File upload statuses
STATUS_NO_MORE_REQUESTS = 99
STATUS_UPLOAD_IN_PROGRESS = 17

# Read this much during hashing, must be a power of 2 and not more than 2 ** 10
HASH_CHUNK_SIZE_BYTES = 8192

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


# pylint: disable=too-few-public-methods,too-many-arguments
# pylint: disable=too-many-instance-attributes
class _UploadInfo(object):
    """Structure containing upload details"""

    def __init__(self, fd=None, name=None, folder_key=None, path=None,
                 hash_info=None, size=None, filedrop_key=None,
                 action_on_duplicate=None):
        self.fd = fd
        self.name = name
        self.folder_key = folder_key
        self.path = path
        self.hash_info = hash_info
        self.size = size
        self.filedrop_key = filedrop_key
        self.action_on_duplicate = action_on_duplicate


class _UploadUnitInfo(object):
    """Structure containing upload unit details"""
    def __init__(self, upload_info=None, fd=None, uid=None, hash_=None):
        self.upload_info = upload_info
        self.fd = fd
        self.uid = uid
        self.hash_ = hash_


UploadResult = namedtuple('UploadResult', [
    'action', 'quickkey', 'hash_', 'filename', 'size', 'created', 'revision'
])


# pylint: enable=too-few-public-methods,too-many-arguments
class UploadSession(object):  # pylint: disable=too-few-public-methods
    """Allocate/deallocate action token automatically"""

    def __init__(self, api):
        """Initialize context manager

        api -- MediaFireApi instance
        """
        self.action_token = None
        self._api = api

    def __enter__(self):
        """Allocate action token"""
        self.action_token = self._api.user_get_action_token(
            type_="upload", lifespan=1440)['action_token']

        self._api.set_action_token(type_="upload",
                                   action_token=self.action_token)

    def __exit__(self, *exc_details):
        """Destroys action token"""
        self._api.user_destroy_action_token(action_token=self.action_token)


class UploadError(Exception):
    """Basic upload error"""
    pass


class RetriableUploadError(UploadError):
    """Retriable upload error"""
    pass


MediaFireHashInfo = namedtuple('MediaFireHashInfo', [
    # sha256 digest of the whole file
    'file',
    # array of sha256 digests of upload units
    'units',
    # size of the file, for verification
    'size'
])


def decode_resumable_upload_bitmap(bitmap_node, number_of_units):
    """Decodes bitmap_node to hash of unit_id: is_uploaded

    bitmap_node -- bitmap node of resumable_upload with
                   'count' number and 'words' containing array
    number_of_units -- number of units we are uploading to
                       define the number of bits for bitmap
    """
    bitmap = 0
    for token_id in range(int(bitmap_node['count'])):
        value = int(bitmap_node['words'][token_id])
        bitmap = bitmap | (value << (0xf * token_id))

    result = {}

    for unit_id in range(number_of_units):
        mask = 1 << unit_id
        result[unit_id] = (bitmap & mask) == mask

    return result


def compute_hash_info(fd, unit_size=None):
    """Get MediaFireHashInfo structure from the fd, unit_size

    fd -- file descriptor - expects exclusive access because of seeking
    unit_size -- size of a single unit

    Returns MediaFireHashInfo:
    hi.file -- sha256 of the whole file
    hi.units -- list of sha256 hashes for each unit
    """

    logger.debug("compute_hash_info(%s, unit_size=%s)", fd, unit_size)

    fd.seek(0, os.SEEK_END)
    file_size = fd.tell()
    fd.seek(0, os.SEEK_SET)

    units = []
    unit_counter = 0

    file_hash = hashlib.sha256()
    unit_hash = hashlib.sha256()

    for chunk in iter(lambda: fd.read(HASH_CHUNK_SIZE_BYTES), b''):
        file_hash.update(chunk)

        unit_hash.update(chunk)
        unit_counter += len(chunk)

        if unit_size is not None and unit_counter == unit_size:
            # flush the current unit hash
            units.append(unit_hash.hexdigest().lower())
            unit_counter = 0
            unit_hash = hashlib.sha256()

    if unit_size is not None and unit_counter > 0:
        # leftover block
        units.append(unit_hash.hexdigest().lower())

    fd.seek(0, os.SEEK_SET)

    return MediaFireHashInfo(
        file=file_hash.hexdigest().lower(),
        units=units,
        size=file_size
    )


class MediaFireUploader(object):
    """API encapsulating Upload magic"""

    def __init__(self, api):
        """Initialize MediaFireUploader

        api -- MediaFireApi instance
        """
        self._api = api

    # pylint: disable=too-many-arguments
    def upload(self, fd, name=None, folder_key=None, filedrop_key=None,
               path=None, action_on_duplicate=None):
        """Upload file, returns UploadResult object

        fd -- file-like object to upload from, expects exclusive access
        name -- file name
        folder_key -- folderkey of the target folder
        path -- path to file relative to folder_key
        filedrop_key -- filedrop to use instead of folder_key
        action_on_duplicate -- skip, keep, replace
        """

        # Get file handle content length in the most reliable way
        fd.seek(0, os.SEEK_END)
        size = fd.tell()
        fd.seek(0, os.SEEK_SET)

        if size > UPLOAD_SIMPLE_LIMIT_BYTES:
            resumable = True
        else:
            resumable = False

        logger.debug("Calculating checksum")
        hash_info = compute_hash_info(fd)

        if hash_info.size != size:
            # Has the file changed beween computing the hash
            # and calling upload()?
            raise ValueError("hash_info.size mismatch")

        upload_info = _UploadInfo(fd=fd, name=name, folder_key=folder_key,
                                  hash_info=hash_info, size=size, path=path,
                                  filedrop_key=filedrop_key,
                                  action_on_duplicate=action_on_duplicate)

        # Check whether file is present
        check_result = self._upload_check(upload_info, resumable)

        upload_result = None
        upload_func = None

        folder_key = check_result.get('folder_key', None)
        if folder_key is not None:
            # We know precisely what folder_key to use, drop path
            upload_info.folder_key = folder_key
            upload_info.path = None

        if check_result['hash_exists'] == 'yes':
            # file exists somewhere in MediaFire
            if check_result['in_folder'] == 'yes' and \
                    check_result['file_exists'] == 'yes':
                # file exists in this directory
                different_hash = check_result.get('different_hash', 'no')
                if different_hash == 'no':
                    # file is already there
                    upload_func = self._upload_none

            if not upload_func:
                # different hash or in other folder
                upload_func = self._upload_instant

        if not upload_func:
            if resumable:
                resumable_upload_info = check_result['resumable_upload']
                upload_info.hash_info = compute_hash_info(
                    fd, int(resumable_upload_info['unit_size']))
                upload_func = self._upload_resumable
            else:
                upload_func = self._upload_simple

        # Retry retriable exceptions
        retries = UPLOAD_RETRY_COUNT
        while retries > 0:
            try:
                # Provide check_result to avoid calling API twice
                upload_result = upload_func(upload_info, check_result)
            except (RetriableUploadError, MediaFireConnectionError):
                retries -= 1
                logger.exception("%s failed (%d retries left)",
                                 upload_func.__name__, retries)
                # Refresh check_result for next iteration
                check_result = self._upload_check(upload_info, resumable)
            except Exception:
                logger.exception("%s failed", upload_func)
                break
            else:
                break

        if upload_result is None:
            raise UploadError("Upload failed")

        return upload_result
    # pylint: enable=too-many-arguments

    def _poll_upload(self, upload_key, action):
        """Poll upload until quickkey is found

        upload_key -- upload_key returned by upload/* functions
        """

        if len(upload_key) != UPLOAD_KEY_LENGTH:
            # not a regular 11-char-long upload key
            # There is no API to poll filedrop uploads
            return UploadResult(
                action=action,
                quickkey=None,
                hash_=None,
                filename=None,
                size=None,
                created=None,
                revision=None
            )

        quick_key = None
        while quick_key is None:
            poll_result = self._api.upload_poll(upload_key)
            doupload = poll_result['doupload']

            logger.debug("poll(%s): status=%d, description=%s, filename=%s,"
                         " result=%d",
                         upload_key, int(doupload['status']),
                         doupload['description'], doupload['filename'],
                         int(doupload['result']))

            if int(doupload['result']) != 0:
                break

            if 'fileerror' in doupload and doupload['fileerror']:
                raise UploadError('Got fileerror={} while uploading {}'.format(
                    doupload['fileerror'], upload_key))

            if int(doupload['status']) == STATUS_NO_MORE_REQUESTS:
                quick_key = doupload['quickkey']
            elif int(doupload['status']) == STATUS_UPLOAD_IN_PROGRESS:
                # BUG: http://forum.mediafiredev.com/showthread.php?588
                raise RetriableUploadError(
                    "Invalid state transition ({})".format(
                        doupload['description']
                    )
                )
            else:
                time.sleep(UPLOAD_POLL_INTERVAL)

        return UploadResult(
            action=action,
            quickkey=doupload['quickkey'],
            hash_=doupload['hash'],
            filename=doupload['filename'],
            size=doupload['size'],
            created=doupload['created'],
            revision=doupload['revision']
        )

    def _upload_check(self, upload_info, resumable=False):
        """Wrapper around upload/check"""
        return self._api.upload_check(
            filename=upload_info.name,
            size=upload_info.size,
            hash_=upload_info.hash_info.file,
            folder_key=upload_info.folder_key,
            filedrop_key=upload_info.filedrop_key,
            path=upload_info.path,
            resumable=resumable
        )

    # pylint: disable=no-self-use
    # We just provide a consistent interface
    def _upload_none(self, upload_info, check_result):
        """Dummy upload function for when we don't actually upload"""
        return UploadResult(
            action=None,
            quickkey=check_result['duplicate_quickkey'],
            hash_=upload_info.hash_info.file,
            filename=upload_info.name,
            size=upload_info.size,
            created=None,
            revision=None
        )
    # pylint: enable=no-self-use

    def _upload_instant(self, upload_info, _=None):
        """Instant upload and return quickkey

        Can be used when the file is already stored somewhere in MediaFire

        upload_info -- UploadInfo object
        check_result -- ignored
        """

        result = self._api.upload_instant(
            upload_info.name,
            upload_info.size,
            upload_info.hash_info.file,
            path=upload_info.path,
            folder_key=upload_info.folder_key,
            filedrop_key=upload_info.filedrop_key,
            action_on_duplicate=upload_info.action_on_duplicate
        )

        return UploadResult(
            action='upload/instant',
            quickkey=result['quickkey'],
            filename=result['filename'],
            revision=result['new_device_revision'],
            hash_=upload_info.hash_info.file,
            size=upload_info.size,
            created=None
        )

    def _upload_simple(self, upload_info, _=None):
        """Simple upload and return quickkey

        Can be used for small files smaller than UPLOAD_SIMPLE_LIMIT_BYTES

        upload_info -- UploadInfo object
        check_result -- ignored
        """

        upload_result = self._api.upload_simple(
            upload_info.fd,
            upload_info.name,
            folder_key=upload_info.folder_key,
            filedrop_key=upload_info.filedrop_key,
            path=upload_info.path,
            file_size=upload_info.size,
            file_hash=upload_info.hash_info.file,
            action_on_duplicate=upload_info.action_on_duplicate)

        logger.debug("upload_result: %s", upload_result)

        upload_key = upload_result['doupload']['key']

        return self._poll_upload(upload_key, 'upload/simple')

    def _upload_resumable_unit(self, uu_info):
        """Upload a single unit and return raw upload/resumable result

        uu_info -- UploadUnitInfo instance
        """

        # Get actual unit size
        unit_size = uu_info.fd.len

        if uu_info.hash_ is None:
            raise ValueError('UploadUnitInfo.hash_ is now required')

        return self._api.upload_resumable(
            uu_info.fd,
            uu_info.upload_info.size,
            uu_info.upload_info.hash_info.file,
            uu_info.hash_,
            uu_info.uid,
            unit_size,
            filedrop_key=uu_info.upload_info.filedrop_key,
            folder_key=uu_info.upload_info.folder_key,
            path=uu_info.upload_info.path,
            action_on_duplicate=uu_info.upload_info.action_on_duplicate)

    def _upload_resumable_all(self, upload_info, bitmap,
                              number_of_units, unit_size):
        """Prepare and upload all resumable units and return upload_key

        upload_info -- UploadInfo object
        bitmap -- bitmap node of upload/check
        number_of_units -- number of units requested
        unit_size -- size of a single upload unit in bytes
        """

        fd = upload_info.fd

        upload_key = None

        for unit_id in range(number_of_units):
            upload_status = decode_resumable_upload_bitmap(
                bitmap, number_of_units)

            if upload_status[unit_id]:
                logger.debug("Skipping unit %d/%d - already uploaded",
                             unit_id + 1, number_of_units)
                continue

            logger.debug("Uploading unit %d/%d",
                         unit_id + 1, number_of_units)

            offset = unit_id * unit_size

            with SubsetIO(fd, offset, unit_size) as unit_fd:

                unit_info = _UploadUnitInfo(
                    upload_info=upload_info,
                    hash_=upload_info.hash_info.units[unit_id],
                    fd=unit_fd,
                    uid=unit_id)

                upload_result = self._upload_resumable_unit(unit_info)

                # upload_key is needed for polling
                if upload_key is None:
                    upload_key = upload_result['doupload']['key']

        return upload_key

    def _upload_resumable(self, upload_info, check_result):
        """Resumable upload and return quickkey

        upload_info -- UploadInfo object
        check_result -- dict of upload/check call result
        """

        resumable_upload = check_result['resumable_upload']

        unit_size = int(resumable_upload['unit_size'])
        number_of_units = int(resumable_upload['number_of_units'])

        # make sure we have calculated the right thing
        logger.debug("number_of_units=%s (expected %s)",
                     number_of_units, len(upload_info.hash_info.units))
        assert len(upload_info.hash_info.units) == number_of_units

        logger.debug("Preparing %d units * %d bytes",
                     number_of_units, unit_size)

        upload_key = None
        retries = UPLOAD_RETRY_COUNT

        all_units_ready = resumable_upload['all_units_ready'] == 'yes'
        bitmap = resumable_upload['bitmap']

        while not all_units_ready and retries > 0:
            upload_key = self._upload_resumable_all(upload_info, bitmap,
                                                    number_of_units, unit_size)

            check_result = self._upload_check(upload_info, resumable=True)

            resumable_upload = check_result['resumable_upload']
            all_units_ready = resumable_upload['all_units_ready'] == 'yes'
            bitmap = resumable_upload['bitmap']

            if not all_units_ready:
                retries -= 1
                logger.debug("Some units failed to upload (%d retries left)",
                             retries)

        if not all_units_ready:
            # Most likely non-retriable
            raise UploadError("Could not upload all units")

        logger.debug("Upload complete, polling for status")

        return self._poll_upload(upload_key, 'upload/resumable')
