# Geometry Extractor (WKT/WKB)

A QGIS plugin for extracting and inspecting vector feature geometries as WKT or hexadecimal WKB.

## Features

- Read vector layers already loaded in the current QGIS project.
- Read File Geodatabases (`.gdb`) and Shapefiles (`.shp`) directly.
- Export geometry as WKT or WKB hexadecimal text (little-endian).
- Preview up to 2,000 features in the table.
- Inspect the full geometry representation of the selected feature.
- Copy the selected geometry to the clipboard.
- Export all extracted records to a semicolon-delimited CSV file.

## Using a layer loaded in QGIS

1. Open the plugin from **Plugins → Geometry Extractor (WKT/WKB)**.
2. Set **Input source** to **Loaded QGIS Map Layer**.
3. Select a vector layer from the layer list.
4. Click **Refresh** if you have added or removed layers since opening the dialog.
5. Select **WKT** or **WKB (HEX, little-endian)**.
6. Click **Extract Geometry**.

The plugin reads all features from the selected layer, not only the currently selected features.

## Using an external data source

1. Choose **File Geodatabase (.gdb)** or **Shapefile (.shp)**.
2. Browse to the source.
3. Select the layer/feature class.
4. Choose the output format and click **Extract Geometry**.

## Output notes

- WKT is returned as text.
- WKB is exported as uppercase hexadecimal text using little-endian byte order.
- Geometry coordinates and vertex order are not intentionally normalized or modified.
- The output is generated from the geometry object exposed by QGIS or OGR. It is not a byte-for-byte dump of a dataset's internal storage.
- CSV output uses a semicolon (`;`) delimiter and UTF-8 with BOM encoding.

## Requirements

- QGIS 3.22 or later.
- The plugin uses the QGIS Python API and the GDAL/OGR libraries bundled with QGIS.

## Installation

### From a ZIP package

1. In QGIS, open **Plugins → Manage and Install Plugins**.
2. Select **Install from ZIP**.
3. Choose the plugin ZIP file.

### From the QGIS Plugin Repository

Once approved and published, search for **Geometry Extractor (WKT/WKB)** in the QGIS Plugin Repository.

## License

This plugin is licensed under the GNU General Public License, version 2 or (at your option) any later version. See `LICENSE`.
