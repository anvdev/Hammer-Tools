import os
import sqlite3

try:
    from PyQt5.QtCore import QBuffer, QIODevice
    from PyQt5.QtGui import QImage, QPixmap, QIcon
except ImportError:
    from PySide2.QtCore import QBuffer, QIODevice
    from PySide2.QtGui import QImage, QPixmap, QIcon

from . import ui
from .db import connect
from .texture import Texture
from .map_type import MapType
from .image import imageToBytes
from .text import convertName

MISSING_MATERIAL_THUMBNAIL_ICON = ui.icon('SOP_material', 256)


class Material(object):
    __slots__ = ('_id', '_name', '_comment', '_favorite', '_options', '_path', '_thumbnail',
                 '_thumbnail_engine_id', '_thumbnail')

    def fillFromData(self, data):
        self._id = data.get('id', self._id)
        self._name = data.get('name', self._name)
        self._comment = data.get('comment', self._comment)
        self._favorite = data.get('favorite', self._favorite)
        self._options = data.get('options', self._options)
        self._path = data.get('path', self._path).replace('\\', '/')

    @staticmethod
    def fromData(data):
        mat = Material()
        mat.fillFromData(data)
        return mat

    def asData(self):
        return {
            'id': self.id(),
            'name': self.name(),
            'comment': self.comment() or None,
            'favorite': self.isFavorite(),
            'options': self._options or None,
            'path': self._path
        }

    @staticmethod
    def allMaterials():
        connection = connect()
        materials_data = connection.execute('SELECT id, name, comment, favorite, path FROM material').fetchall()
        connection.close()
        return tuple(Material.fromData(data) for data in materials_data)

    @staticmethod
    def addMaterialToDB(material, external_connection=None):
        if isinstance(material, dict):
            material = Material.fromData(material)

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        connection.execute('PRAGMA foreign_keys = OFF')
        cursor = connection.execute(
            'INSERT OR REPLACE INTO material (id, name, comment, favorite, options, path) '
            'VALUES (:id, :name, :comment, :favorite, :options, :path)',
            material.asData()
        )
        if material.id() is None:
            material._id = cursor.lastrowid
        connection.execute('PRAGMA foreign_keys = ON')

        if external_connection is None:
            connection.commit()
            connection.close()
        return material

    @staticmethod
    def addMaterialsFromFolder(path, naming_options=None, library=None, favorite=False, options=None):
        materials = []
        for root, _, files in os.walk(path):
            for file in files:
                if MapType.mapType(file) not in {MapType.Unknown, MapType.Thumbnail}:
                    mat = Material.fromData({
                        'name': convertName(os.path.basename(root), naming_options),
                        'favorite': favorite,
                        'options': options,
                        'path': root
                    })
                    materials.append(mat)
                    break

        connection = connect()
        connection.execute('BEGIN')

        if library is not None:
            for mat in materials:
                try:
                    library.addMaterial(mat, external_connection=connection)
                except sqlite3.IntegrityError:
                    continue
        else:
            for mat in materials:
                try:
                    Material.addMaterialToDB(mat, external_connection=connection)
                except sqlite3.IntegrityError:
                    continue

        connection.commit()
        connection.close()
        return tuple(mat for mat in materials if mat.id() is not None)

    def __init__(self):
        self._id = None
        self._name = None
        self._comment = None
        self._favorite = None
        self._options = None
        self._path = None
        self._thumbnail_engine_id = None
        self._thumbnail = None

    def id(self):
        return self._id

    def __eq__(self, other):
        if isinstance(other, Material):
            if self.id() and other.id():
                return self.id() == other.id()
            else:
                pass  # Todo: Compare attributes
        else:
            return NotImplemented

    def name(self):
        return self._name

    def comment(self):
        return self._comment or ''

    def isFavorite(self):
        return self._favorite

    def markAsFavorite(self, state=True, external_connection=None):
        if state is None:
            state = not self._favorite

        self._favorite = state

        if self.id() is None:
            return

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        connection.execute('UPDATE material SET favorite = :state WHERE id = :material_id',
                           {'state': state, 'material_id': self.id()})

        if external_connection is None:
            connection.commit()
            connection.close()

    def thumbnail(self, engine=None, reload=False):
        if engine is not None and self.id():
            if engine.id() != self._thumbnail_engine_id:
                connection = connect()
                data = connection.execute('SELECT image FROM material_thumbnail '
                                          'WHERE material_id = :material_id AND engine_id = :engine_id',
                                          {'material_id': self.id(), 'engine_id': engine.id()}).fetchone()
                connection.close()
                if data is not None:
                    self._thumbnail = QIcon(
                        QPixmap.fromImage(QImage.fromData(bytes(data['image']), 'png'))
                    )
                    self._thumbnail_engine_id = engine.id()
                    return self._thumbnail
        return self._thumbnail

    def addThumbnail(self, image, engine_id, external_connection=None):
        if self.id() is None:  # Fixme
            self._thumbnail = image
            return

        image_data = sqlite3.Binary(imageToBytes(image))

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        connection.execute('INSERT OR REPLACE INTO material_thumbnail '
                           '(material_id, engine_id, image) '
                           'VALUES (:material_id, :engine_id, :image)',
                           {'material_id': self.id(), 'engine_id': engine_id, 'image': image_data})

        if external_connection is None:
            connection.commit()
            connection.close()

    def options(self):
        return self._options or {}

    def path(self):
        return self._path

    def textures(self):  # Todo: + Textures from database
        textures = []
        for file_name in os.listdir(self.path()):
            tex = Texture(file_name, self)
            if tex.type not in {MapType.Unknown, MapType.Thumbnail}:
                textures.append(tex)
        return tuple(set(textures))

    def addTexture(self, texture, role=None, external_connection=None):
        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        if texture.id() is None:
            Texture.addTextureToDB(texture, external_connection=connection)

        connection.execute('INSERT INTO texture_material VALUES (:texture_id, :library_id, :role)',
                           {'texture_id': texture.id(), 'role': role, 'library_id': self.id()})

        if external_connection is None:
            connection.commit()
            connection.close()
        return texture

    def libraries(self):
        from .library import Library

        connection = connect()
        libraries_data = connection.execute('SELECT * FROM library '
                                            'LEFT JOIN material_library ON material_library.library_id = library.id '
                                            'WHERE material_library.material_id = :material_id',
                                            {'library_id': self.id()})
        connection.close()
        return tuple(Library.fromData(data) for data in libraries_data)

    def remove(self, external_connection=None):
        if self.id() is None:
            return

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        connection.execute('DELETE FROM material '
                           'WHERE id = :material_id',
                           {'material_id': self.id()})

        self._id = None

        if external_connection is None:
            connection.commit()
            connection.close()
