import os
import subprocess
import tempfile

try:
    from PyQt5.QtCore import QBuffer, QIODevice, Qt
    from PyQt5.QtGui import QImage
except ImportError:
    from PySide2.QtCore import QBuffer, QIODevice, Qt
    from PySide2.QtGui import QImage


def imageToBytes(image):
    buffer = QBuffer()
    buffer.open(QIODevice.ReadWrite)
    image.save(buffer, 'png')
    data = buffer.data()
    buffer.close()
    return data


def loadImage(path):
    from .texture import TextureFormat

    tex_format = TextureFormat(path)
    if tex_format in {'png', 'bmp', 'tga', 'tif', 'tiff', 'jpg', 'jpeg'}:
        return QImage(path)

    temp_path = os.path.join(tempfile.gettempdir(), str(os.getpid()) + 'hammer_temp_image.png')
    temp_path = temp_path.replace('\\', '/')
    subprocess.call('iconvert -g off {0} {1}'.format(path, temp_path))
    try:
        return QImage(temp_path)
    finally:
        os.remove(temp_path)
