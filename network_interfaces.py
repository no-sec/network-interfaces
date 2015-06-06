# -*- coding: utf-8 -*-
import re
import os
import shutil

__version__ = '0.1.0'
__author__ = 'vahid'

DEFAULT_HEADER = """
# Generated by `networking-interfaces`. A python library to manage /etc/network/interfaces file.
# You may manually edit this file. But it may be rewritten by the library.
"""


def clean_list(l):
    return [j for j in [i.strip().strip('"') for i in l] if j]


def list_hash(l):
    return hash(tuple(l))


class Stanza(object):
    _type = None
    _filename = None
    _headers = None
    _items = None

    def __init__(self, filename, *headers):
        self._filename = filename
        self._headers = headers
        self._items = []

    def add_entry(self, l):
        cells = re.split('\s+', l)
        cells = clean_list(cells)
        if cells:
            self._items.append(cells)

    def __repr__(self):
        return ' '.join(self._headers)

    def __getattr__(self, item):
        try:
            return self[item]
        except (KeyError, IndexError):
            raise AttributeError('%s %s' % (object.__repr__(self), item))

    def __setattr__(self, key, value):
        if hasattr(self.__class__, key):
            super(Stanza, self).__setattr__(key, value)
        else:
            self[key] = value

    def __getitem_internal(self, item):
        key = item.replace('_', '-')
        for i in self._items:
            if i[0] == key:
                return i
        return None

    def __getitem__(self, item):
        if not isinstance(item, basestring):
            raise TypeError(type(item))
        result = self.__getitem_internal(item)
        if not result:
            raise KeyError(item)
        return ' '.join(result[1:])

    def __setitem__(self, key, value):
        if not isinstance(key, basestring):
            raise TypeError(type(key))
        values = re.split('\s', value)

        cells = self.__getitem_internal(key)
        if not cells:
            self.add_entry(' '.join([key] + values))
        else:
            del cells[1:]
            cells += values

    def __delitem__(self, key):
        pass

    def _items_hash(self):
        result = 0
        for i in self._items:
            result ^= list_hash(i)
        return result

    def _headers_hash(self):
        result = 0
        for h in self._headers:
            result ^= h.__hash__()
        return result

    def __hash__(self):
        return \
            self._type.__hash__() ^ \
            self._headers_hash() ^ \
            self._items_hash()

    @classmethod
    def is_stanza(cls, s):
        return re.match(r'^(iface|mapping|auto|allow-|source).*', s)

    @classmethod
    def subclasses(cls):
        return cls.__subclasses__() + [g for s in cls.__subclasses__()
                                       for g in s.subclasses()]

    @classmethod
    def create(cls, header, filename):
        cells = re.split('\s+', header)
        cells = clean_list(cells)
        stanza_type = cells[0]
        subclasses = cls.subclasses()

        # Checking for exact match
        for subclass in subclasses:
            if subclass._type and stanza_type == subclass._type:
                return subclass(filename, *cells)

        # Partial start match
        for subclass in subclasses:
            if subclass._type and stanza_type.startswith(subclass._type):
                return subclass(filename, *cells)


class MultilineStanza(Stanza):
    def __repr__(self):
        return '%s\n%s\n' % (
            super(MultilineStanza, self).__repr__(),
            '\n'.join(['  ' + ' '.join(i) for i in self._items]))


class StartupStanza(Stanza):
    @property
    def mode(self):
        return self._headers[0]

    @property
    def iface_name(self):
        return self._headers[1]


class Auto(StartupStanza):
    _type = 'auto'


class Allow(StartupStanza):
    _type = 'allow-'


class IfaceBase(MultilineStanza):
    startup = None

    @property
    def name(self):
        return self._headers[1]

    @name.setter
    def name(self, val):
        self._headers[1] = val

    def __hash__(self):
        return hash(self.startup) ^ super(IfaceBase, self).__hash__()

    def __repr__(self):
        if self.startup:
            return '%s\n%s' % (self.startup, super(IfaceBase, self).__repr__())
        return super(IfaceBase, self).__repr__()


class Iface(IfaceBase):
    _type = 'iface'

    @property
    def address_family(self):
        return self._headers[2]

    @address_family.setter
    def address_family(self, val):
        self._headers[2] = val

    @property
    def method(self):
        return self._headers[3]

    @method.setter
    def method(self, val):
        self._headers[3] = val


class Mapping(IfaceBase):
    _type = 'mapping'

    def __getattr__(self, item):
        if item.startswith('map_'):
            map_name = item.split('_')[1]
            key = map_name.replace('_', '-')
            return ' '.join([i for i in self._items if i[0] == 'map' and i[1] == key][0][2:])
        return super(Mapping, self).__getattr__(item)

    @property
    def mappings(self):
        return [i for i in self._items if i[0] == 'map']


class Source(Stanza):
    _type = 'source'

    @property
    def source_filename(self):
        return self._headers[1]

    @source_filename.setter
    def source_filename(self, val):
        self._headers[1] = val


class SourceDirectory(Stanza):
    _type = 'source-directory'

    @property
    def source_directory(self):
        return self._headers[1]

    @source_directory.setter
    def source_directory(self, val):
        self._headers[1] = val


class InterfacesFile(object):

    @property
    def absolute_filename(self):
        if self.filename.startswith('/'):
            return self.filename

        if self.source:
            rootdir = os.path.dirname(self.source._filename)
            return os.path.abspath(os.path.join(rootdir, self.filename))

        raise ValueError('Cannot resolve absolute path for %s' % self.filename)

    def __init__(self, filename, header=DEFAULT_HEADER, backup='.back', source=None):
        self.source = source
        self.filename = filename
        self.dirname = os.path.dirname(filename)
        self.sub_files = []
        self.header = header
        self.backup = backup
        current_stanza = None
        stanzas = []

        with open(self.absolute_filename) as f:
            for l in f:
                line = l.strip()
                if not line or line.startswith('#'):
                    continue
                if Stanza.is_stanza(line):
                    if current_stanza:
                        stanzas.append(current_stanza)
                    current_stanza = Stanza.create(line, self.filename)
                else:
                    current_stanza.add_entry(line)
            if current_stanza:
                stanzas.append(current_stanza)

        self.interfaces = [iface for iface in stanzas if isinstance(iface, Iface)]
        for i in self.interfaces:
            stanzas.remove(i)

        self.mappings = [mapping for mapping in stanzas if isinstance(mapping, Mapping)]
        for i in self.mappings:
            stanzas.remove(i)

        self.sources = [source for source in stanzas if isinstance(source, (Source, SourceDirectory))]
        subfiles = []
        for i in self.sources:
            if isinstance(i, SourceDirectory):
                d = i.source_directory
                subfiles += [(os.path.join(d, f), i) for f in os.listdir(os.path.join(self.dirname, d))
                             if os.path.isfile(os.path.join(self.dirname, d, f)) and
                             re.match('^[a-zA-Z0-9_-]+$', f)]
            else:
                subfiles.append((i.source_filename, i))

        for subfile in subfiles:
            self.sub_files.append(InterfacesFile(subfile[0], source=subfile[1]))

        for startup in [s for s in stanzas if isinstance(s, StartupStanza)]:
            self.get_iface(startup.iface_name).startup = startup

    def find_iface(self, name):
        return [iface for iface in self.interfaces if iface.name.index(name)]

    def get_iface(self, name):
        result = [iface for iface in self.interfaces + self.mappings if iface.name == name]
        if result:
            return result[0]

        for s in self.sub_files:
            try:
                return s.get_iface(name)
            except KeyError:
                continue

        raise KeyError(name)

    # def normalize_path(self, p):
    #     if p.startswith('/'):
    #         return p
    #     return os.path.join(self.dirname, p)

    def save(self, recursive=False, filename=None, directory=None):

        filename = filename if filename else self.filename
        if not filename.startswith('/') and directory:
            filename = os.path.abspath(os.path.join(directory, filename))

        if self.backup and os.path.exists(filename):
            shutil.copyfile(filename, '%s%s' % (filename, self.backup))

        with open(filename, 'w') as f:
            f.write(self.header)
            for iface in self.interfaces:
                f.write('\n')
                f.write(repr(iface))

            for map in self.mappings:
                f.write('\n')
                f.write(repr(map))

            for source in self.sources:
                f.write('\n')
                f.write(repr(source))

        if recursive:
            dirname = directory if directory else os.path.abspath(os.path.dirname(filename))
            for sub_file in self.sub_files:
                sub_file.save(recursive=recursive, directory=dirname)

    def __hash__(self):
        result = 0
        for iface in self.interfaces:
            result ^= hash(iface)

        for map in self.mappings:
            result ^= hash(map)

        for source in self.sources:
            result ^= hash(source)
        return result


class InterfaceMainFile(InterfacesFile):

    def __init__(self, *args, **kwargs):
        super(InterfaceMainFile, self).__init__(*args, **kwargs)

