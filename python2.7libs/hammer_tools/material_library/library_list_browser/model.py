try:
    from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt
except ImportError:
    from PySide2.QtCore import QAbstractListModel, QModelIndex, Qt

from ..data_roles import InternalDataRole
from ..library import Library, AllLibrary, UnboundLibrary
from ..library.polyhaven_library import PolyHavenLibrary  # Fixme
from ..tooltip_formlayout import ToolTipFormLayout


class LibraryListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super(LibraryListModel, self).__init__(parent)

        self._libraries = ()

    def updateLibraryList(self):
        self.beginResetModel()
        self._libraries = AllLibrary(), UnboundLibrary()
        try:
            self._libraries += PolyHavenLibrary(),
        except Exception:  # Test only
            pass
        self._libraries += Library.allLibraries()
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._libraries)

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        return self.createIndex(row, column, self._libraries[row])

    def data(self, index, role):
        if not index.isValid():
            return

        library = index.internalPointer()

        if role == InternalDataRole:
            return library

        if role == Qt.DisplayRole:
            return library.name()
        elif role == Qt.ToolTipRole:
            tooltip = ToolTipFormLayout()
            tooltip.addRow('<b>ID</b>', library.id())
            tooltip.addRow('<b>Name</b>', library.name())
            tooltip.addRow('<b>Path</b>', library.path())
            tooltip.addRow('<b>Comment</b>', library.comment() or None)
            tooltip.addRow('<b>Materials</b>', len(library.materials()))
            tooltip.addRow('<b>Textures</b>', len(library.textures()))
            return str(tooltip)
