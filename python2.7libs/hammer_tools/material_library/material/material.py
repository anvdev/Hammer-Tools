import os
import sqlite3

try:
    from PyQt5.QtCore import QBuffer, QIODevice
    from PyQt5.QtGui import QImage, QPixmap, QIcon
except ImportError:
    from PySide2.QtCore import QBuffer, QIODevice
    from PySide2.QtGui import QImage, QPixmap, QIcon

import hou

from ..db.connect import connect
from ..texture_map import MapType, TextureMap
from .material_options import MaterialOptions
from .material_source import MaterialSource

MISSING_THUMBNAIL_ICON = hou.qt.Icon('SHOP_vopmaterial', 256, 256)


def imageToBytes(image):
    buffer = QBuffer()
    buffer.open(QIODevice.ReadWrite)
    image.save(buffer, 'png')
    data = buffer.data()
    buffer.close()
    return data


class Material(object):
    @staticmethod
    def fromData(data):
        mat = Material()
        mat._id = data.get('id')
        mat._name = data['name']
        mat._comment = data.get('comment')
        mat._favorite = data.get('favorite', False)
        mat._options = data.get('options')
        mat._source_path = data['source_path'].replace('\\', '/')
        return mat

    def asData(self):
        return {
            'id': self.id(),
            'name': self.name(),
            'comment': self.comment(),
            'favorite': self.isFavorite(),
            'options': self._options,
            'source_path': self._source_path,
            'thumbnail': sqlite3.Binary(imageToBytes(self._thumbnail))
            if self._thumbnail and self._thumbnail != MISSING_THUMBNAIL_ICON else None
        }

    @staticmethod
    def allMaterials():
        connection = connect()
        materials_data = connection.execute('SELECT id, name, comment, favorite, source_path FROM material').fetchall()
        connection.close()
        return tuple(Material.fromData(data) for data in materials_data)

    @staticmethod
    def addMaterial(material, external_connection=None):
        if isinstance(material, dict):
            material = Material.fromData(material)

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        cursor = connection.execute('INSERT INTO material (name, comment, favorite, options, source_path, thumbnail) '
                                    'VALUES (:name, :comment, :favorite, :options, :source_path, :thumbnail)',
                                    material.asData())
        material._id = cursor.lastrowid

        if external_connection is None:
            connection.commit()
            connection.close()
        return material

    @staticmethod
    def addMaterialsFromFolder(path, naming_mode, library=None, favorite=False, options=None):
        materials = []
        for root, _, files in os.walk(path):
            for file in files:
                if TextureMap.mapType(file) not in (MapType.Unknown, MapType.Thumbnail):
                    mat = Material.fromData({
                        'name': os.path.basename(root),
                        'favorite': favorite,
                        'options': options,
                        'source_path': root
                    })
                    materials.append(mat)
                    break

        connection = connect()
        connection.execute('BEGIN')

        if library is not None:
            for mat in materials:
                library.addMaterial(mat, connection)
        else:
            for mat in materials:
                Material.addMaterial(mat, connection)

        connection.commit()
        connection.close()

        return tuple(materials)

    def __init__(self):
        self._id = None
        self._name = None
        self._comment = None
        self._favorite = None
        self._options = None
        self._source_path = None
        self._thumbnail = None
        self._thumbnail_engine_id = None
        self._thumbnail_for_engine = None

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
        return self._comment

    def isFavorite(self):
        return self._favorite

    def markAsFavorite(self, state=True, external_connection=None):
        if self.id() is None:
            self._favorite = state
            return

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        connection.execute('UPDATE material SET favorite = :state WHERE id = :material_id',
                           {'state': state, 'material_id': self.id()})

        self._favorite = state

        if external_connection is None:
            connection.commit()
            connection.close()

    def _loadDefaultThumbnail(self):
        if self.id() is None:
            return

        connection = connect()
        data = connection.execute('SELECT thumbnail AS image FROM material '
                                  'WHERE id = :material_id',
                                  {'material_id': self.id()}).fetchone()
        connection.close()
        if data['image']:
            self._thumbnail = QIcon(QPixmap.fromImage(QImage.fromData(bytes(data['image']), 'png')))
        else:
            self._thumbnail = MISSING_THUMBNAIL_ICON

    def thumbnail(self, engine=None):
        if self.id() and engine:
            if engine.id() != self._thumbnail_engine_id:
                connection = connect()
                data = connection.execute('SELECT image FROM material_thumbnail '
                                          'WHERE material_id = :material_id AND engine_id = :engine_id',
                                          {'material_id': self.id(), 'engine_id': engine.id()}).fetchone()
                connection.close()
                if data is not None:
                    self._thumbnail_for_engine = QIcon(
                        QPixmap.fromImage(QImage.fromData(bytes(data['image']), 'png'))
                    )
                    self._thumbnail_engine_id = engine.id()
                    return self._thumbnail_for_engine
            else:
                return self._thumbnail_for_engine

        if self._thumbnail is None:
            self._loadDefaultThumbnail()
        return self._thumbnail

    def addThumbnail(self, image, engine_id=None, external_connection=None):
        if self.id() is None:
            self._thumbnail = image
            return

        image_data = sqlite3.Binary(imageToBytes(image))

        if external_connection is None:
            connection = connect()
        else:
            connection = external_connection

        if engine_id is None:
            connection.execute('UPDATE material SET thumbnail = :image WHERE id = :id',
                               {'id': self.id(), 'image': image_data})
        else:
            connection.execute('INSERT OR UPDATE INTO material VALUES (:material_id, :engine_id, :image)',
                               {'material_id': self.id(), 'engine_id': engine_id, 'image': image_data})

        if external_connection is None:
            connection.commit()
            connection.close()

    def options(self):
        return MaterialOptions.fromData(self._options)

    def source(self):
        return MaterialSource(self, self._source_path)

    def textures(self):
        return self.source().textures()

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
