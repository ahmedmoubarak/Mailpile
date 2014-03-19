# coding: utf-8
#
# Misc. utility functions for Mailpile.
#
import cgi
import datetime
import hashlib
import locale
import re
import subprocess
import os
import sys
import string
import tempfile
import threading
import time
import StringIO
from gettext import gettext as _

try:
    from PIL import Image
except:
    Image = None


global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT, QUITTING


QUITTING = False

DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]'
                         ':\"|;\'\\\<\>\?,\.\/\-]{2,}')

STOPLIST = set(['an', 'and', 'are', 'as', 'at', 'by', 'for', 'from',
                'has', 'http', 'https', 'i', 'in', 'is', 'it',
                'mailto', 'me',
                'og', 'or', 're', 'so', 'the', 'to', 'was', 'you'])

BORING_HEADERS = ('received', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'dkim-signature', 'domainkey-signature', 'received-spf')

EXPECTED_HEADERS = ('from', 'to', 'subject', 'date')

B64C_STRIP = '\n='

B64C_TRANSLATE = string.maketrans('/', '_')

B64W_TRANSLATE = string.maketrans('/+', '_-')

STRHASH_RE = re.compile('[^0-9a-z]+')

B36_ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


class WorkerError(Exception):
    pass


class UsageError(Exception):
    pass


class AccessError(Exception):
    pass


class UrlRedirectException(Exception):
    """An exception indicating we need to redirecting to another URL."""
    def __init__(self, url):
        Exception.__init__(self, 'Should redirect to: %s' % url)
        self.url = url


def b64c(b):
    """
    Rewrite a base64 string:
        - Remove LF and = characters
        - Replace slashes by underscores

    >>> b64c("abc123456def")
    'abc123456def'
    >>> b64c("\\na/=b=c/")
    'a_bc_'
    >>> b64c("a+b+c+123+")
    'a+b+c+123+'
    """
    return string.translate(b, B64C_TRANSLATE, B64C_STRIP)


def b64w(b):
    """
    Rewrite a base64 string by replacing
    "+" by "-" (e.g. for URLs).

    >>> b64w("abc123456def")
    'abc123456def'
    >>> b64w("a+b+c+123+")
    'a-b-c-123-'
    """
    return string.translate(b, B64W_TRANSLATE, B64C_STRIP)


def escape_html(t):
    """
    Replace characters that have a special meaning in HTML
    by their entity equivalents. Return the replaced
    string.

    >>> escape_html("Hello, Goodbye.")
    'Hello, Goodbye.'
    >>> escape_html("Hello<>World")
    'Hello&lt;&gt;World'
    >>> escape_html("<&>")
    '&lt;&amp;&gt;'

    Keyword arguments:
    t -- The string to escape
    """
    return cgi.escape(t)


def _hash(cls, data):
    h = cls()
    for s in data:
        if isinstance(s, unicode):
            h.update(s.encode('utf-8'))
        else:
            h.update(s)
    return h


def sha1b64(s):
    """
    Apply the SHA1 hash algorithm to a string
    and return the base64-encoded hash value

    >>> sha1b64("Hello")
    '9/+ei3uy4Jtwk1pdeF4MxdnQq/A=\\n'

    >>> sha1b64(u"Hello")
    '9/+ei3uy4Jtwk1pdeF4MxdnQq/A=\\n'

    Keyword arguments:
    s -- The string to hash
    """
    return _hash(hashlib.sha1, [s]).digest().encode('base64')


def sha512b64(*data):
    """
    Apply the SHA512 hash algorithm to a string
    and return the base64-encoded hash value

    >>> sha512b64("Hello")[:64]
    'NhX4DJ0pPtdAJof5SyLVjlKbjMeRb4+sf933+9WvTPd309eVp6AKFr9+fz+5Vh7p'
    >>> sha512b64(u"Hello")[:64]
    'NhX4DJ0pPtdAJof5SyLVjlKbjMeRb4+sf933+9WvTPd309eVp6AKFr9+fz+5Vh7p'

    Keyword arguments:
    s -- The string to hash
    """
    return _hash(hashlib.sha512, data).digest().encode('base64')


def md5_hex(*data):
    return _hash(hashlib.md5, data).hexdigest()


def strhash(s, length, obfuscate=None):
    """
    Create a hash of

    >>> strhash("Hello", 10)
    'hello9_+ei'
    >>> strhash("Goodbye", 5, obfuscate="mysalt")
    'voxpj'

    Keyword arguments:
    s -- The string to be hashed
    length -- The length of the hash to create.
                        Might be limited by the hash method
    obfuscate -- None to disable SHA512 obfuscation,
                             or a salt to append to the string
                             before hashing
    """
    if obfuscate:
        hashedStr = b64c(sha512b64(s, obfuscate).lower())
    else:  # Don't obfuscate
        hashedStr = re.sub(STRHASH_RE, '', s.lower())[:(length - 4)]
        while len(hashedStr) < length:
            hashedStr += b64c(sha1b64(s)).lower()
    return hashedStr[:length]


def b36(number):
    """
    Convert a number to base36

    >>> b36(2701)
    '231'
    >>> b36(12345)
    '9IX'
    >>> b36(None)
    '0'

    Keyword arguments:
    number -- An integer to convert to base36
    """
    if not number or number < 0:
        return B36_ALPHABET[0]
    base36 = []
    while number:
        number, i = divmod(number, 36)
        base36.append(B36_ALPHABET[i])
    return ''.join(reversed(base36))


def elapsed_datetime(timestamp):
    """
    Return "X days ago" style relative dates for recent dates.
    """
    ts = datetime.date.fromtimestamp(timestamp)
    days_ago = (datetime.date.today() - ts).days

    if days_ago < 1:
        return _('today')
    elif days_ago < 2:
        return _('%d day') % days_ago
    elif days_ago < 7:
        return _('%d days') % days_ago
    elif days_ago < 366:
        return ts.strftime("%b %d")
    else:
        return ts.strftime("%b %d %Y")


def friendly_datetime(timestamp):
    date = datetime.date.fromtimestamp(timestamp)
    return date.strftime("%b %d, %Y")


def friendly_time(timestamp):
    date = datetime.datetime.fromtimestamp(timestamp)
    return date.strftime("%H:%M")


def friendly_number(number, base=1000, decimals=0, suffix='',
                    powers=['', 'k', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']):
    """
    Format a number as friendly text, using common suffixes.

    >>> friendly_number(102)
    '102'
    >>> friendly_number(10240)
    '10k'
    >>> friendly_number(12341234, decimals=1)
    '12.3M'
    >>> friendly_number(1024000000, base=1024, suffix='iB')
    '976MiB'
    """
    count = 0
    number = float(number)
    while number > base and count < len(powers):
        number /= base
        count += 1
    if decimals:
        fmt = '%%.%df%%s%%s' % decimals
    else:
        fmt = '%d%s%s'
    return fmt % (number, powers[count], suffix)


GPG_BEGIN_MESSAGE = '-----BEGIN PGP MESSAGE'
GPG_END_MESSAGE = '-----END PGP MESSAGE'


def decrypt_gpg(lines, fd):
    for line in fd:
        lines.append(line)
        if line.startswith(GPG_END_MESSAGE):
            break

    gpg = subprocess.Popen(['gpg', '--batch'],
                           stdin=subprocess.PIPE,
                           stderr=subprocess.PIPE,
                           stdout=subprocess.PIPE)
    lines = gpg.communicate(input=''.join(lines))[0].splitlines(True)
    if gpg.wait() != 0:
        raise AccessError("GPG was unable to decrypt the data.")

    return lines


def decrypt_and_parse_lines(fd, parser, config, newlines=False):
    import mailpile.crypto.symencrypt as symencrypt
    if not newlines:
        _parser = lambda l: parser(l.rstrip('\r\n'))
    else:
        _parser = parser
    size = 0
    while True:
        line = fd.readline(102400)
        if line == '':
            break
        size += len(line)
        if line.startswith(GPG_BEGIN_MESSAGE):
            for line in decrypt_gpg([line], fd):
                _parser(line.decode('utf-8'))
        elif line.startswith(symencrypt.SymmetricEncrypter.BEGIN_DATA):
            if not config or not config.prefs.obfuscate_index:
                raise ValueError(_("Symmetric decryption is not available "
                                   "without config and key."))
            for line in symencrypt.SymmetricEncrypter(
                    config.prefs.obfuscate_index).decrypt_fd([line], fd):
                _parser(line.decode('utf-8'))
        else:
            _parser(line.decode('utf-8'))
    return size


def backup_file(filename, backups=5, min_age_delta=0):
    if os.path.exists(filename):
        if os.stat(filename).st_mtime >= time.time() - min_age_delta:
            return

        for ver in reversed(range(1, backups)):
            bf = '%s.%d' % (filename, ver)
            if os.path.exists(bf):
                nbf = '%s.%d' % (filename, ver+1)
                if os.path.exists(nbf):
                    os.remove(nbf)
                os.rename(bf, nbf)
        os.rename(filename, '%s.1' % filename)


class GpgWriter(object):
    def __init__(self, gpg):
        self.fd = gpg.stdin
        self.gpg = gpg

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def write(self, data):
        self.fd.write(data)

    def close(self):
        self.fd.close()
        self.gpg.wait()


def gpg_open(filename, recipient, mode):
    fd = open(filename, mode)
    if recipient and ('a' in mode or 'w' in mode):
        gpg = subprocess.Popen(['gpg', '--batch', '-aer', recipient],
                               stdin=subprocess.PIPE,
                               stdout=fd)
        return GpgWriter(gpg)
    return fd


def dict_merge(*dicts):
    """
    Merge one or more dicts into one.

    >>> d = dict_merge({'a': 'A'}, {'b': 'B'}, {'c': 'C'})
    >>> sorted(d.keys()), sorted(d.values())
    (['a', 'b', 'c'], ['A', 'B', 'C'])
    """
    final = {}
    for d in dicts:
        final.update(d)
    return final


def play_nice_with_threads():
    """
    Long-running batch jobs should call this now and then to pause
    their activities if there are other threads that would like to
    run. This is a bit of a hack!
    """
    delay = max(0, 0.01 * (threading.activeCount() - 2))
    if delay:
        time.sleep(delay)
    return delay


def thumbnail(fileobj, output_fd, height=None, width=None):
    """
    Generates a thumbnail image , which should be a file,
    StringIO, or string, containing a PIL-supported image.
    FIXME: Failure modes unmanaged.

    Keyword arguments:
    fileobj -- Either a StringIO instance, a file object or
                         a string (containing the image) to
                         read the source image from
    output_fd -- A file object or filename, or StringIO to
    """
    if not Image:
        # If we don't have PIL, we just return the supplied filename in
        # the hopes that somebody had the good sense to extract the
        # right attachment to that filename...
        return None

    # Ensure the source image is either a file-like object or a StringIO
    if (not isinstance(fileobj, (file, StringIO.StringIO))):
        fileobj = StringIO.StringIO(fileobj)

    image = Image.open(fileobj)

    # defining the size
    if height is None and width is None:
        raise Exception("Must supply width or height!")
    # If only one coordinate is given, calculate the
    # missing one in order to make the thumbnail
    # have the same proportions as the source img
    if height and not width:
        x = height
        y = int((float(height) / image.size[0]) * image.size[1])
    elif width and not height:
        y = width
        x = int((float(width) / image.size[1]) * image.size[0])
    else:  # We have both sizes
        y = width
        x = height
    try:
        image.thumbnail([x, y], Image.ANTIALIAS)
    except IOError:
        return None

    # If saving an optimized image fails, save it unoptimized
    # Keep the format (png, jpg) of the source image
    try:
        image.save(output_fd, format=image.format, quality=90, optimize=1)
    except:
        image.save(output_fd, format=image.format, quality=90)

    return image


class CleanText:
    """
    This is a helper class for aggressively cleaning text, dumbing it
    down to just ASCII and optionally forbidding some characters.

    >>> CleanText(u'clean up\\xfe', banned='up ').clean
    'clean'
    >>> CleanText(u'clean\\xfe', replace='_').clean
    'clean_'
    >>> CleanText(u'clean\\t').clean
    'clean\\t'
    >>> str(CleanText(u'c:\\\\l/e.an', banned=CleanText.FS))
    'clean'
    >>> CleanText(u'c_(l e$ a) n!', banned=CleanText.NONALNUM).clean
    'clean'
    """
    FS = ':/.\'\"\\'
    CRLF = '\r\n'
    WHITESPACE = '\r\n\t '
    NONALNUM = ''.join([chr(c) for c in (set(range(32, 127)) -
                                         set(range(ord('0'), ord('9') + 1)) -
                                         set(range(ord('a'), ord('z') + 1)) -
                                         set(range(ord('A'), ord('Z') + 1)))])
    NONDNS = ''.join([chr(c) for c in (set(range(32, 127)) -
                                       set(range(ord('0'), ord('9') + 1)) -
                                       set(range(ord('a'), ord('z') + 1)) -
                                       set(range(ord('A'), ord('Z') + 1)) -
                                       set([ord('-'), ord('_'), ord('.')]))])
    NONVARS = ''.join([chr(c) for c in (set(range(32, 127)) -
                                        set(range(ord('0'), ord('9') + 1)) -
                                        set(range(ord('a'), ord('z') + 1)) -
                                        set([ord('_')]))])

    def __init__(self, text, banned='', replace=''):
        self.clean = str("".join([i if (((ord(i) > 31 and ord(i) < 127) or
                                         (i in self.WHITESPACE)) and
                                        i not in banned) else replace
                                  for i in (text or '')]))

    def __str__(self):
        return str(self.clean)

    def __unicode__(self):
        return unicode(self.clean)


def HideBinary(text):
    try:
        text.decode('utf-8')
        return text
    except UnicodeDecodeError:
        return '[BINARY DATA, %d BYTES]' % len(text)


class DebugFileWrapper(object):
    def __init__(self, dbg, fd):
        self.fd = fd
        self.dbg = dbg

    def __getattribute__(self, name):
        if name in ('fd', 'dbg', 'write', 'flush', 'close'):
            return object.__getattribute__(self, name)
        else:
            self.dbg.write('==(%d.%s)\n' % (self.fd.fileno(), name))
            return object.__getattribute__(self.fd, name)

    def write(self, data, *args, **kwargs):
        self.dbg.write('<=(%d.write)= %s\n' % (self.fd.fileno(),
                                               HideBinary(data).rstrip()))
        return self.fd.write(data, *args, **kwargs)

    def flush(self, *args, **kwargs):
        self.dbg.write('==(%d.flush)\n' % self.fd.fileno())
        return self.fd.flush(*args, **kwargs)

    def close(self, *args, **kwargs):
        self.dbg.write('==(%d.close)\n' % self.fd.fileno())
        return self.fd.close(*args, **kwargs)


# If 'python util.py' is executed, start the doctest unittest
if __name__ == "__main__":
    import doctest
    import sys
    if doctest.testmod().failed:
        sys.exit(1)
