# -*- coding: utf-8 -*-
"""Geometry Extractor (WKT/WKB) QGIS plugin.

WKT is returned as text. WKB is exported as hexadecimal text in
little-endian byte order. No geometry normalization, coordinate
rounding, or vertex reordering is performed.
"""

import os
import csv
import traceback

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QSplitter, QGroupBox, QAbstractItemView, QApplication
)
from osgeo import gdal, ogr
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes


class GeometryExtractorDialog(QDialog):
    PREVIEW_LIMIT = 2000

    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Geometry Extractor — WKT / WKB")
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icon.svg")))
        self.resize(1200, 780)
        self.source_path = ""
        self.layers = []
        self.records = []
        self._build_ui()
        if self.source_kind.currentData() == "qgis":
            self.refresh_qgis_layers()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Geometry Extractor — WKT / WKB")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        root.addWidget(title)

        intro = QLabel(
            "Extract feature geometries from loaded QGIS vector layers, File Geodatabases, "
            "or Shapefiles. Choose WKT text or WKB hexadecimal output. Geometry coordinates "
            "and vertex order are not normalized or modified."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        source_group = QGroupBox("Input source")
        source_form = QFormLayout(source_group)

        source_row = QHBoxLayout()
        self.source_kind = QComboBox()
        self.source_kind.addItem("Loaded QGIS Map Layer", "qgis")
        self.source_kind.addItem("File Geodatabase (.gdb)", "gdb")
        self.source_kind.addItem("Shapefile (.shp)", "shp")
        self.source_kind.currentIndexChanged.connect(self.source_kind_changed)
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setReadOnly(True)
        self.source_path_edit.setPlaceholderText("Select a source...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_source)
        self.browse_button = browse_btn
        self.refresh_layers_btn = QPushButton("Refresh")
        self.refresh_layers_btn.clicked.connect(self.refresh_qgis_layers)
        source_row.addWidget(self.source_kind)
        source_row.addWidget(self.source_path_edit, 1)
        source_row.addWidget(browse_btn)
        source_row.addWidget(self.refresh_layers_btn)
        source_form.addRow("Source:", source_row)

        self.layer_combo = QComboBox()
        self.layer_combo.setEnabled(False)
        source_form.addRow("Feature Class / Layer:", self.layer_combo)

        self.format_combo = QComboBox()
        self.format_combo.addItem("WKT", "wkt")
        self.format_combo.addItem("WKB (HEX, little-endian)", "wkb_hex")
        self.format_combo.currentIndexChanged.connect(self.change_output_format)
        source_form.addRow("Output format:", self.format_combo)

        root.addWidget(source_group)

        action_row = QHBoxLayout()
        self.extract_btn = QPushButton("Extract Geometry")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self.extract_geometry)
        self.export_btn = QPushButton("Export All to CSV...")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_csv)
        self.copy_btn = QPushButton("Copy Selected Geometry")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_selected_geometry)
        action_row.addWidget(self.extract_btn)
        action_row.addWidget(self.export_btn)
        action_row.addWidget(self.copy_btn)
        action_row.addStretch()
        root.addLayout(action_row)

        self.status_label = QLabel("Select a source and layer to begin.")
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Vertical)

        table_group = QGroupBox("Extracted features (preview)")
        table_layout = QVBoxLayout(table_group)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Feature ID (FID)", "Geometry Type", "Geometry"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.show_selected_geometry)
        table_layout.addWidget(self.table)
        splitter.addWidget(table_group)

        geometry_group = QGroupBox("Selected feature — full geometry representation")
        geometry_layout = QVBoxLayout(geometry_group)
        self.geometry_text = QPlainTextEdit()
        self.geometry_text.setReadOnly(True)
        self.geometry_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        geometry_layout.addWidget(self.geometry_text)
        splitter.addWidget(geometry_group)
        splitter.setSizes([430, 250])
        root.addWidget(splitter, 1)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        root.addWidget(self.note_label)
        self._update_note()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _update_note(self):
        fmt = self.format_combo.currentData()
        if fmt == "wkt":
            detail = "WKT is exported as text."
        else:
            detail = (
                "WKB is exported as hexadecimal text (HEX), using little-endian "
                "byte order. This is a readable representation of WKB bytes."
            )
        self.note_label.setText(
            "Preview limit: {:,} features. CSV export includes all features. {} "
            "The output is generated from the geometry object; it is not a byte-for-byte "
            "dump of the source file's internal storage."
            .format(self.PREVIEW_LIMIT, detail)
        )

    def change_output_format(self):
        self._update_note()
        if self.records:
            self._populate_table()

    def source_kind_changed(self):
        kind = self.source_kind.currentData()
        is_qgis = kind == "qgis"
        self.source_path_edit.setEnabled(not is_qgis)
        self.browse_button.setEnabled(not is_qgis)
        self.refresh_layers_btn.setEnabled(is_qgis)

        self.source_path = ""
        self.source_path_edit.clear()
        self.layers = []
        self.layer_combo.clear()
        self.layer_combo.setEnabled(False)
        self.extract_btn.setEnabled(False)
        self.records = []
        self.table.setRowCount(0)
        self.geometry_text.clear()
        self.export_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)

        if is_qgis:
            self.refresh_qgis_layers()
        else:
            self.status_label.setText("Browse for a File Geodatabase or Shapefile.")

    def refresh_qgis_layers(self):
        if self.source_kind.currentData() != "qgis":
            return

        project = QgsProject.instance()
        vector_layers = [
            layer for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer) and layer.isValid()
        ]

        # Put the active layer first when it is a valid vector layer.
        active_layer = self.iface.activeLayer() if self.iface is not None else None
        if active_layer in vector_layers:
            vector_layers.remove(active_layer)
            vector_layers.insert(0, active_layer)

        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layers = []
        for layer in vector_layers:
            self.layers.append({"id": layer.id(), "name": layer.name()})
            self.layer_combo.addItem(layer.name(), layer.id())
        self.layer_combo.blockSignals(False)

        self.layer_combo.setEnabled(bool(vector_layers))
        self.extract_btn.setEnabled(bool(vector_layers))
        self.source_path_edit.setText(
            "{} vector layer(s) loaded in the current QGIS project".format(
                len(vector_layers)
            )
        )
        self.status_label.setText(
            "Select a loaded QGIS vector layer and click Extract Geometry."
            if vector_layers else
            "No valid vector layers are currently loaded in the QGIS project."
        )

    def browse_source(self):
        kind = self.source_kind.currentData()
        if kind == "qgis":
            self.refresh_qgis_layers()
            return

        if kind == "gdb":
            path = QFileDialog.getExistingDirectory(
                self, "Select File Geodatabase (.gdb)"
            )
            if not path:
                return
            if not path.lower().endswith(".gdb") or not os.path.isdir(path):
                QMessageBox.warning(
                    self, "Invalid source",
                    "Select a File Geodatabase folder ending in .gdb."
                )
                return
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Shapefile", "", "Shapefile (*.shp)"
            )
            if not path:
                return
            if not path.lower().endswith(".shp") or not os.path.isfile(path):
                QMessageBox.warning(
                    self, "Invalid source",
                    "Select a file with the .shp extension."
                )
                return

        try:
            ds = gdal.OpenEx(path, gdal.OF_VECTOR | gdal.OF_READONLY)
            if ds is None:
                raise RuntimeError("GDAL/OGR could not open the selected source.")
            layers = []
            try:
                for i in range(ds.GetLayerCount()):
                    layer = ds.GetLayerByIndex(i)
                    if layer is not None:
                        layers.append({"index": i, "name": layer.GetName()})
            finally:
                ds = None

            if not layers:
                QMessageBox.warning(
                    self, "No layers found",
                    "The source was opened, but no vector layers were found."
                )
                return

            self.source_path = os.path.normpath(path)
            self.layers = layers
            self.source_path_edit.setText(self.source_path)
            self.layer_combo.blockSignals(True)
            self.layer_combo.clear()
            for item in layers:
                self.layer_combo.addItem(
                    "{}  [layer {}]".format(item["name"], item["index"]),
                    item["index"]
                )
            self.layer_combo.blockSignals(False)
            self.layer_combo.setEnabled(True)
            self.extract_btn.setEnabled(True)
            self.records = []
            self.table.setRowCount(0)
            self.geometry_text.clear()
            self.export_btn.setEnabled(False)
            self.copy_btn.setEnabled(False)
            self.status_label.setText(
                "Source loaded: {} layer(s). Select a layer and click Extract Geometry."
                .format(len(layers))
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Source error",
                "{}\\n\\n{}".format(exc, traceback.format_exc())
            )

    def _open_selected_layer(self):
        if not self.source_path or self.layer_combo.currentIndex() < 0:
            raise RuntimeError("Select a source and a layer first.")
        ds = gdal.OpenEx(self.source_path, gdal.OF_VECTOR | gdal.OF_READONLY)
        if ds is None:
            raise RuntimeError("Could not reopen the selected source.")
        layer = ds.GetLayerByIndex(int(self.layer_combo.currentData()))
        if layer is None:
            ds = None
            raise RuntimeError("Could not read the selected layer.")
        return ds, layer

    @staticmethod
    def _get_geometry_type(geom):
        if geom is None:
            return "None"
        try:
            return geom.GetGeometryName()
        except Exception:
            return "Unknown"

    @staticmethod
    def _export_geometry(geom, output_format):
        if geom is None:
            return ""
        if output_format == "wkt":
            try:
                return geom.ExportToWkt()
            except TypeError:
                return geom.ExportToWkt([])
        # OGR WKB byte order constants: wkbNDR = little-endian.
        try:
            raw = geom.ExportToWkb(ogr.wkbNDR)
        except TypeError:
            raw = geom.ExportToWkb()
        if isinstance(raw, bytearray):
            raw = bytes(raw)
        return raw.hex().upper()

    def _extract_qgis_layer(self, layer):
        count = 0
        total = layer.featureCount()
        self.status_label.setText(
            "Reading QGIS layer... reported feature count: {}".format(total)
        )
        QApplication.processEvents()

        for feature in layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isNull():
                geometry_type = "None"
                wkt_value = ""
                wkb_value = ""
            else:
                geometry_type = QgsWkbTypes.displayString(geom.wkbType())
                wkt_value = geom.asWkt()
                wkb_value = bytes(geom.asWkb()).hex().upper()

            self.records.append({
                "fid": feature.id(),
                "geometry_type": geometry_type,
                "wkt": wkt_value,
                "wkb_hex": wkb_value
            })
            count += 1
            if count % 1000 == 0:
                self.status_label.setText(
                    "Reading QGIS layer... {:,} processed".format(count)
                )
                QApplication.processEvents()

    def extract_geometry(self):
        kind = self.source_kind.currentData()
        if self.layer_combo.currentIndex() < 0:
            return
        if kind != "qgis" and not self.source_path:
            return

        self.extract_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.records = []
        self.table.setRowCount(0)
        self.geometry_text.clear()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if kind == "qgis":
                layer_id = self.layer_combo.currentData()
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer is None or not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                    raise RuntimeError(
                        "The selected QGIS layer is no longer available. Refresh the layer list."
                    )
                self._extract_qgis_layer(layer)
                source_name = layer.name()
            else:
                ds, layer = self._open_selected_layer()
                try:
                    layer.ResetReading()
                    total = layer.GetFeatureCount()
                    self.status_label.setText(
                        "Reading features... reported feature count: {}".format(total)
                    )
                    QApplication.processEvents()

                    count = 0
                    for feature in layer:
                        geom = feature.GetGeometryRef()
                        self.records.append({
                            "fid": feature.GetFID(),
                            "geometry_type": self._get_geometry_type(geom),
                            "wkt": self._export_geometry(geom, "wkt"),
                            "wkb_hex": self._export_geometry(geom, "wkb_hex")
                        })
                        count += 1
                        if count % 1000 == 0:
                            self.status_label.setText(
                                "Reading features... {:,} processed".format(count)
                            )
                            QApplication.processEvents()
                finally:
                    ds = None
                source_name = os.path.basename(self.source_path)

            self._populate_table()
            self.export_btn.setEnabled(bool(self.records))
            self.copy_btn.setEnabled(bool(self.records))
            self.status_label.setText(
                "Completed: {:,} feature(s) extracted from '{}'. {:,} shown in preview."
                .format(
                    len(self.records), source_name,
                    min(len(self.records), self.PREVIEW_LIMIT)
                )
            )
            if self.records:
                self.table.selectRow(0)
        except Exception as exc:
            QMessageBox.critical(
                self, "Extraction failed",
                "{}\\n\\n{}".format(exc, traceback.format_exc())
            )
            self.status_label.setText("Extraction failed.")
        finally:
            QApplication.restoreOverrideCursor()
            self.extract_btn.setEnabled(self.layer_combo.currentIndex() >= 0)

    def _current_value(self, record):
        if self.format_combo.currentData() == "wkt":
            return record["wkt"]
        return record["wkb_hex"]

    def _populate_table(self):
        count = min(len(self.records), self.PREVIEW_LIMIT)
        self.table.setRowCount(count)
        for row, record in enumerate(self.records[:count]):
            values = [
                record["fid"],
                record["geometry_type"],
                self._current_value(record)
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(row, col, item)
        self.table.setHorizontalHeaderLabels([
            "Feature ID (FID)",
            "Geometry Type",
            "WKT" if self.format_combo.currentData() == "wkt" else "WKB (HEX)"
        ])

    def show_selected_geometry(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.geometry_text.clear()
            return
        index = rows[0].row()
        if 0 <= index < len(self.records):
            self.geometry_text.setPlainText(
                self._current_value(self.records[index])
            )
            self.copy_btn.setEnabled(bool(self._current_value(self.records[index])))

    def copy_selected_geometry(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        index = rows[0].row()
        if 0 <= index < len(self.records):
            value = self._current_value(self.records[index])
            QApplication.clipboard().setText(value)
            label = "WKT" if self.format_combo.currentData() == "wkt" else "WKB HEX"
            self.status_label.setText(
                "{} for FID {} copied to clipboard.".format(
                    label, self.records[index]["fid"]
                )
            )

    def export_csv(self):
        if not self.records:
            QMessageBox.information(self, "No data", "Extract geometry first.")
            return
        fmt = self.format_combo.currentData()
        default_name = "Geometry_Extraction_{}.csv".format(
            "WKT" if fmt == "wkt" else "WKB_HEX"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export geometry records", default_name, "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            field_name = "WKT" if fmt == "wkt" else "WKB_HEX"
            with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(["FID", "Geometry_Type", field_name])
                for record in self.records:
                    writer.writerow([
                        record["fid"],
                        record["geometry_type"],
                        self._current_value(record)
                    ])
            QMessageBox.information(
                self, "Export complete",
                "Exported {:,} feature(s) to:\n{}".format(len(self.records), path)
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


class GeometryExtractorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        self.action = QAction(
            QIcon(icon_path), "Geometry Extractor (WKT/WKB)",
            self.iface.mainWindow()
        )
        self.action.setToolTip("Extract feature geometries as WKT or WKB")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Geometry Extractor (WKT/WKB)", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Geometry Extractor (WKT/WKB)", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = GeometryExtractorDialog(self.iface.mainWindow(), self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
