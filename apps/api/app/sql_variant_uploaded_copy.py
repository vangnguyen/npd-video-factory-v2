"""Bounded independent Local video/audio import; S3 real storage not configured.

Inherits exclusive writes, SHA/count verification and repeated-cancel draining.
Container magic is structural validation; it does not certify decoded video QC.
"""
import hashlib
import os
import stat
from .sql_variant_storyboard_copy import LocalStoryboardCopier, plain
from .sql_variant_repository import SqlVariantError

class LocalEvidenceCopier(LocalStoryboardCopier):
    @staticmethod
    def verify(path,content_type,size,checksum):
        if not content_type.startswith('video/') and content_type!='audio/flac':
            return LocalStoryboardCopier.verify(path,content_type,size,checksum)
        path=plain(path);before=path.stat()
        if before.st_size!=size or before.st_nlink!=1 or not stat.S_ISREG(before.st_mode):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        sha=hashlib.sha256();count=0;head=b''
        with path.open('rb') as inp:
            opened=os.fstat(inp.fileno())
            if (opened.st_dev,opened.st_ino,opened.st_size)!=(before.st_dev,before.st_ino,size):
                raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
            while True:
                block=inp.read(min(1024*1024,size-count+1))
                if not block:break
                count+=len(block)
                if count>size:raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
                sha.update(block)
                if len(head)<32:head=(head+block)[:32]
        after=plain(path).stat()
        if (count!=size or sha.hexdigest()!=checksum or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
            !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
            raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        if not (content_type=='video/mp4' and head[4:8]==b'ftyp' or content_type=='video/webm' and head[:4]==b'\x1a\x45\xdf\xa3'
            or content_type=='audio/flac' and head[:4]==b'fLaC'):
            raise SqlVariantError('SQL_VARIANT_COPY_MEDIA_INVALID')
        return None
